"""Shared configuration utilities for the demo API."""

import os

from fastapi import HTTPException


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
