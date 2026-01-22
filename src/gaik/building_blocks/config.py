"""
Shared API configuration for OpenAI and Azure OpenAI.

This module provides reusable configuration utilities for creating
OpenAI/Azure OpenAI clients across different extraction modules.
"""

from functools import lru_cache

from openai import AzureOpenAI, OpenAI
from pydantic_settings import BaseSettings


class OpenAISettings(BaseSettings):
    """OpenAI/Azure configuration from environment variables."""

    # Azure settings
    AZURE_API_KEY: str | None = None
    AZURE_ENDPOINT: str = "https://haagahelia-poc-gaik.openai.azure.com/"
    AZURE_API_VERSION: str = "2025-03-01-preview"
    AZURE_DEPLOYMENT: str = "gpt-5.1"
    AZURE_TRANSCRIPTION_MODEL: str = "whisper"

    # OpenAI settings
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-5.1-2025-11-13"
    OPENAI_TRANSCRIPTION_MODEL: str = "whisper-1"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> OpenAISettings:
    """Get cached settings singleton."""
    return OpenAISettings()


def get_openai_config(use_azure: bool = True) -> dict:
    """
    Get OpenAI configuration based on whether to use Azure or standard OpenAI.

    Args:
        use_azure: If True, use Azure OpenAI. If False, use standard OpenAI API.

    Returns:
        Configuration dictionary with appropriate settings

    Example:
        >>> config = get_openai_config(use_azure=True)
        >>> # Returns Azure config with deployment name
        >>> config = get_openai_config(use_azure=False)
        >>> # Returns OpenAI config with model name
    """
    settings = get_settings()

    if use_azure:
        return {
            "use_azure": True,
            "api_key": settings.AZURE_API_KEY,
            "azure_endpoint": settings.AZURE_ENDPOINT,
            "azure_audio_endpoint": settings.AZURE_ENDPOINT,
            "api_version": settings.AZURE_API_VERSION,
            "model": settings.AZURE_DEPLOYMENT,
            "transcription_model": settings.AZURE_TRANSCRIPTION_MODEL,
        }

    return {
        "use_azure": False,
        "api_key": settings.OPENAI_API_KEY,
        "model": settings.OPENAI_MODEL,
        "transcription_model": settings.OPENAI_TRANSCRIPTION_MODEL,
    }


def create_openai_client(config: dict):
    """
    Create an OpenAI or Azure OpenAI client based on configuration.

    Args:
        config: Configuration dictionary from get_openai_config()

    Returns:
        OpenAI or AzureOpenAI client instance

    Example:
        >>> config = get_openai_config(use_azure=True)
        >>> client = create_openai_client(config)
    """
    if config.get("use_azure", False):
        return AzureOpenAI(
            api_key=config["api_key"],
            api_version=config["api_version"],
            azure_endpoint=config["azure_endpoint"],
        )
    else:
        return OpenAI(api_key=config["api_key"])
