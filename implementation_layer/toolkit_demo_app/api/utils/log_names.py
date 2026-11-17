"""File names stay out of the logs.

A file name a user uploads can carry personal data (``Matti_Virtanen_lab_results.pdf``),
and the logs go to the cluster's log store and to everyone with access to the project.
Log lines name an upload by :func:`file_tag` instead: its extension and a short tag that
is the same for the same name within one process, so the lines of one upload can still
be followed, but the name cannot be read back. The salt is new in every process.
"""

from __future__ import annotations

import hashlib
import secrets
from pathlib import PurePath

_SALT = secrets.token_bytes(16)

# Only a known file type is kept as the extension: anything else after the last dot can
# be part of the name ("Virtanen.Matti").
_KNOWN_EXTENSIONS = frozenset(
    ".pdf .docx .doc .xlsx .xls .csv .tsv .txt .md .json .xml .html .htm .pptx .odt .ods "
    ".rtf .png .jpg .jpeg .gif .webp .tif .tiff .bmp .heic .mp3 .wav .m4a .ogg .flac "
    ".webm .mp4 .mpeg .mpga .mov .zip .eml .msg .bpmn".split()
)


def file_tag(name: str | PurePath | None) -> str:
    """``"upload 3f9a1c2b.pdf"`` for a file name or path; ``"upload"`` without one."""
    if not name:
        return "upload"
    text = str(name)
    suffix = PurePath(text).suffix.lower()
    if suffix not in _KNOWN_EXTENSIONS:
        suffix = ""
    digest = hashlib.blake2b(text.encode("utf-8", "replace"), key=_SALT, digest_size=4)
    return f"upload {digest.hexdigest()}{suffix}"


def error_kind(exc: BaseException) -> str:
    """What failed, without the message: the exception type and an HTTP status if any.

    The message can repeat an upload's name or its content; the status is what an
    operator needs to tell a wrong password (401) from a service that is down (503).
    """
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None) or getattr(exc, "status_code", None)
    return (
        f"{type(exc).__name__} (HTTP {status})" if isinstance(status, int) else type(exc).__name__
    )
