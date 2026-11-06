"""Check that a file's content matches the format its parser expects.

A file name's extension says what the caller believes the file is; the first
bytes say what it is. The parsers call this before they hand a file to the
underlying library, so a misnamed file fails with one clear error.
"""

from __future__ import annotations

_HEAD_BYTES = 1024
_ZIP_SIGNATURE = b"PK\x03\x04"


def _head(file_path: str) -> bytes:
    with open(file_path, "rb") as handle:
        return handle.read(_HEAD_BYTES)


def ensure_pdf_content(file_path: str) -> None:
    """Raise ValueError unless the file starts like a PDF.

    The ``%PDF-`` marker may be preceded by a few bytes, so it is searched for
    in the first kilobyte, the same tolerance PDF readers apply.
    """
    if b"%PDF-" not in _head(file_path):
        raise ValueError(f"The content of '{file_path}' is not a PDF document.")


def ensure_docx_content(file_path: str) -> None:
    """Raise ValueError unless the file starts like a DOCX (a ZIP container)."""
    if not _head(file_path).startswith(_ZIP_SIGNATURE):
        raise ValueError(f"The content of '{file_path}' is not a DOCX document.")
