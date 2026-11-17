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


def file_tag(name: str | PurePath | None) -> str:
    """``"upload 3f9a1c2b.pdf"`` for a file name or path; ``"upload"`` without one."""
    if not name:
        return "upload"
    text = str(name)
    suffix = PurePath(text).suffix.lower()
    if not suffix[1:].isalnum() or len(suffix) > 6:
        suffix = ""
    digest = hashlib.blake2b(text.encode("utf-8", "replace"), key=_SALT, digest_size=4)
    return f"upload {digest.hexdigest()}{suffix}"
