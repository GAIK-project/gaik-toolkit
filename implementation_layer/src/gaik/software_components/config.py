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
        azure_endpoint = os.getenv("AZURE_ENDPOINT")
        return {
            "use_azure": True,
            "api_key": os.getenv("AZURE_API_KEY"),
            "azure_endpoint": azure_endpoint,
            "azure_audio_endpoint": azure_endpoint,
            "api_version": os.getenv("AZURE_API_VERSION", "2025-03-01-preview"),
            "model": os.getenv("AZURE_DEPLOYMENT", "gpt-6-luna"),
            "transcription_model": os.getenv("AZURE_TRANSCRIPTION_MODEL", "gpt-4o-transcribe"),
        }
    else:
        return {
            "use_azure": False,
            "api_key": os.getenv("OPENAI_API_KEY"),
            "base_url": os.getenv("OPENAI_BASE_URL"),
            "model": os.getenv("OPENAI_MODEL", "gpt-6-luna"),
            "transcription_model": os.getenv("OPENAI_TRANSCRIPTION_MODEL", "gpt-4o-transcribe"),
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
    # Import lazily: llm.factory also imports this legacy helper.
    from gaik.software_components.llm.providers import Provider, resolve_provider

    # A bare legacy client config has always meant standard OpenAI. Provider-aware
    # factories resolve their defaults first and pass an explicit provider here.
    name = resolve_provider(config={"use_azure": False, **config})
    options = {
        key: config[key] for key in ("timeout", "max_retries", "http_client") if key in config
    }
    if name == Provider.AZURE.value:
        options["api_version"] = config["api_version"]
        if config.get("base_url"):
            options["base_url"] = config["base_url"]
        else:
            options["azure_endpoint"] = config["azure_endpoint"]
        return AzureOpenAI(api_key=config["api_key"], **options)
    if name not in {
        Provider.OPENAI.value,
        Provider.OPENAI_COMPATIBLE.value,
        Provider.AITTA.value,
    }:
        raise ValueError(f"create_openai_client does not support provider={name!r}")
    if name == Provider.OPENAI_COMPATIBLE.value:
        for field in ("base_url", "model"):
            if not config.get(field):
                raise ValueError(f"openai_compatible requires an explicit {field!r}")
    if config.get("base_url"):
        options["base_url"] = config["base_url"]
    elif name == Provider.AITTA.value:
        options["base_url"] = "https://aitta-api.csc.fi/openai/v1"
    if name == Provider.AITTA.value:
        options.setdefault("timeout", 600.0)
    return OpenAI(api_key=config["api_key"], **options)
