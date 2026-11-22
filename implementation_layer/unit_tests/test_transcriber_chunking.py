"""Chunking behavior for the regular Transcriber component."""

from __future__ import annotations

import traceback
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
            "gaik.software_components.transcriber.transcriber._decode_audio",
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
            "gaik.software_components.transcriber.transcriber._decode_audio",
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
            "gaik.software_components.transcriber.transcriber._decode_audio",
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
            "gaik.software_components.transcriber.transcriber._decode_audio",
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
            "gaik.software_components.transcriber.transcriber._decode_audio",
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
        "gaik.software_components.transcriber.transcriber._decode_audio",
        return_value=_FakeAudio(duration_ms=int(duration_s * 1000)),
    ):
        assert transcriber._needs_chunking(audio) is True


def test_duration_limit_above_the_api_ceiling_is_capped(tmp_path: Path):
    """A caller asking for more than the API allows still gets chunked."""
    audio = tmp_path / "long.mp3"
    audio.write_bytes(b"tiny")
    transcriber = _transcriber(max_duration_seconds=1500)

    with patch(
        "gaik.software_components.transcriber.transcriber._decode_audio",
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


def _chunk_requests(
    tmp_path: Path,
    base_prompt: str | None,
    transcripts: list[str | Exception],
    *,
    allow_partial: bool = False,
) -> list[dict[str, object]]:
    """Transcribe three chunks; each request returns (or raises) the next item."""
    audio_path = tmp_path / "long.mp3"
    audio_path.write_bytes(b"tiny")
    requests: list[dict[str, object]] = []

    def create_request(**kwargs: object) -> SimpleNamespace:
        requests.append({key: value for key, value in kwargs.items() if key != "file"})
        outcome = transcripts[len(requests) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(text=outcome, usage=None)

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
            allow_partial=allow_partial,
        )
    assert len(requests) == 3
    return requests


def _three_chunks(tmp_path: Path, replies: list[str | Exception], **options: object):
    """Run three chunks; returns (requests, transcript), or (requests, raised error)."""
    audio_path = tmp_path / "long.mp3"
    audio_path.write_bytes(b"tiny")
    requests: list[dict[str, object]] = []

    def create_request(**kwargs: object) -> SimpleNamespace:
        requests.append({key: value for key, value in kwargs.items() if key != "file"})
        outcome = replies[len(requests) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(text=outcome, usage=None)

    with (
        patch("gaik.software_components.transcriber.transcriber.create_openai_client") as factory,
        patch("gaik.software_components.transcriber.transcriber.time.sleep"),
    ):
        factory.return_value.audio.transcriptions.create.side_effect = create_request
        try:
            outcome = split_and_transcribe_with_context(
                str(audio_path),
                {"use_azure": False, "api_key": "test-key"},
                max_size_mb=100,
                max_duration_seconds=60,
                audio=_SliceableFakeAudio(duration_ms=120_000),
                transcription_model="gpt-4o-transcribe",
                **options,
            )
        except RuntimeError as error:
            outcome = error
    return requests, outcome


def test_a_failed_chunk_raises_with_its_time_range_and_the_rest_are_not_sent(tmp_path: Path):
    requests, outcome = _three_chunks(tmp_path, ["One", RuntimeError("provider error"), "Three"])

    assert isinstance(outcome, RuntimeError)
    assert "Segment 2 of 3 (00:40 - 01:20)" in str(outcome)
    assert "provider error" not in str(outcome)
    assert len(requests) == 2


def test_the_failed_chunk_error_keeps_the_provider_message_out_of_its_traceback(
    tmp_path: Path,
):
    # A logged traceback (logger.exception) shows a chained cause or context in full.
    _, outcome = _three_chunks(tmp_path, ["One", RuntimeError("provider error"), "Three"])

    assert isinstance(outcome, RuntimeError)
    assert outcome.__cause__ is None
    assert outcome.__suppress_context__
    logged = "".join(traceback.format_exception(type(outcome), outcome, outcome.__traceback__))
    assert "provider error" not in logged
    assert "Segment 2 of 3" in logged


def test_allow_partial_marks_the_failed_chunk_and_transcribes_the_rest(tmp_path: Path):
    requests, outcome = _three_chunks(
        tmp_path, ["One", RuntimeError("provider error"), "Three"], allow_partial=True
    )

    assert len(requests) == 3
    assert "[Timestamp: 00:40 - 01:20]\n[Transcription failed for segment 2]" in outcome
    assert "One" in outcome and "Three" in outcome


def test_allow_partial_still_raises_when_every_chunk_failed(tmp_path: Path):
    # A wrong key or a missing deployment fails every chunk: the markers alone are
    # no transcript, whatever allow_partial says.
    failed: list[dict] = []
    requests, outcome = _three_chunks(
        tmp_path,
        [PermissionError("bad key k-123")] * 3,
        allow_partial=True,
        failed_segments=failed,
    )

    assert len(requests) == 3
    assert isinstance(outcome, RuntimeError)
    assert "None of the 3 segments could be transcribed (PermissionError)" in str(outcome)
    assert "k-123" not in str(outcome)
    assert outcome.__cause__ is None
    assert failed == []  # nothing to report beside the raised error


def test_allow_partial_lists_the_failed_segments(tmp_path: Path, capsys):
    failed: list[dict] = []
    _, outcome = _three_chunks(
        tmp_path,
        ["One", RuntimeError("provider error"), "Three"],
        allow_partial=True,
        failed_segments=failed,
    )

    assert isinstance(outcome, str)
    assert failed == [{"segment": 2, "start_seconds": 40.0, "end_seconds": 80.0}]
    assert "Segments 2 of 3 could not be transcribed" in capsys.readouterr().out


def test_the_transcription_result_lists_the_failed_segments(tmp_path: Path):
    audio = tmp_path / "long.mp3"
    audio.write_bytes(b"tiny")
    transcriber = Transcriber(
        {"use_azure": False, "api_key": "test-key"},
        output_dir=tmp_path / "w",
        allow_partial=True,
        transcription_model="gpt-4o-transcribe",
    )
    lost = {"segment": 2, "start_seconds": 40.0, "end_seconds": 80.0}

    def split(*_args, failed_segments, **_kwargs):
        failed_segments.append(lost)
        return "[Timestamp: 00:40 - 01:20]\n[Transcription failed for segment 2]"

    with (
        patch.object(transcriber, "_needs_chunking", return_value=True),
        patch(
            "gaik.software_components.transcriber.transcriber._decode_audio",
            return_value=_SliceableFakeAudio(duration_ms=120_000),
        ),
        patch(
            "gaik.software_components.transcriber.transcriber.split_and_transcribe_with_context",
            side_effect=split,
        ),
    ):
        result = transcriber.transcribe(audio)

    assert result.failed_segments == [lost]


def test_a_transcription_result_without_failures_lists_none():
    from gaik.software_components.transcriber.transcriber import TranscriptionResult

    assert TranscriptionResult("text", None, "job").failed_segments == []


@pytest.mark.parametrize("allow_partial", [False, True])
def test_the_transcriber_passes_allow_partial_to_the_chunked_path(
    tmp_path: Path, allow_partial: bool
):
    audio = tmp_path / "long.mp3"
    audio.write_bytes(b"tiny")
    transcriber = Transcriber(
        {"use_azure": False, "api_key": "test-key"},
        output_dir=tmp_path / "w",
        allow_partial=allow_partial,
    )
    with (
        patch.object(transcriber, "_needs_chunking", return_value=True),
        patch(
            "gaik.software_components.transcriber.transcriber._decode_audio",
            return_value=_SliceableFakeAudio(duration_ms=1_000),
        ),
        patch(
            "gaik.software_components.transcriber.transcriber.split_and_transcribe_with_context",
            return_value="text",
        ) as split,
    ):
        transcriber._transcribe_input_remote(audio, None, "gpt-4o-transcribe")

    assert split.call_args.kwargs["allow_partial"] is allow_partial


_CONTEXT = "Matti Virtanen, pumppu P-17"


@pytest.mark.parametrize(
    ("base_prompt", "first_chunk", "expected_prompts"),
    [
        # Without caller context the first request has no prompt; later ones
        # continue from the previous transcript.
        (None, "Transcript 1", [None, "Transcript 1", "Transcript 2"]),
        # The caller's context reaches every chunk, before the previous transcript.
        (
            _CONTEXT,
            "Transcript 1",
            [_CONTEXT, f"{_CONTEXT}\nTranscript 1", f"{_CONTEXT}\nTranscript 2"],
        ),
        # With allow_partial, after a failed first chunk there is no transcript to
        # continue from.
        (None, RuntimeError("first chunk failed"), [None, None, "Transcript 2"]),
        (
            _CONTEXT,
            RuntimeError("first chunk failed"),
            [_CONTEXT, _CONTEXT, f"{_CONTEXT}\nTranscript 2"],
        ),
    ],
)
def test_every_chunk_gets_the_caller_context_before_the_previous_transcript(
    tmp_path: Path,
    base_prompt: str | None,
    first_chunk: str | Exception,
    expected_prompts: list[str | None],
):
    requests = _chunk_requests(
        tmp_path,
        base_prompt,
        [first_chunk, "Transcript 2", "Transcript 3"],
        allow_partial=isinstance(first_chunk, Exception),
    )

    # None means the request carries no prompt at all, not an empty one.
    assert [request.get("prompt", None) for request in requests] == expected_prompts
    assert ["prompt" in request for request in requests] == [
        prompt is not None for prompt in expected_prompts
    ]


def test_a_later_chunk_carries_only_the_end_of_a_long_previous_transcript(tmp_path: Path):
    previous = " ".join(f"sana{number}" for number in range(100))
    requests = _chunk_requests(tmp_path, _CONTEXT, [previous, "Transcript 2", "Transcript 3"])

    assert requests[1]["prompt"] == f"{_CONTEXT}\n{previous[-170:]}"


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


def test_a_bad_enhancement_ratio_fails_when_the_transcriber_is_built():
    for ratio in (0, 1.5, -0.1):
        with pytest.raises(ValueError, match="enhancement_max_change_ratio"):
            _transcriber(enhancement_max_change_ratio=ratio)
    assert _transcriber(enhancement_max_change_ratio=None).enhancement_max_change_ratio is None
