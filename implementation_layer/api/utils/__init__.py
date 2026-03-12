"""Shared utilities for API endpoints."""

import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from fastapi import HTTPException, UploadFile

from implementation_layer.api.config import settings


def validate_upload(
    file: UploadFile,
    allowed_extensions: list[str],
) -> str:
    """Validate uploaded file has a filename and allowed extension.

    Returns the lowercase file extension.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {suffix}. Allowed: {allowed_extensions}",
        )
    return suffix


def validate_file_size(content: bytes) -> None:
    """Validate file content does not exceed MAX_FILE_SIZE_MB."""
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {settings.MAX_FILE_SIZE_MB}MB",
        )


@contextmanager
def temp_file(content: bytes, suffix: str) -> Generator[str, None, None]:
    """Context manager: write content to a temp file, yield its path, then clean up."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        yield tmp_path
    finally:
        Path(tmp_path).unlink(missing_ok=True)
