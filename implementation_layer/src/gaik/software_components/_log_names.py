"""Name a file in a log line without its path or name.

A file name can carry personal data (``Matti_Virtanen_lab_results.pdf``), and so can the
folders above it. Log lines and progress prints name a file by :func:`file_tag` instead:
its extension and a short tag that is the same for the same path within one process, so
the lines about one file can still be followed, but the name cannot be read back. The
salt comes from ``GAIK_LOG_TAG_SALT`` when it is set, so tags match across a
deployment's processes and restarts; otherwise it is new in every process.

Exceptions raised to the caller keep the path: the caller passed it in and needs it.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import PurePath

# blake2b takes a key of at most 64 bytes, so a set salt of any length is hashed to 32.
_SALT = (
    hashlib.sha256(os.environ["GAIK_LOG_TAG_SALT"].encode("utf-8")).digest()
    if os.environ.get("GAIK_LOG_TAG_SALT")
    else secrets.token_bytes(16)
)

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


def error_text(exc: BaseException, *paths: str | PurePath | None, limit: int = 300) -> str:
    """``"ValueError: cannot open file 3f9a1c2b.pdf"``: the error with each path's text,
    file name and stem replaced by its tag, so a log line keeps the cause."""
    text = f"{type(exc).__name__}: {exc}"
    for path in paths:
        if not path:
            continue
        tag = file_tag(path)
        whole = str(path)
        pure = PurePath(whole)
        # An OSError's repr doubles a Windows path's backslashes; tag that form too.
        forms = {whole, whole.replace("\\", "\\\\"), pure.name, pure.stem}
        for part in sorted(forms, key=len, reverse=True):
            if len(part) >= 3:
                text = text.replace(part, tag)
    return text if len(text) <= limit else text[: limit - 1] + "…"
