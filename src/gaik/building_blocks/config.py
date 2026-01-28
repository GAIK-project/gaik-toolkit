"""
Shared API configuration for OpenAI and Azure OpenAI.

This module provides reusable configuration utilities for creating
OpenAI/Azure OpenAI clients across different extraction modules.
"""

import os

from dotenv import load_dotenv
from openai import AzureOpenAI, OpenAI

# Load environment variables
load_dotenv()


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
    if use_azure:
        azure_endpoint = os.getenv("AZURE_ENDPOINT", "https://haagahelia-poc-gaik.openai.azure.com/")
        return {
            "use_azure": True,
            "api_key": os.getenv("AZURE_API_KEY"),
            "azure_endpoint": azure_endpoint,
            "azure_audio_endpoint": azure_endpoint,
            "api_version": os.getenv("AZURE_API_VERSION", "2025-03-01-preview"),
            "model": os.getenv("AZURE_DEPLOYMENT", "gpt-5.1"),
            "transcription_model": os.getenv("AZURE_TRANSCRIPTION_MODEL", "whisper"),
        }
    else:
        return {
            "use_azure": False,
            "api_key": os.getenv("OPENAI_API_KEY"),
            "model": os.getenv("OPENAI_MODEL", "gpt-5.1-2025-11-13"),
            "transcription_model": os.getenv("OPENAI_TRANSCRIPTION_MODEL", "whisper-1"),
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
