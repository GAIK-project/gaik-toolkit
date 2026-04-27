"""Provider-aware configuration loader.

Returns a single dict that is a superset of the legacy ``get_openai_config()``
shape: it always carries ``provider`` and ``model`` and adds provider-specific
keys (``api_key``, ``azure_endpoint``, ``project_id`` …). Legacy callers that
only read ``use_azure``/``api_key`` keep working.
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

from gaik.software_components.llm.providers import Provider, resolve_provider

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} not found in environment")
    return value.strip()


def _embedding_model_default(provider: str) -> str:
    if provider in (Provider.OPENAI.value, Provider.AZURE.value):
        return os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    if provider in (Provider.GOOGLE.value, Provider.VERTEX.value):
        return os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
    return os.getenv("EMBEDDING_MODEL", "")


def get_llm_config(
    provider: str | None = None,
    **overrides: Any,
) -> dict:
    """Build a config dict for the chosen provider.

    Examples:
        >>> get_llm_config()                       # uses LLM_PROVIDER or azure
        >>> get_llm_config("anthropic")            # explicit
        >>> get_llm_config("google", model="gemini-2.0-flash")
    """
    name = resolve_provider(provider)
    if name == Provider.OPENAI.value:
        config = _openai_config()
    elif name == Provider.AZURE.value:
        config = _azure_config()
    elif name == Provider.ANTHROPIC.value:
        config = _anthropic_config()
    elif name == Provider.ANTHROPIC_FOUNDRY.value:
        config = _anthropic_foundry_config()
    elif name == Provider.GOOGLE.value:
        config = _google_config()
    elif name == Provider.VERTEX.value:
        config = _vertex_config()
    else:
        raise ValueError(f"Unsupported provider: {name}")
    config.update(overrides)
    return config


def _openai_config() -> dict:
    return {
        "provider": Provider.OPENAI.value,
        "use_azure": False,
        "api_key": _require("OPENAI_API_KEY"),
        "model": os.getenv("OPENAI_MODEL", "gpt-5.4-2026-03-05"),
        "transcription_model": os.getenv("OPENAI_TRANSCRIPTION_MODEL", "gpt-4o-transcribe"),
        "embedding_model": _embedding_model_default(Provider.OPENAI.value),
    }


def _azure_config() -> dict:
    endpoint = _require("AZURE_ENDPOINT")
    return {
        "provider": Provider.AZURE.value,
        "use_azure": True,
        "api_key": _require("AZURE_API_KEY"),
        "azure_endpoint": endpoint,
        "azure_audio_endpoint": endpoint,
        "api_version": os.getenv("AZURE_API_VERSION", "2025-03-01-preview"),
        "model": os.getenv("AZURE_DEPLOYMENT", "gpt-5.4"),
        "transcription_model": os.getenv("AZURE_TRANSCRIPTION_MODEL", "gpt-4o-transcribe"),
        "embedding_model": _embedding_model_default(Provider.AZURE.value),
    }


def _anthropic_config() -> dict:
    return {
        "provider": Provider.ANTHROPIC.value,
        "api_key": _require("ANTHROPIC_API_KEY"),
        "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        "max_tokens": int(os.getenv("ANTHROPIC_MAX_TOKENS", "4096")),
    }


def _anthropic_foundry_config() -> dict:
    return {
        "provider": Provider.ANTHROPIC_FOUNDRY.value,
        "api_key": _require("AZURE_API_KEY"),
        "resource": _require("ANTHROPIC_FOUNDRY_RESOURCE"),
        "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        "max_tokens": int(os.getenv("ANTHROPIC_MAX_TOKENS", "4096")),
    }


def _google_config() -> dict:
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY (or GEMINI_API_KEY) not found in environment")
    return {
        "provider": Provider.GOOGLE.value,
        "api_key": api_key.strip(),
        "model": os.getenv("GOOGLE_MODEL", "gemini-2.5-flash"),
        "embedding_model": _embedding_model_default(Provider.GOOGLE.value),
    }


def _vertex_config() -> dict:
    return {
        "provider": Provider.VERTEX.value,
        "project_id": _require("GOOGLE_PROJECT_ID"),
        "service_account_json": _require("GOOGLE_SERVICE_ACCOUNT_JSON"),
        "scopes": [
            scope.strip()
            for scope in _require("GOOGLE_SCOPES").split(",")
            if scope.strip()
        ],
        "generate_content_url": _require("GOOGLE_GENERATE_CONTENT_URL"),
        "model": os.getenv("GOOGLE_MODEL", "gemini-2.5-flash"),
        "embedding_model": _embedding_model_default(Provider.VERTEX.value),
    }
