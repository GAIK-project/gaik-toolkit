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


def _env(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return default


_REQUIRED_FIELDS = {
    Provider.OPENAI.value: {"api_key": "OPENAI_API_KEY"},
    Provider.AZURE.value: {"api_key": "AZURE_API_KEY", "azure_endpoint": "AZURE_ENDPOINT"},
    Provider.AITTA.value: {"api_key": "AITTA_API_KEY (or AITTA_API_TOKEN / AITTA_TOKEN)"},
    Provider.OPENAI_COMPATIBLE.value: {
        "api_key": "OPENAI_API_KEY",
        "base_url": "OPENAI_BASE_URL",
        "model": "OPENAI_MODEL",
    },
    Provider.ANTHROPIC.value: {"api_key": "ANTHROPIC_API_KEY"},
    Provider.ANTHROPIC_FOUNDRY.value: {
        "api_key": "ANTHROPIC_FOUNDRY_API_KEY (or AZURE_API_KEY)",
        "resource": "ANTHROPIC_FOUNDRY_RESOURCE",
    },
    Provider.GOOGLE.value: {"api_key": "GOOGLE_API_KEY (or GEMINI_API_KEY)"},
    Provider.VERTEX.value: {
        "project_id": "GOOGLE_PROJECT_ID (or GOOGLE_CLOUD_PROJECT)",
    },
    Provider.LITELLM.value: {"model": "LITELLM_MODEL (provider-prefixed model ID)"},
}


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

    Explicit keyword overrides are applied before required-field validation, so
    credentials and endpoints can be supplied without setting environment variables.
    Aitta uses its OpenAI-compatible API with a 600-second cold-start timeout.
    Other compatible servers require their own ``base_url`` and ``model``.
    """
    name = resolve_provider(provider)
    if name == Provider.OPENAI.value:
        config = _openai_config()
    elif name == Provider.OPENAI_COMPATIBLE.value:
        config = _compatible_config()
    elif name == Provider.AITTA.value:
        config = _aitta_config()
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
    elif name == Provider.LITELLM.value:
        config = {
            "model": _env("LITELLM_MODEL"),
            "api_key": _env("LITELLM_API_KEY"),
            "base_url": _env("LITELLM_BASE_URL"),
            "api_version": _env("LITELLM_API_VERSION"),
            "embedding_model": _env("LITELLM_EMBEDDING_MODEL", default=""),
        }
    else:
        raise ValueError(f"Unsupported provider: {name}")
    config.update(overrides)
    config["provider"] = name
    config["use_azure"] = name == Provider.AZURE.value
    if name == Provider.AZURE.value and "azure_audio_endpoint" not in overrides:
        config["azure_audio_endpoint"] = config["azure_endpoint"]
    for field, env_name in _REQUIRED_FIELDS[name].items():
        if field == "azure_endpoint" and config.get("base_url"):
            continue
        value = config.get(field)
        if isinstance(value, str):
            value = value.strip()
            config[field] = value
        if not value:
            raise ValueError(f"{env_name} not found in environment; provide {field!r} explicitly")
    return config


def _openai_config() -> dict:
    return {
        "provider": Provider.OPENAI.value,
        "use_azure": False,
        "api_key": _env("OPENAI_API_KEY"),
        "base_url": _env("OPENAI_BASE_URL"),
        "model": os.getenv("OPENAI_MODEL", "gpt-6-luna"),
        "transcription_model": os.getenv("OPENAI_TRANSCRIPTION_MODEL", "gpt-4o-transcribe"),
        "embedding_model": _embedding_model_default(Provider.OPENAI.value),
    }


def _compatible_config() -> dict:
    return {
        "provider": Provider.OPENAI_COMPATIBLE.value,
        "api_key": _env("OPENAI_API_KEY"),
        "base_url": _env("OPENAI_BASE_URL"),
        "model": _env("OPENAI_MODEL"),
        "embedding_model": _env("EMBEDDING_MODEL", default=""),
    }


def _aitta_config() -> dict:
    return {
        "provider": Provider.AITTA.value,
        "api_key": _env("AITTA_API_KEY", "AITTA_API_TOKEN", "AITTA_TOKEN"),
        "base_url": _env("AITTA_BASE_URL", default="https://aitta-api.csc.fi/openai/v1"),
        "model": _env("AITTA_MODEL", default="google/gemma-4-31b-it"),
        "embedding_model": _env("AITTA_EMBEDDING_MODEL", default=""),
        "timeout": 600.0,
    }


def _azure_config() -> dict:
    endpoint = _env("AZURE_ENDPOINT")
    return {
        "provider": Provider.AZURE.value,
        "use_azure": True,
        "api_key": _env("AZURE_API_KEY"),
        "azure_endpoint": endpoint,
        "azure_audio_endpoint": endpoint,
        "api_version": os.getenv("AZURE_API_VERSION", "2025-03-01-preview"),
        "model": os.getenv("AZURE_DEPLOYMENT", "gpt-6-luna"),
        "transcription_model": os.getenv("AZURE_TRANSCRIPTION_MODEL", "gpt-4o-transcribe"),
        "embedding_model": _embedding_model_default(Provider.AZURE.value),
    }


def _anthropic_config() -> dict:
    return {
        "provider": Provider.ANTHROPIC.value,
        "api_key": _env("ANTHROPIC_API_KEY"),
        "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        "max_tokens": int(os.getenv("ANTHROPIC_MAX_TOKENS", "4096")),
    }


def _anthropic_foundry_config() -> dict:
    return {
        "provider": Provider.ANTHROPIC_FOUNDRY.value,
        "api_key": _env("ANTHROPIC_FOUNDRY_API_KEY", "AZURE_API_KEY"),
        "resource": _env("ANTHROPIC_FOUNDRY_RESOURCE"),
        "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        "max_tokens": int(os.getenv("ANTHROPIC_MAX_TOKENS", "4096")),
    }


def _google_config() -> dict:
    return {
        "provider": Provider.GOOGLE.value,
        "api_key": _env("GOOGLE_API_KEY", "GEMINI_API_KEY"),
        "model": os.getenv("GOOGLE_MODEL", "gemini-2.5-flash"),
        "embedding_model": _embedding_model_default(Provider.GOOGLE.value),
    }


def _vertex_config() -> dict:
    return {
        "provider": Provider.VERTEX.value,
        "project_id": _env("GOOGLE_PROJECT_ID", "GOOGLE_CLOUD_PROJECT"),
        "location": _env("GOOGLE_CLOUD_LOCATION", default="global"),
        # Standard ADC can be a user, service account, or workload identity file.
        # Let google-auth resolve GOOGLE_APPLICATION_CREDENTIALS itself instead
        # of interpreting every ADC file as a service account private key.
        "service_account_json": _env("GOOGLE_SERVICE_ACCOUNT_JSON"),
        "scopes": [
            scope.strip()
            for scope in (
                _env("GOOGLE_SCOPES") or "https://www.googleapis.com/auth/cloud-platform"
            ).split(",")
            if scope.strip()
        ],
        "generate_content_url": _env("GOOGLE_GENERATE_CONTENT_URL"),
        "model": os.getenv("GOOGLE_MODEL", "gemini-2.5-flash"),
        "embedding_model": _embedding_model_default(Provider.VERTEX.value),
    }
