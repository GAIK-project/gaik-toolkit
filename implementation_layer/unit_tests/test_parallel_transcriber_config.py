"""Config invariants for parallel_transcriber.

Locks the GPT-4o diarize timeout fix: the default ``api_timeout_seconds`` must be
large enough for a default ``gpt4o_chunk_duration_minutes`` chunk, otherwise a
dense 23-min chunk exceeds the timeout and diarize raises
``RuntimeError("GPT-4o transcription timed out")`` after retries.
"""

from __future__ import annotations

from gaik.software_components.parallel_transcriber import TranscriptionConfig


def test_default_api_timeout_is_600():
    assert TranscriptionConfig().api_timeout_seconds == 600


def test_default_timeout_fits_default_gpt4o_chunk():
    cfg = TranscriptionConfig()
    # Rule of thumb: budget ~25s of wall-clock per audio-minute of dense speech.
    assert cfg.api_timeout_seconds >= cfg.gpt4o_chunk_duration_minutes * 25, (
        f"api_timeout_seconds={cfg.api_timeout_seconds} too small for a "
        f"{cfg.gpt4o_chunk_duration_minutes}-min chunk — diarize will time out"
    )


def test_from_env_api_timeout_override(monkeypatch):
    monkeypatch.setenv("API_TIMEOUT_SECONDS", "300")
    assert TranscriptionConfig.from_env().api_timeout_seconds == 300


def test_from_env_azure_alias_override(monkeypatch):
    monkeypatch.delenv("API_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("AZURE_OPENAI_TIMEOUT_SECONDS", "450")
    assert TranscriptionConfig.from_env().api_timeout_seconds == 450
