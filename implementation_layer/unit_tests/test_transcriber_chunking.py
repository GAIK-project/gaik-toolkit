"""Chunking behavior for the regular Transcriber component."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from gaik.software_components.transcriber.transcriber import (
    DEFAULT_MAX_DURATION_SECONDS,
    REMOTE_MAX_DURATION_SECONDS,
    Transcriber,
    split_and_transcribe_with_context,
)


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


def test_default_duration_limit_stays_under_the_api_ceiling():
    """Regression for #11: the shipped default must not exceed what the API takes."""
    assert DEFAULT_MAX_DURATION_SECONDS < REMOTE_MAX_DURATION_SECONDS


@pytest.mark.parametrize("duration_s", [1400.001, 1433.728, 1499.0])
def test_duration_just_over_the_api_ceiling_is_chunked_by_default(
    tmp_path: Path, duration_s: float
):
    """Regression for #11.

    With the old default of 1500 s these durations passed our own check, went
    out as a single request, and came back as
    ``BadRequestError: audio duration ... is longer than 1400 seconds``.
    """
    audio = tmp_path / "long.mp3"
    audio.write_bytes(b"tiny")  # small enough that size never forces chunking
    transcriber = _transcriber(max_duration_seconds=DEFAULT_MAX_DURATION_SECONDS)

    with patch(
        "gaik.software_components.transcriber.transcriber.AudioSegment.from_file",
        return_value=_FakeAudio(duration_ms=int(duration_s * 1000)),
    ):
        assert transcriber._needs_chunking(audio) is True


def test_duration_limit_above_the_api_ceiling_is_capped(tmp_path: Path):
    """A caller asking for more than the API allows still gets chunked."""
    audio = tmp_path / "long.mp3"
    audio.write_bytes(b"tiny")
    transcriber = _transcriber(max_duration_seconds=1500)

    with patch(
        "gaik.software_components.transcriber.transcriber.AudioSegment.from_file",
        return_value=_FakeAudio(duration_ms=1_433_728),
    ):
        assert transcriber._needs_chunking(audio) is True


class _FakeChunk:
    def __init__(self, duration_ms: int, exported: list[int]) -> None:
        self.duration_ms = duration_ms
        self._exported = exported

    def export(self, path, format):  # noqa: A002 - mirrors PyDub's signature
        self._exported.append(self.duration_ms)
        Path(path).write_bytes(b"chunk")


class _SliceableFakeAudio(_FakeAudio):
    def __init__(self, duration_ms: int) -> None:
        super().__init__(duration_ms)
        self.exported_chunk_ms: list[int] = []

    def __getitem__(self, item: slice) -> _FakeChunk:
        start = item.start or 0
        stop = self.duration_ms if item.stop is None else min(item.stop, self.duration_ms)
        return _FakeChunk(stop - start, self.exported_chunk_ms)


@pytest.mark.parametrize("max_duration_seconds", [DEFAULT_MAX_DURATION_SECONDS, 1500])
@pytest.mark.parametrize("duration_s", [2800.0, 2850.0, 3000.0, 5600.0, 12_000.0])
def test_chunks_never_exceed_the_api_ceiling(
    tmp_path: Path, duration_s: float, max_duration_seconds: int
):
    """The split itself must not hand the API a chunk it will refuse.

    A 2850 s file at a 1500 s budget used to split into two 1425 s chunks —
    both over the limit, so every chunk failed.
    """
    audio_path = tmp_path / "long.mp3"
    audio_path.write_bytes(b"tiny")  # small enough that size never forces chunking
    audio = _SliceableFakeAudio(duration_ms=int(duration_s * 1000))

    with (
        patch("gaik.software_components.transcriber.transcriber.openai") as fake_openai,
        patch("gaik.software_components.transcriber.transcriber.time.sleep"),
    ):
        fake_openai.audio.transcriptions.create.return_value.text = "chunk transcript"
        split_and_transcribe_with_context(
            str(audio_path),
            {"use_azure": False, "api_key": "test-key"},
            max_size_mb=100,
            max_duration_seconds=max_duration_seconds,
            audio=audio,
            transcription_model="gpt-4o-transcribe",
        )

    assert audio.exported_chunk_ms
    longest_chunk_s = max(audio.exported_chunk_ms) / 1000
    assert longest_chunk_s <= REMOTE_MAX_DURATION_SECONDS


def test_whisper_resolves_to_a_valid_openai_model_id():
    """`whisper` is not an OpenAI model id — sending it returns a 404."""
    transcriber = _transcriber(transcription_model="whisper")

    assert transcriber._resolve_transcription_model() == "whisper-1"


def test_explicit_model_wins_over_the_config():
    """Asking for Whisper on a gpt-4o config used to silently return gpt-4o."""
    transcriber = _transcriber(
        api_config={
            "use_azure": False,
            "api_key": "test-key",
            "transcription_model": "gpt-4o-transcribe",
        },
        transcription_model="whisper-1",
    )

    assert transcriber._resolve_transcription_model() == "whisper-1"


def test_azure_keeps_the_configured_deployment_name():
    """On Azure the model is a deployment name, so the config stays authoritative."""
    transcriber = _transcriber(
        api_config={"use_azure": True, "api_key": "test-key", "transcription_model": "whisper"},
        transcription_model="whisper",
    )

    assert transcriber._resolve_transcription_model() == "whisper"
