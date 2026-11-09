"""Does an uploaded file's content match the type its name says?

The routes choose a parser, a transcriber or a reader from the file name's
extension. The name is whatever the client sent, so before a file is written
to disk the route checks the content's leading signature against that
extension; for the ZIP-based office formats it also checks the archive holds
the part that format needs. Text formats (CSV, TXT, JSON, ...) are accepted
when they carry no binary signature and no NUL bytes; their encoding is the
reader's business.
"""

from __future__ import annotations

import io
import zipfile

# Extension -> the content family it must have.
_FAMILY_BY_EXTENSION = {
    ".pdf": "pdf",
    ".png": "png",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".gif": "gif",
    ".bmp": "bmp",
    ".tif": "tiff",
    ".tiff": "tiff",
    ".webp": "webp",
    ".wav": "wav",
    ".mp3": "mpeg_audio",
    ".aac": "mpeg_audio",
    ".m4a": "iso_media",
    ".mp4": "iso_media",
    ".mov": "iso_media",
    ".webm": "webm",
    ".ogg": "ogg",
    ".flac": "flac",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".xlsm": "xlsx",
    ".xls": "ole",
    ".parquet": "parquet",
    ".txt": "text",
    ".md": "text",
    ".markdown": "text",
    ".csv": "text",
    ".tsv": "text",
    ".json": "text",
}

# Leading atoms of an ISO base media file (MP4, M4A, MOV), at byte 4.
_ISO_ATOMS = (b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip")

# Signatures that are never text, so a renamed binary is not taken as CSV.
# Executables ("MZ") and Parquet ("PAR1") are left to the NUL check: both hold
# zero bytes early on, while a CSV may well start with a column named "MZ".
_BINARY_PREFIXES = (
    b"%PDF-",
    b"\x89PNG",
    b"\xff\xd8\xff",
    b"GIF8",
    b"PK\x03\x04",
    b"PK\x05\x06",
    b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
    b"\x1f\x8b",
    b"7z\xbc\xaf\x27\x1c",
    b"Rar!\x1a\x07",
    b"\x7fELF",
)

_TEXT_PROBE_BYTES = 64 * 1024


def _is_mpeg_audio(data: bytes) -> bool:
    if data.startswith(b"ID3"):
        return True
    # A bare MPEG audio frame has 11 sync bits, then a version (01 is reserved,
    # 00 is MPEG-2.5, common for low-rate voice) and a layer (00 is reserved).
    # An ADTS (AAC) frame has 12 sync bits and layer 00.
    if len(data) < 2 or data[0] != 0xFF or (data[1] & 0xE0) != 0xE0:
        return False
    version = (data[1] >> 3) & 0b11
    layer = (data[1] >> 1) & 0b11
    adts = (data[1] & 0xF0) == 0xF0 and layer == 0
    return adts or (version != 0b01 and layer != 0)


def _zip_names(data: bytes) -> set[str]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return set(archive.namelist())
    except (zipfile.BadZipFile, OSError, ValueError):
        return set()


def _matches(family: str, data: bytes) -> bool:
    if family == "pdf":
        # PDF readers accept a header within the first kilobyte.
        return b"%PDF-" in data[:1024]
    if family == "png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if family == "jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if family == "gif":
        return data.startswith((b"GIF87a", b"GIF89a"))
    if family == "bmp":
        return data.startswith(b"BM")
    if family == "tiff":
        return data.startswith((b"II*\x00", b"MM\x00*"))
    if family == "webp":
        return data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    if family == "wav":
        return data.startswith((b"RIFF", b"RF64")) and data[8:12] == b"WAVE"
    if family == "mpeg_audio":
        return _is_mpeg_audio(data)
    if family == "iso_media":
        return data[4:8] in _ISO_ATOMS
    if family == "webm":
        return data.startswith(b"\x1a\x45\xdf\xa3")
    if family == "ogg":
        return data.startswith(b"OggS")
    if family == "flac":
        return data.startswith(b"fLaC")
    if family == "ole":
        return data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    if family == "parquet":
        return data.startswith(b"PAR1") and data.endswith(b"PAR1")
    if family == "docx":
        names = _zip_names(data)
        return "[Content_Types].xml" in names and "word/document.xml" in names
    if family == "xlsx":
        names = _zip_names(data)
        return "[Content_Types].xml" in names and "xl/workbook.xml" in names
    if family == "text":
        head = data[:_TEXT_PROBE_BYTES]
        # Whitespace first does not make a binary text, and a PDF reader takes
        # a header anywhere in the first kilobyte (see "pdf" above).
        if head.lstrip(b" \t\r\n\f\v").startswith(_BINARY_PREFIXES) or b"%PDF-" in head[:1024]:
            return False
        return b"\x00" not in head
    return False


def content_mismatch(suffix: str, data: bytes) -> str | None:
    """None when ``data`` is what ``suffix`` says; else a message for the user.

    ``suffix`` is the lower-case extension the route already accepted. An
    extension this module does not know is reported, so a route that adds one
    has to add its signature here too.
    """
    family = _FAMILY_BY_EXTENSION.get(suffix.lower())
    if family is None:
        return f"Files of type {suffix} cannot be checked."
    if not data:
        return "The file is empty."
    if not _matches(family, data):
        return f"The file's content is not a {suffix} file."
    return None
