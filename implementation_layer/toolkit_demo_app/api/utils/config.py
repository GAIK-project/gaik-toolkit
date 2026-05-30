"""Shared configuration utilities for the demo API."""

import os

import fitz
from fastapi import HTTPException, UploadFile

# File size limits
MAX_FILE_SIZE_MB = 20
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Vision parser page limit (CPU environment in CSC Rahti)
MAX_VISION_PAGES = 10


async def validate_file_size(file: UploadFile) -> bytes:
    """Validate file size and return content if valid."""
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB",
        )
    await file.seek(0)
    return content


def get_api_config():
    """Get Azure OpenAI configuration from environment variables.

    Raises:
        HTTPException: If AZURE_API_KEY is not set.
    """
    if not os.getenv("AZURE_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="AZURE_API_KEY environment variable must be set",
        )

    from gaik.software_components.config import get_openai_config

    return get_openai_config(use_azure=True)


def validate_vision_page_limit(file_path: str, suffix: str, parser_type: str) -> None:
    """Raise HTTPException if a vision parser PDF exceeds the page limit."""
    if parser_type not in {"vision", "vision_plus"} or suffix != ".pdf":
        return

    with fitz.open(file_path) as document:
        page_count = document.page_count

    if page_count > MAX_VISION_PAGES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{parser_type} parser supports at most {MAX_VISION_PAGES} pages per PDF. "
                f"Received {page_count} pages."
            ),
        )
