"""The legacy Claude config reads the Foundry key the way get_llm_config does."""

import pytest

pytest.importorskip("anthropic")

from gaik.software_components.parsers.multimodal_parser.config import (
    get_claude_config,  # noqa: E402
)


def test_foundry_key_wins_over_azure_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_API_KEY", "foundry-key")
    monkeypatch.setenv("AZURE_API_KEY", "azure-openai-key")
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_RESOURCE", "res")

    assert get_claude_config(use_azure=True)["api_key"] == "foundry-key"


def test_azure_key_is_the_fallback(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_FOUNDRY_API_KEY", raising=False)
    monkeypatch.setenv("AZURE_API_KEY", "shared-key")
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_RESOURCE", "res")

    assert get_claude_config(use_azure=True)["api_key"] == "shared-key"


def test_no_key_at_all_names_the_variable(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_FOUNDRY_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_RESOURCE", "res")

    with pytest.raises(ValueError, match="AZURE_API_KEY"):
        get_claude_config(use_azure=True)
