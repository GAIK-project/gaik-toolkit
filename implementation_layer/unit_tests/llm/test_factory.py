"""Tests for ``gaik.software_components.llm.factory.create_llm_client``."""

from __future__ import annotations

import pytest
from gaik.software_components.llm.config import get_llm_config
from gaik.software_components.llm.factory import build_compat_client, create_llm_client
from openai import AzureOpenAI, OpenAI


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


@pytest.mark.parametrize("environment_provider", [None, "azure", "google"])
def test_minimal_legacy_config_remains_standard_openai(monkeypatch, environment_provider):
    if environment_provider is None:
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
    else:
        monkeypatch.setenv("LLM_PROVIDER", environment_provider)
    config = {"api_key": "test-key", "model": "legacy-model"}
    client = build_compat_client(config)
    try:
        assert type(client) is OpenAI
        assert config == {"api_key": "test-key", "model": "legacy-model"}
    finally:
        client.close()


@pytest.mark.parametrize("routing", [{"provider": "azure"}, {"use_azure": True}])
def test_compat_respects_explicit_azure_routing(monkeypatch, routing):
    monkeypatch.setenv("LLM_PROVIDER", "google")
    client = build_compat_client(
        {
            **routing,
            "api_key": "test-key",
            "model": "azure-deployment",
            "azure_endpoint": "https://example.openai.azure.com",
            "api_version": "2025-03-01-preview",
        }
    )
    try:
        assert isinstance(client, AzureOpenAI)
    finally:
        client.close()


def test_new_factories_keep_environment_provider_selection(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "azure")
    options = {
        "api_key": "test-key",
        "model": "azure-deployment",
        "azure_endpoint": "https://example.openai.azure.com",
        "api_version": "2025-03-01-preview",
    }
    assert get_llm_config(**options)["provider"] == "azure"
    client = create_llm_client(options)
    try:
        assert client.provider == "azure"
        assert isinstance(client.raw, AzureOpenAI)
    finally:
        client.raw.close()
