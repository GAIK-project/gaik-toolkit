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


def _capture_azure_posts(monkeypatch) -> list[dict]:
    monkeypatch.setenv("TTS_ENDPOINT", "https://example.test/speech")
    monkeypatch.setenv("AZURE_API_KEY", "k")
    payloads: list[dict] = []

    def fake_post(url, *, headers, json, timeout):
        payloads.append(json)
        return SimpleNamespace(raise_for_status=lambda: None, content=b"audio")

    monkeypatch.setattr(tts_module.requests, "post", fake_post)
    return payloads


def test_synthesize_speaks_the_language_the_instance_was_given(monkeypatch):
    payloads = _capture_azure_posts(monkeypatch)
    config = {"use_azure": True, "api_key": "k"}

    english = TextToSpeech(api_config=config, model="gpt-4o-mini-tts", language="en")
    assert english.synthesize("Hello").language == "en"
    assert TextToSpeech(api_config=config, model="gpt-4o-mini-tts").synthesize("Hei").language == (
        "fi"
    )
    # An explicit language still wins over the instance's.
    result = english.synthesize("Hei", language="fi")
    assert result.language == "fi"

    # The language reaches the model, not only the result's label.
    spoken = [payload["instructions"] for payload in payloads]
    assert "in English" in spoken[0]
    assert "in Finnish" in spoken[1]
    assert "in Finnish" in spoken[2] and "English" not in spoken[2]
    assert result.instructions == spoken[2]


def test_azure_sends_the_format_and_speed_the_result_is_labelled_with(monkeypatch):
    payloads = _capture_azure_posts(monkeypatch)
    tts = TextToSpeech(
        api_config={"use_azure": True, "api_key": "k"},
        model="tts-hd",
        response_format="wav",
        speed=1.5,
        language="en",
    )

    result = tts.synthesize("Hello")

    assert payloads[0]["response_format"] == "wav" == result.response_format
    assert payloads[0]["speed"] == 1.5
    assert result.filename.endswith(".wav")
    # tts-1 / tts-1-hd take no instructions: none are sent, and the result says so.
    assert "instructions" not in payloads[0]
    assert result.instructions is None


def test_a_call_overrides_the_format_and_speed(monkeypatch):
    payloads = _capture_azure_posts(monkeypatch)
    tts = TextToSpeech(api_config={"use_azure": True, "api_key": "k"}, model="tts-hd")

    result = tts.synthesize("Hei", response_format="flac", speed=0.75)

    assert (payloads[0]["response_format"], payloads[0]["speed"]) == ("flac", 0.75)
    assert result.content_type == "audio/flac"


def test_the_openai_branch_sends_instructions_only_to_a_model_that_takes_them():
    tts = TextToSpeech(api_config={"use_azure": False, "api_key": "k"}, model="tts-1")
    requests_made: list[dict] = []

    class _Streamed:
        def __init__(self, **kwargs):
            requests_made.append(kwargs)

        def __enter__(self):
            return SimpleNamespace(iter_bytes=lambda: [b"a", b"b"])

        def __exit__(self, *_exc):
            return False

    tts.client = SimpleNamespace(
        audio=SimpleNamespace(
            speech=SimpleNamespace(with_streaming_response=SimpleNamespace(create=_Streamed))
        )
    )

    assert tts.synthesize("Hello", speed=1.25).instructions is None
    tts.model = "gpt-4o-mini-tts"
    assert "in Finnish" in tts.synthesize("Hei").instructions

    assert "instructions" not in requests_made[0]
    assert requests_made[0]["speed"] == 1.25
    assert "in Finnish" in requests_made[1]["instructions"]


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
