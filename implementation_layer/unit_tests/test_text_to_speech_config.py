"""TextToSpeech resolves its provider the same way as its OpenAI client."""

import pytest
from gaik.software_components.text_to_speech import TextToSpeech


def test_bare_legacy_config_is_openai_whatever_llm_provider_says(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "aitta")
    tts = TextToSpeech({"api_key": "test"})
    try:
        assert type(tts.client).__name__ == "OpenAI"
    finally:
        tts.client.close()


@pytest.mark.parametrize("config", [{"provider": "aitta"}, {"provider": "anthropic"}])
def test_explicit_non_audio_provider_is_rejected(config):
    with pytest.raises(NotImplementedError, match="only supports OpenAI/Azure"):
        TextToSpeech({**config, "api_key": "test"})
