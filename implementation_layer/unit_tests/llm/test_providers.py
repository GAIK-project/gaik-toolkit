"""Tests for ``gaik.software_components.llm.providers.resolve_provider``."""

from __future__ import annotations

import os

import pytest

from gaik.software_components.llm.providers import Provider, resolve_provider


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)


def test_explicit_argument_wins_over_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert resolve_provider("google") == "google"


def test_config_provider_used_when_no_argument(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert resolve_provider(config={"provider": "google"}) == "google"


def test_env_used_when_no_argument_or_config():
    os.environ["LLM_PROVIDER"] = "anthropic"
    try:
        assert resolve_provider() == "anthropic"
    finally:
        os.environ.pop("LLM_PROVIDER", None)


def test_legacy_use_azure_true_maps_to_azure():
    assert resolve_provider(config={"use_azure": True}) == Provider.AZURE.value


def test_legacy_use_azure_false_maps_to_openai():
    assert resolve_provider(config={"use_azure": False}) == Provider.OPENAI.value


def test_default_is_azure():
    assert resolve_provider() == Provider.AZURE.value


def test_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        resolve_provider("mistral")


def test_provider_name_is_normalized():
    assert resolve_provider("  GOOGLE  ") == "google"
