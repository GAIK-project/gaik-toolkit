"""What an uploaded input file is, decided from its bytes.

A case input and a PoC sample input are handed to the wizard's agent and to the
sandboxed run, so the API checks what each file actually is before it is
stored. The file name and the Content-Type header are only what the client
says; the type comes from the content (its leading signature, and for the
ZIP-based office formats, the archive's own layout), and the declared
extension must agree with it.

Only the types the session's input contract asks for are accepted: the
``artifacts`` the draft blueprint expects from outside the pipeline, and its
``technical_spec.input_types`` / ``input_formats``. A session whose contract
names none of the supported types (no draft yet, or only words we do not map)
accepts every supported type.

Nothing here writes to disk: a refused file never reaches the input directory.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from wizard_api.services import pdf_content, poc_service

# ---------------------------------------------------------------------------
# The supported types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Kind:
    label: str
    extensions: tuple[str, ...]


#: Every type an input may be. The key is the kind the content is detected as.
KINDS: dict[str, Kind] = {
    "pdf": Kind("PDF", (".pdf",)),
    "png": Kind("PNG", (".png",)),
    "jpeg": Kind("JPEG", (".jpg", ".jpeg")),
    "gif": Kind("GIF", (".gif",)),
    "webp": Kind("WebP", (".webp",)),
    "tiff": Kind("TIFF", (".tif", ".tiff")),
    "wav": Kind("WAV", (".wav",)),
    "mp3": Kind("MP3", (".mp3",)),
    "m4a": Kind("M4A", (".m4a",)),
    "txt": Kind("TXT", (".txt",)),
    "md": Kind("MD", (".md", ".markdown")),
    "csv": Kind("CSV", (".csv",)),
    "json": Kind("JSON", (".json",)),
    "docx": Kind("DOCX", (".docx",)),
    "xlsx": Kind("XLSX", (".xlsx",)),
}

_BY_EXTENSION = {ext: key for key, kind in KINDS.items() for ext in kind.extensions}

IMAGE_KINDS = frozenset({"png", "jpeg", "gif", "webp", "tiff"})
AUDIO_KINDS = frozenset({"wav", "mp3", "m4a"})
TEXT_KINDS = frozenset({"txt", "md", "csv", "json"})
ZIP_KINDS = frozenset({"docx", "xlsx"})
ALL_KINDS = frozenset(KINDS)
#: Accepted whatever the contract names: a package's own settings files.
ALWAYS_ACCEPTED = frozenset({"json"})

#: Contract words (artifact types, input types, input formats) → the kinds
#: that satisfy them. A word not here is matched on its ``_``-separated parts,
#: so ``pdf_document`` asks for what ``pdf`` and ``document`` ask for.
_CONTRACT_WORDS: dict[str, frozenset[str]] = {
    "pdf": frozenset({"pdf"}),
    "image": IMAGE_KINDS,
    "images": IMAGE_KINDS,
    "photo": IMAGE_KINDS,
    "picture": IMAGE_KINDS,
    "scan": IMAGE_KINDS | {"pdf"},
    "png": frozenset({"png"}),
    "jpg": frozenset({"jpeg"}),
    "jpeg": frozenset({"jpeg"}),
    "gif": frozenset({"gif"}),
    "webp": frozenset({"webp"}),
    "tif": frozenset({"tiff"}),
    "tiff": frozenset({"tiff"}),
    "audio": AUDIO_KINDS,
    "recording": AUDIO_KINDS,
    "speech": AUDIO_KINDS,
    "voice": AUDIO_KINDS,
    "video": AUDIO_KINDS,
    "wav": frozenset({"wav"}),
    "mp3": frozenset({"mp3"}),
    "m4a": frozenset({"m4a"}),
    "text": frozenset({"txt", "md"}),
    "txt": frozenset({"txt"}),
    "transcript": frozenset({"txt", "md"}),
    "markdown": frozenset({"md"}),
    "md": frozenset({"md"}),
    "csv": frozenset({"csv"}),
    "json": frozenset({"json"}),
    "docx": frozenset({"docx"}),
    "word": frozenset({"docx"}),
    "xlsx": frozenset({"xlsx"}),
    "excel": frozenset({"xlsx"}),
    "spreadsheet": frozenset({"xlsx", "csv"}),
    "tabular": frozenset({"xlsx", "csv"}),
    "table": frozenset({"xlsx", "csv"}),
    "document": frozenset({"pdf", "docx", "txt", "md"}),
    "documents": frozenset({"pdf", "docx", "txt", "md"}),
}

# ---------------------------------------------------------------------------
# Archive bounds (DOCX and XLSX are ZIP files)
# ---------------------------------------------------------------------------

#: What a DOCX or XLSX may unpack to, and how many entries it may hold. Checked
#: on the bytes in memory before anything (the agent, the run, a parser) opens
#: it. Real office documents of a size the upload limit allows sit far below.
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 1000

_READ_CHUNK = 1024 * 1024


class UnsupportedInputError(poc_service.InputRejectedError):
    """The content is not an accepted type, or not the type its name says (415)."""


class InvalidInputError(poc_service.InputRejectedError):
    """The content is an accepted type but not a usable file of it (422)."""


class UnsafeContentError(InvalidInputError):
    """A document that carries macros or actions a viewer would run (422, input_unsafe)."""


# ---------------------------------------------------------------------------
# The session's contract
# ---------------------------------------------------------------------------


def _kinds_for_word(word: Any) -> frozenset[str]:
    if not isinstance(word, str):
        return frozenset()
    norm = word.strip().lower().lstrip(".").replace("-", "_").replace(" ", "_")
    if norm in _CONTRACT_WORDS:
        return _CONTRACT_WORDS[norm]
    found: set[str] = set()
    for part in norm.split("_"):
        found |= _CONTRACT_WORDS.get(part, frozenset())
    return frozenset(found)


def _words(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [value]
    return []


def _wanted_kinds(draft: dict[str, Any] | None) -> set[str]:
    if not isinstance(draft, dict):
        return set()
    wanted: set[str] = set()
    artifacts = draft.get("artifacts")
    if isinstance(artifacts, dict):
        for artifact in artifacts.values():
            if isinstance(artifact, dict) and artifact.get("source") != "generated":
                wanted |= _kinds_for_word(artifact.get("type"))
    tech = draft.get("technical_spec")
    if isinstance(tech, dict):
        for key in ("input_types", "input_formats"):
            for word in _words(tech.get(key)):
                wanted |= _kinds_for_word(word)
    return wanted


def contract_kinds(draft: dict[str, Any] | None) -> frozenset[str]:
    """The kinds the session's input contract explicitly asks for (all, when it names none).

    Unlike ``allowed_kinds``, this does not silently add JSON to an audio or
    document contract — used to check whether a PoC test file is compatible
    with a new case (#253).
    """
    wanted = _wanted_kinds(draft)
    return frozenset(wanted) if wanted else ALL_KINDS


def allowed_kinds(draft: dict[str, Any] | None) -> frozenset[str]:
    """The kinds the session's input contract asks for, plus JSON (all, when it names none)."""
    wanted = _wanted_kinds(draft)
    if not wanted:
        return ALL_KINDS
    # JSON is how a package takes its settings next to the inputs the contract
    # names (an input bundle, a report spec, a query set), and a blueprint
    # rarely lists those as artifacts. It is checked as text like the rest.
    return frozenset(wanted | ALWAYS_ACCEPTED)


def describe(kinds: frozenset[str]) -> str:
    return ", ".join(KINDS[k].label for k in KINDS if k in kinds)


def accepted(kinds: frozenset[str]) -> list[dict[str, Any]]:
    """The accepted types as the upload form shows them: a label and its extensions."""
    kinds = kinds & ALL_KINDS or ALL_KINDS
    return [
        {"kind": key, "label": kind.label, "extensions": list(kind.extensions)}
        for key, kind in KINDS.items()
        if key in kinds
    ]


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

_M4A_BRANDS = {b"M4A ", b"M4B ", b"mp41", b"mp42", b"isom", b"iso2", b"dash", b"3gp4", b"3gp5"}


def _is_mp3(data: bytes) -> bool:
    if data.startswith(b"ID3"):
        return True
    # A bare MPEG audio frame: 11 sync bits, a layer that is not "reserved".
    return len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0 and bool(data[1] & 0x06)


def _sniff_binary(data: bytes) -> str | None:
    """The binary kind the content's signature names, or None."""
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if data.startswith((b"II*\x00", b"MM\x00*")):
        return "tiff"
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return "wav"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    if data[4:8] == b"ftyp" and data[8:12] in _M4A_BRANDS:
        return "m4a"
    if data.startswith((b"PK\x03\x04", b"PK\x05\x06")):
        return "zip"
    if _is_mp3(data):
        return "mp3"
    return None


#: Signatures of formats we never accept, so a renamed one is reported as a
#: mismatch instead of reaching the text check.
_OTHER_BINARY = (
    b"\x1f\x8b",  # gzip
    b"7z\xbc\xaf\x27\x1c",
    b"Rar!\x1a\x07",
    b"\x7fELF",
    b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",  # legacy office
)


def _zip_kind(data: bytes) -> str:
    """Bound and inspect a ZIP held in memory; return ``docx``/``xlsx`` or ``zip``.

    The entry count, every entry's path and the total size it unpacks to are
    checked before anything else opens it. The size is measured by inflating
    each entry here, in memory, and stopping at the bound, so an entry whose
    header understates its size is caught as well.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError, ValueError) as exc:
        raise InvalidInputError("the file is not a readable archive") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_ENTRIES:
            raise InvalidInputError(f"the archive has more than {MAX_ARCHIVE_ENTRIES} entries")
        names = set()
        declared = 0
        for info in infos:
            name = info.filename
            path = PurePosixPath(name.replace("\\", "/"))
            if (
                name.startswith(("/", "\\"))
                or (len(name) > 1 and name[1] == ":")
                or ".." in path.parts
            ):
                raise InvalidInputError("the archive has an entry outside its own folder")
            if info.flag_bits & 0x1:
                raise InvalidInputError("the archive has an encrypted entry")
            if name in names:
                raise InvalidInputError("the archive has a duplicate entry")
            names.add(name)
            declared += info.file_size
        limit_mb = MAX_ARCHIVE_UNCOMPRESSED_BYTES // (1024 * 1024)
        if declared > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
            raise InvalidInputError(f"the archive unpacks to more than {limit_mb} MB")
        total = 0
        try:
            for info in infos:
                if info.is_dir():
                    continue
                with archive.open(info) as fh:
                    while chunk := fh.read(_READ_CHUNK):
                        total += len(chunk)
                        if total > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                            raise InvalidInputError(
                                f"the archive unpacks to more than {limit_mb} MB"
                            )
        except InvalidInputError:
            raise
        except (zipfile.BadZipFile, OSError, ValueError, NotImplementedError, EOFError) as exc:
            raise InvalidInputError("the file is not a readable archive") from exc
        archive_types = b""
        if "[Content_Types].xml" in names:
            # Within the bound already measured above.
            archive_types = archive.read("[Content_Types].xml")
    if "[Content_Types].xml" in names and (
        any(_is_macro_part(name) for name in names) or _declares_macros(archive_types)
    ):
        raise UnsafeContentError(
            "files with macros are not accepted; save the document without macros"
        )
    if "[Content_Types].xml" in names and "word/document.xml" in names:
        return "docx"
    if "[Content_Types].xml" in names and "xl/workbook.xml" in names:
        return "xlsx"
    return "zip"


def _is_macro_part(name: str) -> bool:
    """A VBA project, or an ActiveX control's binary, inside an office file."""
    lowered = name.lower().replace("\\", "/")
    base = lowered.rsplit("/", 1)[-1]
    return base in {"vbaproject.bin", "vbadata.xml"} or (
        "/activex/" in f"/{lowered}" and base.endswith(".bin")
    )


def _declares_macros(content_types: bytes) -> bool:
    """``[Content_Types].xml`` names a macro-enabled document or a VBA part."""
    lowered = content_types.lower()
    return b"macroenabled" in lowered or b"vbaproject" in lowered


def _check_text(data: bytes, kind: str) -> None:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InvalidInputError(f"a {KINDS[kind].label} file must be UTF-8 text") from exc
    if "\x00" in text:
        raise InvalidInputError(f"a {KINDS[kind].label} file must be UTF-8 text")
    if kind == "json":
        try:
            json.loads(text)
        except ValueError as exc:
            raise InvalidInputError("the JSON file is not valid JSON") from exc


def check(filename: str, data: bytes, allowed: frozenset[str] = ALL_KINDS) -> str:
    """Return the file's kind, or raise if it is not one ``allowed`` accepts.

    The kind the extension names must be allowed, and the content must be that
    kind. Size bounds on the upload itself are the caller's (``read_upload``).
    """
    allowed = allowed & ALL_KINDS or ALL_KINDS
    accepted = f"accepted types: {describe(allowed)}"
    # The name rules first, so a name that tries to leave the input directory
    # is reported as that, whatever its extension.
    suffix = PurePosixPath(poc_service.safe_input_name(filename)).suffix.lower()
    kind = _BY_EXTENSION.get(suffix)
    if kind is None or kind not in allowed:
        raise UnsupportedInputError(f"this file type is not accepted here; {accepted}")
    if not data:
        raise poc_service.InputRejectedError("the file is empty")

    sniffed = _sniff_binary(data)
    # An archive is opened only where an office format is declared; any other
    # ZIP is a mismatch and is never looked inside.
    if sniffed == "zip" and kind in ZIP_KINDS:
        sniffed = _zip_kind(data)
    if kind in TEXT_KINDS:
        if sniffed is not None or data.startswith(_OTHER_BINARY):
            raise UnsupportedInputError(
                f"the file's content does not match its {suffix} extension; {accepted}"
            )
        _check_text(data, kind)
        return kind
    if sniffed != kind:
        raise UnsupportedInputError(
            f"the file's content does not match its {suffix} extension; {accepted}"
        )
    if kind == "pdf":
        try:
            pdf_content.check(data)
        except (pdf_content.ActiveContentError, pdf_content.TooComplexError) as exc:
            raise UnsafeContentError(str(exc)) from exc
    return kind
