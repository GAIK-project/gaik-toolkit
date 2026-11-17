"""A file's type, read from the start of its content rather than from its name.

The parsers pick how to read a file from its extension. Before they read it,
they call :func:`check_file_type`, which reads the first bytes of the file and
refuses it with :class:`FileTypeMismatchError` when the content is not what the
extension says (a ZIP archive named ``.pdf``, a PDF named ``.png``) or not a
type the parser reads at all. Only the standard library is used::

    from gaik.software_components.file_type import FileTypeMismatchError, detect_file_type

    detect_file_type("report.pdf")  # "pdf"

The detected types are ``"pdf"``, ``"docx"``, ``"xlsx"``, ``"pptx"``, ``"zip"``
(another ZIP archive), ``"ole"`` (a legacy Office .doc/.xls/.ppt file),
``"png"``, ``"jpeg"``, ``"gif"``, ``"webp"``, ``"tiff"``, ``"bmp"``,
``"text"``, ``"empty"`` and ``"unknown"`` (binary content of no listed type).

A PDF may start with other bytes before its ``%PDF-`` header, and PyMuPDF
repairs a PDF without one, so content of no recognised type in a ``.pdf`` file
is left to the parser, which reports a file it cannot read.
"""

from __future__ import annotations

import zipfile
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
    ".png": frozenset({"png"}),
    ".jpg": frozenset({"jpeg"}),
    ".jpeg": frozenset({"jpeg"}),
    ".gif": frozenset({"gif"}),
    ".webp": frozenset({"webp"}),
    ".tif": frozenset({"tiff"}),
    ".tiff": frozenset({"tiff"}),
    ".bmp": frozenset({"bmp"}),
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

_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"II*\x00", "tiff"),
    (b"MM\x00*", "tiff"),
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
    return "unknown"


def _zip_type(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            content_types = ""
            try:
                info = archive.getinfo("[Content_Types].xml")
            except KeyError:
                info = None
            if info is not None and info.file_size <= _MAX_CONTENT_TYPES_BYTES:
                content_types = archive.read(info).decode("utf-8", "replace")
    except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError):
        return "zip"
    for member, content_type, kind in _OOXML_MAIN_PARTS:
        if member in names or content_type in content_types:
            return kind
    return "zip"


def _either(types: Collection[str]) -> str:
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

    def fits(expected: Collection[str]) -> bool:
        if detected in expected:
            return True
        return "pdf" in expected and detected in _LEFT_TO_PDF_PARSER

    if by_extension is not None and not fits(by_extension):
        raise refuse(by_extension, f" as its extension {extension} says")
    if accepted is not None and not fits(accepted):
        raise refuse(accepted, "")
    return detected
