"""Offline tests for TextToSpeech's Azure/OpenAI branching.

No test calls a real TTS API: Azure synthesis is exercised through a mocked
``requests.post``, and the OpenAI branch is checked only for which client it builds.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from gaik.software_components.text_to_speech import TextToSpeech
from gaik.software_components.text_to_speech import text_to_speech as tts_module


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for key in ("AZURE_ENDPOINT", "AZURE_OPENAI_ENDPOINT", "TTS_ENDPOINT", "AZURE_API_KEY"):
        monkeypatch.delenv(key, raising=False)


def test_azure_mode_builds_no_chat_client_and_needs_no_azure_endpoint():
    # Azure synthesis is a raw HTTP call (see below), so building an AzureOpenAI SDK
    # client here would demand an AZURE_ENDPOINT that Azure mode never uses.
    tts = TextToSpeech(api_config={"use_azure": True, "api_key": "k"}, language="en")
    assert tts.client is None


def test_openai_mode_still_builds_a_client():
    tts = TextToSpeech(api_config={"use_azure": False, "api_key": "k"}, language="en")
    assert tts.client is not None


def test_azure_synthesize_posts_to_tts_endpoint(monkeypatch):
    monkeypatch.setenv("TTS_ENDPOINT", "https://example.test/speech")
    monkeypatch.setenv("AZURE_API_KEY", "k")
    calls = []

    def fake_post(url, *, headers, json, timeout):
        calls.append((url, headers, json, timeout))
        return SimpleNamespace(raise_for_status=lambda: None, content=b"audio-bytes")

    monkeypatch.setattr(tts_module.requests, "post", fake_post)

    tts = TextToSpeech(api_config={"use_azure": True, "api_key": "k"}, language="en")
    result = tts.synthesize("Hello", language="en")

    assert result.audio_bytes == b"audio-bytes"
    assert calls[0][0] == "https://example.test/speech"
    assert calls[0][2]["input"] == "Hello"
