"""Name a file in a log line without its path or name.

A file name can carry personal data (``Matti_Virtanen_lab_results.pdf``), and so can the
folders above it. Log lines and progress prints name a file by :func:`file_tag` instead:
its extension and a short tag that is the same for the same path within one process, so
the lines about one file can still be followed, but the name cannot be read back. The
salt is new in every process.

Exceptions raised to the caller keep the path: the caller passed it in and needs it.
"""

from __future__ import annotations

import hashlib
import secrets
from pathlib import PurePath

_SALT = secrets.token_bytes(16)

# Only a known file type is kept as the extension: anything else after the last dot can
# be part of the name ("Virtanen.Matti").
_KNOWN_EXTENSIONS = frozenset(
    ".pdf .docx .doc .xlsx .xls .xlsm .csv .tsv .txt .md .json .xml .html .htm .pptx .odt "
    ".ods .rtf .png .jpg .jpeg .gif .webp .tif .tiff .bmp .heic .mp3 .wav .m4a .ogg .flac "
    ".webm .mp4 .mpeg .mpga .mov .mkv .avi .zip .eml .msg .bpmn .parquet".split()
)


def file_tag(path: str | PurePath | None) -> str:
    """``"file 3f9a1c2b.pdf"`` for a file name or path; ``"file"`` without one."""
    if not path:
        return "file"
    text = str(path)
    suffix = PurePath(text).suffix.lower()
    if suffix not in _KNOWN_EXTENSIONS:
        suffix = ""
    digest = hashlib.blake2b(text.encode("utf-8", "replace"), key=_SALT, digest_size=4)
    return f"file {digest.hexdigest()}{suffix}"
