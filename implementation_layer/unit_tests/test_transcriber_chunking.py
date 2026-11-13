"""Chunking behavior for the regular Transcriber component."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from gaik.software_components.transcriber.transcriber import (
    DEFAULT_MAX_DURATION_SECONDS,
    REMOTE_MAX_DURATION_SECONDS,
    Transcriber,
    _transcription_usage,
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
    single.assert_called_once_with(audio, "prompt", "gpt-4o-transcribe", None)


@pytest.mark.parametrize(
    ("overrides", "custom_context", "expected_prompt"),
    [
        ({}, "", None),
        ({}, "Suomenkielinen aihe", "Suomenkielinen aihe"),
        ({"default_prompt": "Explicit prompt"}, "", "Explicit prompt"),
        (
            {"default_prompt": "Explicit prompt"},
            "Additional context",
            "Explicit prompt\nAdditional context",
        ),
    ],
)
def test_transcribe_sends_only_explicit_prompt_context(
    tmp_path: Path,
    overrides: dict[str, object],
    custom_context: str,
    expected_prompt: str | None,
):
    audio = tmp_path / "short.mp3"
    audio.write_bytes(b"tiny")
    transcriber = _transcriber(output_dir=tmp_path / "output", **overrides)

    with (
        patch(
            "gaik.software_components.transcriber.transcriber.AudioSegment.from_file",
            side_effect=OSError("duration unavailable in test"),
        ),
        patch(
            "gaik.software_components.transcriber.transcriber._create_audio_client"
        ) as create_client,
        patch("gaik.software_components.transcriber.transcriber._close_owned_audio_client"),
        patch.object(transcriber, "_needs_chunking", return_value=False),
    ):
        create_client.return_value.audio.transcriptions.create.return_value = SimpleNamespace(
            text="Transcript", usage=None
        )
        transcriber.transcribe(audio, custom_context=custom_context)

    request = create_client.return_value.audio.transcriptions.create.call_args.kwargs
    if expected_prompt is None:
        assert "prompt" not in request
    else:
        assert request["prompt"] == expected_prompt


def test_custom_context_does_not_leak_into_later_transcriptions(tmp_path: Path):
    audio = tmp_path / "short.mp3"
    audio.write_bytes(b"tiny")
    transcriber = _transcriber(output_dir=tmp_path / "output")

    with (
        patch(
            "gaik.software_components.transcriber.transcriber.AudioSegment.from_file",
            side_effect=OSError("duration unavailable in test"),
        ),
        patch(
            "gaik.software_components.transcriber.transcriber._create_audio_client"
        ) as create_client,
        patch("gaik.software_components.transcriber.transcriber._close_owned_audio_client"),
        patch.object(transcriber, "_needs_chunking", return_value=False),
    ):
        create_client.return_value.audio.transcriptions.create.return_value = SimpleNamespace(
            text="Transcript", usage=None
        )
        transcriber.transcribe(audio, custom_context="Explicit context")
        transcriber.transcribe(audio)

    requests = create_client.return_value.audio.transcriptions.create.call_args_list
    assert requests[0].kwargs["prompt"] == "Explicit context"
    assert "prompt" not in requests[1].kwargs


def test_local_whisper_path_remains_independent_of_remote_prompt(tmp_path: Path):
    audio = tmp_path / "short.mp3"
    audio.write_bytes(b"tiny")
    transcriber = _transcriber(
        output_dir=tmp_path / "output",
        transcription_model="whisper_local",
        initial_prompt="Finnish names",
    )

    with (
        patch(
            "gaik.software_components.transcriber.transcriber.AudioSegment.from_file",
            side_effect=OSError("duration unavailable in test"),
        ),
        patch.object(
            transcriber, "_transcribe_input_local", return_value=("Transcript", None)
        ) as local,
    ):
        transcriber.transcribe(audio, custom_context="Remote-only context")

    local.assert_called_once_with(audio)
    assert transcriber.initial_prompt == "Finnish names"


def test_transcription_usage_maps_tokens_and_duration():
    tokens = SimpleNamespace(type="tokens", input_tokens=7, output_tokens=3, total_tokens=10)
    duration = SimpleNamespace(type="duration", seconds=61.2)
    assert _transcription_usage(SimpleNamespace(usage=tokens)) == {
        "prompt_tokens": 7,
        "completion_tokens": 3,
        "total_tokens": 10,
    }
    assert _transcription_usage(SimpleNamespace(usage=duration)) == {"audio_seconds": 62}
    assert _transcription_usage(SimpleNamespace(usage=None)) == {}
    with pytest.raises(ValueError, match="'credits'"):
        _transcription_usage(SimpleNamespace(usage=SimpleNamespace(type="credits")))


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


@pytest.mark.parametrize(
    ("base_prompt", "fail_first"),
    [
        (None, False),
        ("Explicit Finnish-language context", False),
        (None, True),
        ("Explicit Finnish-language context", True),
    ],
)
def test_chunked_transcription_omits_default_and_uses_prior_transcript_context(
    tmp_path: Path, base_prompt: str | None, fail_first: bool
):
    audio_path = tmp_path / "long.mp3"
    audio_path.write_bytes(b"tiny")
    requests: list[dict[str, object]] = []

    def create_request(**kwargs: object) -> SimpleNamespace:
        requests.append({key: value for key, value in kwargs.items() if key != "file"})
        if fail_first and len(requests) == 1:
            raise RuntimeError("first chunk failed")
        return SimpleNamespace(text=f"Transcript {len(requests)}", usage=None)

    with (
        patch("gaik.software_components.transcriber.transcriber.create_openai_client") as factory,
        patch("gaik.software_components.transcriber.transcriber.time.sleep"),
    ):
        factory.return_value.audio.transcriptions.create.side_effect = create_request
        split_and_transcribe_with_context(
            str(audio_path),
            {"use_azure": False, "api_key": "test-key"},
            max_size_mb=100,
            max_duration_seconds=60,
            audio=_SliceableFakeAudio(duration_ms=120_000),
            base_prompt=base_prompt,
            transcription_model="gpt-4o-transcribe",
        )

    assert len(requests) == 3
    if base_prompt is None:
        assert "prompt" not in requests[0]
    else:
        assert requests[0]["prompt"] == base_prompt
    if fail_first:
        assert "prompt" not in requests[1]
        assert requests[2]["prompt"] == "Transcript 2"
    else:
        assert requests[1]["prompt"] == "Transcript 1"
        assert requests[2]["prompt"] == "Transcript 2"


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
        patch("gaik.software_components.transcriber.transcriber.create_openai_client") as factory,
        patch("gaik.software_components.transcriber.transcriber.time.sleep"),
    ):
        factory.return_value.audio.transcriptions.create.return_value.text = "chunk transcript"
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
