"""Shared utilities for API endpoints."""

import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from fastapi import HTTPException, UploadFile

from api.config import settings


def validate_upload(
    file: UploadFile,
    allowed_extensions: list[str],
) -> str:
    """
    Validate uploaded file has a filename and allowed extension.

    Args:
        file: The uploaded file
        allowed_extensions: List of allowed file extensions (e.g., [".pdf", ".docx"])

    Returns:
        The lowercase file extension

    Raises:
        HTTPException: If filename is missing or extension not allowed
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
    """
    Validate file content does not exceed size limit.

    Args:
        content: The file content bytes

    Raises:
        HTTPException: If file exceeds MAX_FILE_SIZE_MB
    """
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {settings.MAX_FILE_SIZE_MB}MB",
        )


@contextmanager
def temp_file(content: bytes, suffix: str) -> Generator[str, None, None]:
    """
    Context manager for temporary file handling with automatic cleanup.

    Args:
        content: File content to write
        suffix: File extension (e.g., ".pdf")

    Yields:
        Path to the temporary file
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        yield tmp_path
    finally:
        Path(tmp_path).unlink(missing_ok=True)
