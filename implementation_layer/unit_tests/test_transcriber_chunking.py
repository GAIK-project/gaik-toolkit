"""Chunking behavior for the regular Transcriber component."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from gaik.software_components.transcriber.transcriber import Transcriber


class _FakeAudio:
    def __init__(self, duration_ms: int) -> None:
        self.duration_ms = duration_ms

    def __len__(self) -> int:
        return self.duration_ms


def _transcriber(**overrides) -> Transcriber:
    kwargs = {
        "api_config": {"use_azure": False, "api_key": "test-key"},
        "max_size_mb": 100,
        "max_duration_seconds": 60,
        "transcription_model": "gpt-4o-transcribe",
    }
    kwargs.update(overrides)
    return Transcriber(**kwargs)


def test_gpt_transcription_chunks_when_duration_exceeds_limit(tmp_path: Path):
    audio = tmp_path / "long.mp3"
    audio.write_bytes(b"tiny")
    transcriber = _transcriber(max_duration_seconds=1)

    with (
        patch(
            "gaik.software_components.transcriber.transcriber.AudioSegment.from_file",
            return_value=_FakeAudio(duration_ms=2_000),
        ),
        patch(
            "gaik.software_components.transcriber.transcriber.split_and_transcribe_with_context",
            return_value="chunked transcript",
        ) as split,
        patch.object(
            transcriber,
            "_single_pass_transcription",
            side_effect=AssertionError("single-pass should not run"),
        ),
    ):
        result = transcriber._transcribe_input_remote(audio, "prompt", "gpt-4o-transcribe")

    assert result == "chunked transcript"
    split.assert_called_once()
    assert split.call_args.kwargs["transcription_model"] == "gpt-4o-transcribe"


def test_gpt_transcription_single_pass_when_within_size_and_duration(tmp_path: Path):
    audio = tmp_path / "short.mp3"
    audio.write_bytes(b"tiny")
    transcriber = _transcriber(max_duration_seconds=60)

    with (
        patch(
            "gaik.software_components.transcriber.transcriber.AudioSegment.from_file",
            return_value=_FakeAudio(duration_ms=1_000),
        ),
        patch(
            "gaik.software_components.transcriber.transcriber.split_and_transcribe_with_context",
            side_effect=AssertionError("chunking should not run"),
        ),
        patch.object(
            transcriber,
            "_single_pass_transcription",
            return_value="single-pass transcript",
        ) as single,
    ):
        result = transcriber._transcribe_input_remote(audio, "prompt", "gpt-4o-transcribe")

    assert result == "single-pass transcript"
    single.assert_called_once_with(audio, "prompt", "gpt-4o-transcribe")
