"""Audio components must reject non-OpenAI/Azure providers."""

from __future__ import annotations

import pytest
from gaik.software_components.llm.factory import assert_openai_or_azure


def test_openai_passes():
    assert_openai_or_azure({"provider": "openai", "api_key": "x"}, component="X")


def test_azure_passes():
    assert_openai_or_azure({"use_azure": True, "api_key": "x"}, component="X")


def test_no_provider_key_passes():
    assert_openai_or_azure({"use_azure": False, "api_key": "x"}, component="X")


@pytest.mark.parametrize(
    "provider", ["anthropic", "anthropic_foundry", "google", "vertex", "aitta", "openai_compatible"]
)
def test_non_openai_providers_raise(provider: str):
    with pytest.raises(NotImplementedError, match="only supports OpenAI/Azure"):
        assert_openai_or_azure({"provider": provider, "api_key": "x"}, component="X")


def test_provider_names_are_normalized():
    assert_openai_or_azure({"provider": " AZURE "}, component="X")


def test_bare_legacy_config_means_openai_whatever_the_default(monkeypatch):
    # Same rule as create_openai_client(): no provider and no use_azure is standard OpenAI.
    monkeypatch.setenv("LLM_PROVIDER", "aitta")
    assert_openai_or_azure({"api_key": "x"}, component="Transcriber")
    with pytest.raises(NotImplementedError, match="provider='aitta'"):
        assert_openai_or_azure({"provider": "aitta"}, component="Transcriber")


def test_audio_error_does_not_recommend_unsupported_gemini_endpoint():
    with pytest.raises(NotImplementedError) as exc:
        assert_openai_or_azure({"provider": "google"}, component="TextToSpeech")
    assert "generativelanguage.googleapis.com" not in str(exc.value)
