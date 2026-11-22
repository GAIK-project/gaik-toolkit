"""A file's type, read from the start of its content rather than from its name.

The parsers pick how to read a file from its extension. Before they read it,
they call :func:`check_file_type`, which reads the first bytes of the file and
refuses it with :class:`FileTypeMismatchError` when the content is not what the
extension says (a ZIP archive named ``.pdf``, a PDF named ``.png``) or not a
type the parser reads at all. Only the standard library is used, and PyMuPDF
when it is installed (see below)::

    from gaik.software_components.file_type import FileTypeMismatchError, detect_file_type

    detect_file_type("report.pdf")  # "pdf"

The detected types are ``"pdf"``, ``"docx"``, ``"xlsx"``, ``"pptx"``, ``"zip"``
(another ZIP archive), ``"ole"`` (a legacy Office .doc/.xls/.ppt file),
``"png"``, ``"jpeg"``, ``"gif"``, ``"webp"``, ``"tiff"``, ``"bmp"``,
``"text"``, ``"empty"`` and ``"unknown"`` (binary content of no listed type).

A PDF may start with other bytes before its ``%PDF-`` header, and PyMuPDF
repairs a PDF without one, so content of no recognised type in a ``.pdf`` file
is left to the parser, which reports a file it cannot read. When PyMuPDF is
installed, it is asked first: content it opens as another format (SVG, HTML,
XHTML, FB2 or plain text, which it reads too) is refused as no PDF.

An image extension (``.png``, ``.jpg``, ...) accepts any of the image types:
an image saved under another image extension is common, and the parsers take
the image's MIME type from its content.

Text is content without NUL bytes in its first 8 KiB, UTF-16 with a byte order
mark, or UTF-16 without one whose NUL bytes fall only on every other byte. Other
content with a NUL byte is ``"unknown"``. HEIC and AVIF images are ``"unknown"``
too: the parsers do not read them.

The check reads a bounded part of the file: its first 8 KiB and, for a ZIP
archive, the archive's directory only when that is at most a few MiB (a larger
one is read from the first entries instead). Callers check a file's size
against their input limits before they call it.
"""

from __future__ import annotations

import codecs
import struct
import zipfile
import zlib
from collections.abc import Collection
from pathlib import Path

__all__ = [
    "EXTENSION_TYPES",
    "FileTypeMismatchError",
    "check_file_type",
    "detect_file_type",
]

IMAGE_TYPES = frozenset({"png", "jpeg", "gif", "webp", "tiff", "bmp"})
TEXT_TYPES = frozenset({"text", "empty"})

EXTENSION_TYPES: dict[str, frozenset[str]] = {
    ".pdf": frozenset({"pdf"}),
    ".docx": frozenset({"docx"}),
    ".xlsx": frozenset({"xlsx"}),
    ".xlsm": frozenset({"xlsx"}),
    ".pptx": frozenset({"pptx"}),
    # A legacy name also holds its newer Office format: python-docx and Docling
    # read such a file by its content, as they did before this check.
    ".doc": frozenset({"ole", "docx"}),
    ".xls": frozenset({"ole", "xlsx"}),
    ".ppt": frozenset({"ole", "pptx"}),
    # The image's MIME type comes from its content, so any image type is read.
    ".png": IMAGE_TYPES,
    ".jpg": IMAGE_TYPES,
    ".jpeg": IMAGE_TYPES,
    ".gif": IMAGE_TYPES,
    ".webp": IMAGE_TYPES,
    ".tif": IMAGE_TYPES,
    ".tiff": IMAGE_TYPES,
    ".bmp": IMAGE_TYPES,
    ".txt": TEXT_TYPES,
    ".csv": TEXT_TYPES,
    ".md": TEXT_TYPES,
    ".markdown": TEXT_TYPES,
}
"""The content types each extension may hold."""

MIME_TYPES = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "tiff": "image/tiff",
    "bmp": "image/bmp",
}

_LABELS = {
    "pdf": "a PDF document",
    "docx": "a DOCX document",
    "xlsx": "an XLSX workbook",
    "pptx": "a PPTX presentation",
    "zip": "a ZIP archive",
    "ole": "a legacy Office document (.doc, .xls or .ppt)",
    "png": "a PNG image",
    "jpeg": "a JPEG image",
    "gif": "a GIF image",
    "webp": "a WebP image",
    "tiff": "a TIFF image",
    "bmp": "a BMP image",
    "text": "plain text",
    "empty": "an empty file",
    "unknown": "binary data of an unrecognised type",
}

# Content a PDF parser itself decides on (see the module docstring).
_LEFT_TO_PDF_PARSER = frozenset({"text", "empty", "unknown"})

_HEAD_BYTES = 8192
# [Content_Types].xml of a real Office file is a few KiB.
_MAX_CONTENT_TYPES_BYTES = 1024 * 1024
# The directory of a real Office file lists tens to a few thousand parts. A larger
# one is not loaded: zipfile.ZipFile builds an object for every entry it lists.
_MAX_ZIP_DIRECTORY_BYTES = 2 * 1024 * 1024
_MAX_ZIP_ENTRIES = 20_000
# How far the first entries of an archive are read when its directory is not.
_ZIP_HEAD_BYTES = 64 * 1024

_ZIP_READ_ERRORS = (
    zipfile.BadZipFile,
    OSError,
    RuntimeError,
    NotImplementedError,
    EOFError,
    zlib.error,
)

_END_RECORD = struct.Struct("<4s4H2LH")
_END_RECORD_64_LOCATOR = struct.Struct("<4sLQL")
_END_RECORD_64 = struct.Struct("<4sQ2H2L4Q")
_LOCAL_HEADER = struct.Struct("<4s2B4HL2L2H")

_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"II*\x00", "tiff"),
    (b"MM\x00*", "tiff"),
    # BigTIFF.
    (b"II+\x00", "tiff"),
    (b"MM\x00+", "tiff"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "ole"),
)

_OOXML_MAIN_PARTS = (
    ("word/document.xml", "wordprocessingml.document.main", "docx"),
    ("xl/workbook.xml", "spreadsheetml.sheet.main", "xlsx"),
    ("xl/workbook.xml", "ms-excel.sheet.macroEnabled.main", "xlsx"),
    ("ppt/presentation.xml", "presentationml.presentation.main", "pptx"),
)


class FileTypeMismatchError(ValueError):
    """A file's content is not the type its extension says, or not one the parser reads.

    It is a :class:`ValueError`, so code that already catches ``ValueError`` for
    a file it cannot use keeps working.

    Attributes:
        file_name: The file's name, without its directory.
        extension: The file's extension in lower case (``""`` when it has none).
        detected: The type read from the content (see :func:`detect_file_type`).
        expected: The types the extension or the parser allows.
    """

    def __init__(
        self,
        message: str,
        *,
        file_name: str,
        extension: str,
        detected: str,
        expected: Collection[str],
    ) -> None:
        super().__init__(message)
        self.file_name = file_name
        self.extension = extension
        self.detected = detected
        self.expected = tuple(sorted(expected))


def detect_file_type(path: str | Path) -> str:
    """Read the type of a file from its first bytes (and a ZIP's member list).

    Returns one of the types listed in this module's docstring.
    """
    path = Path(path)
    with path.open("rb") as handle:
        head = handle.read(_HEAD_BYTES)
    if not head:
        return "empty"
    for signature, kind in _SIGNATURES:
        if head.startswith(signature):
            return kind
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    # "BM", then the file size and four zero bytes: a text starting "BM" is no BMP.
    if head[:2] == b"BM" and head[6:10] == b"\x00\x00\x00\x00":
        return "bmp"
    if head.lstrip(b" \t\r\n\f\x00").startswith(b"%PDF-"):
        return "pdf"
    # is_zipfile finds the archive's directory at the end of the file, as
    # python-docx and openpyxl do, so bytes before the archive do not hide it.
    if zipfile.is_zipfile(path):
        return _zip_type(path)
    if head.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" not in head:
        return "text"
    if _looks_like_utf16(head):
        return "text"
    return "unknown"


def _looks_like_utf16(head: bytes) -> bool:
    """UTF-16 text without a byte order mark: NUL bytes on one parity only."""
    return _utf16_codec(head) is not None


def _utf16_codec(head: bytes) -> str | None:
    """``"utf-16-le"`` or ``"utf-16-be"`` for UTF-16 text without a byte order mark.

    Text in a Latin script has a NUL high byte in most characters, so at least a
    quarter of the bytes are NUL and every one of them falls on the same parity.
    None for other content.
    """
    sample = head[: len(head) // 2 * 2]
    if len(sample) < 4:
        return None
    even, odd = sample[0::2], sample[1::2]
    for zeros, other, codec in ((odd, even, "utf-16-le"), (even, odd, "utf-16-be")):
        if b"\x00" in other or zeros.count(0) * 2 < len(zeros):
            continue
        try:
            # The sample may end inside a character or a surrogate pair; a
            # decoder that is not final keeps those bytes pending.
            codecs.getincrementaldecoder(codec)().decode(sample, final=False)
        except UnicodeDecodeError:
            return None
        return codec
    return None


def _zip_type(path: Path) -> str:
    directory = _zip_directory_size(path)
    if directory is None:
        return _zip_type_from_first_entries(path)
    content_types = ""
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            try:
                info = archive.getinfo("[Content_Types].xml")
            except KeyError:
                info = None
            if info is not None and info.file_size <= _MAX_CONTENT_TYPES_BYTES:
                try:
                    content_types = _xml_text(archive.read(info))
                except _ZIP_READ_ERRORS:
                    # A part that cannot be unpacked leaves the member names to
                    # decide; the parser reports the damaged part.
                    pass
    except _ZIP_READ_ERRORS:
        return "zip"
    for member, content_type, kind in _OOXML_MAIN_PARTS:
        if member in names or content_type in content_types:
            return kind
    return "zip"


def _xml_text(data: bytes) -> str:
    """An XML part as text: UTF-8, or UTF-16 with or without a byte order mark."""
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        codec = "utf-16"
    elif data.startswith(b"<\x00"):
        codec = "utf-16-le"
    elif data.startswith(b"\x00<"):
        codec = "utf-16-be"
    else:
        codec = "utf-8"
    return data.decode(codec, "replace")


def _zip_directory_size(path: Path) -> tuple[int, int] | None:
    """The entry count and byte size of a ZIP archive's directory, from its end record.

    ``None`` when either is over the caps above, or the end record cannot be read;
    the archive's directory is then not loaded.
    """
    size = path.stat().st_size
    tail_size = min(size, _END_RECORD.size + 0xFFFF)
    with path.open("rb") as handle:
        handle.seek(size - tail_size)
        tail = handle.read(tail_size)
        at = tail.rfind(b"PK\x05\x06")
        if at < 0 or len(tail) - at < _END_RECORD.size:
            return None
        fields = _END_RECORD.unpack_from(tail, at)
        entries, directory = fields[4], fields[5]
        if entries == 0xFFFF or directory == 0xFFFFFFFF or fields[6] == 0xFFFFFFFF:
            # A ZIP64 archive: its counts are in the ZIP64 end record before this one.
            locator_at = size - tail_size + at - _END_RECORD_64_LOCATOR.size
            record_at = locator_at - _END_RECORD_64.size
            if record_at < 0:
                return None
            handle.seek(record_at)
            data = handle.read(_END_RECORD_64.size + _END_RECORD_64_LOCATOR.size)
            if len(data) < _END_RECORD_64.size or data[:4] != b"PK\x06\x06":
                return None
            record = _END_RECORD_64.unpack_from(data)
            entries, directory = record[7], record[8]
    if entries > _MAX_ZIP_ENTRIES or directory > _MAX_ZIP_DIRECTORY_BYTES:
        return None
    return entries, directory


def _zip_type_from_first_entries(path: Path) -> str:
    """The Office type named by the entries in the first bytes of an archive.

    For an archive whose directory is not loaded: the entry headers in its first
    64 KiB are read, where an Office application writes the main part.
    """
    with path.open("rb") as handle:
        head = handle.read(_ZIP_HEAD_BYTES)
    names = set()
    at = head.find(b"PK\x03\x04")
    while 0 <= at <= len(head) - _LOCAL_HEADER.size:
        name_length = _LOCAL_HEADER.unpack_from(head, at)[10]
        start = at + _LOCAL_HEADER.size
        names.add(head[start : start + name_length].decode("utf-8", "replace"))
        at = head.find(b"PK\x03\x04", start)
    for member, _content_type, kind in _OOXML_MAIN_PARTS:
        if member in names:
            return kind
    return "zip"


def _mupdf_opens_as_pdf(path: Path) -> bool | None:
    """Whether PyMuPDF opens the file as a PDF.

    ``None`` when PyMuPDF is not installed or cannot open the file at all; the
    PDF parser then reports what it cannot read.
    """
    try:
        import pymupdf
    except ImportError:
        return None
    try:
        with pymupdf.open(path) as document:
            return bool(document.is_pdf)
    except Exception:
        return None


def _either(types: Collection[str]) -> str:
    if frozenset(types) == IMAGE_TYPES:
        return "an image (PNG, JPEG, GIF, WebP, TIFF or BMP)"
    return " or ".join(_LABELS.get(kind, kind) for kind in sorted(types))


def check_file_type(path: str | Path, accepted: Collection[str] | None = None) -> str:
    """Refuse a file whose content does not match its extension or ``accepted``.

    Args:
        path: The file to check.
        accepted: The content types the caller reads. ``None`` accepts what the
            extension says (:data:`EXTENSION_TYPES`); a file with an extension
            not listed there is then not checked.

    Returns:
        The detected type.

    Raises:
        FileTypeMismatchError: When the content is a known type other than the
            extension's, or not one of ``accepted``. The message names the
            file, the extension and the detected type.
    """
    path = Path(path)
    extension = path.suffix.lower()
    detected = detect_file_type(path)
    by_extension = EXTENSION_TYPES.get(extension)

    def refuse(expected: Collection[str], says: str) -> FileTypeMismatchError:
        return FileTypeMismatchError(
            f"The content of '{path.name}' is {_LABELS[detected]}, not {_either(expected)}{says}.",
            file_name=path.name,
            extension=extension,
            detected=detected,
            expected=expected,
        )

    opened_as_pdf: list[bool | None] = []

    def fits(expected: Collection[str]) -> bool:
        if detected in expected:
            return True
        if "pdf" not in expected or detected not in _LEFT_TO_PDF_PARSER:
            return False
        if not opened_as_pdf:
            opened_as_pdf.append(_mupdf_opens_as_pdf(path))
        return opened_as_pdf[0] is not False

    if by_extension is not None and not fits(by_extension):
        raise refuse(by_extension, f" as its extension {extension} says")
    if accepted is not None and not fits(accepted):
        raise refuse(accepted, "")
    return detected
