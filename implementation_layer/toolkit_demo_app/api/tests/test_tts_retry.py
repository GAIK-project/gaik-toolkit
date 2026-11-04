"""The TTS demo retries a rate-limited (429) speech request instead of failing."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from api.routers import text_to_speech as tts_router


class RateLimitedError(Exception):
    def __init__(self):
        super().__init__("429 Client Error: Too Many Requests")
        self.response = SimpleNamespace(status_code=429, headers={"Retry-After": "0"})


class FlakyTTS:
    def __init__(self, failures: int):
        self.failures = failures
        self.calls = 0

    def synthesize(self, text):
        self.calls += 1
        if self.calls <= self.failures:
            raise RateLimitedError()
        return f"audio:{text}"


@pytest.mark.asyncio
async def test_retries_a_rate_limited_request():
    tts = FlakyTTS(failures=2)
    assert await tts_router._synthesize_with_retry(tts, "hei") == "audio:hei"
    assert tts.calls == 3


@pytest.mark.asyncio
async def test_gives_up_after_the_last_attempt_and_on_other_errors():
    with pytest.raises(RateLimitedError):
        await tts_router._synthesize_with_retry(FlakyTTS(failures=5), "hei")

    class Broken:
        calls = 0

        def synthesize(self, text):
            Broken.calls += 1
            raise ValueError("bad voice")

    with pytest.raises(ValueError):
        await tts_router._synthesize_with_retry(Broken(), "hei")
    assert Broken.calls == 1
