"""Tests for ``gaik.software_components.llm.factory.create_llm_client``."""

from __future__ import annotations

import pytest

from gaik.software_components.llm.factory import create_llm_client


def test_legacy_azure_dict_returns_openai_provider(monkeypatch):
    """A legacy ``{"use_azure": True, ...}`` dict still produces a working client."""
    config = {
        "use_azure": True,
        "api_key": "fake",
        "api_version": "2025-03-01-preview",
        "azure_endpoint": "https://example.openai.azure.com/",
        "model": "gpt-5.4",
    }
    client = create_llm_client(config)
    assert client.provider == "azure"
    assert client.model == "gpt-5.4"


def test_legacy_openai_dict_returns_openai_provider():
    config = {
        "use_azure": False,
        "api_key": "fake",
        "model": "gpt-5.4-2026-03-05",
    }
    client = create_llm_client(config)
    assert client.provider == "openai"


def test_explicit_provider_overrides_use_azure_false():
    config = {
        "provider": "azure",
        "use_azure": False,
        "api_key": "fake",
        "api_version": "2025-03-01-preview",
        "azure_endpoint": "https://example.openai.azure.com/",
        "model": "gpt-5.4",
    }
    client = create_llm_client(config)
    assert client.provider == "azure"


def test_unsupported_provider_raises():
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        create_llm_client({"provider": "mistral", "api_key": "x", "model": "y"})
