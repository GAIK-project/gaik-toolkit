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
    """
    Get OpenAI configuration from environment variables.

    Checks for either Azure or standard OpenAI API keys and returns
    the appropriate configuration.

    Raises:
        HTTPException: If neither AZURE_API_KEY nor OPENAI_API_KEY is set.
    """
    use_azure = bool(os.getenv("AZURE_API_KEY"))
    if not use_azure and not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="Either AZURE_API_KEY or OPENAI_API_KEY environment variable must be set",
        )

    from gaik.software_components.config import get_openai_config

    return get_openai_config(use_azure=use_azure)


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
