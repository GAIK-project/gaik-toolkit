"""ParallelTranscriber backends: the Azure audio client, the request format each model
takes, and stopping the queued chunks after a failure.

No test calls a provider: the SDK client and the HTTP posts are fakes.
"""

from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from gaik.software_components.parallel_transcriber import (
    ParallelTranscriber,
    TranscriptionConfig,
    TranscriptionModel,
    pipeline,
)
from gaik.software_components.parallel_transcriber.srt import parse_srt_content

_CHAT = "https://chat-resource.openai.azure.com"
_AUDIO = "https://audio-resource.openai.azure.com"


# -- the Azure audio client (#143 item 6) --------------------------------------------


@pytest.mark.parametrize(
    "endpoint",
    [
        _AUDIO,
        f"{_AUDIO}/",
        f"{_AUDIO}/openai",
        f"{_AUDIO}/openai/",
        f"{_AUDIO}/openai/v1",
        f"{_AUDIO}/openai/v1/",
        f"{_AUDIO}/openai/deployments/whisper/audio/transcriptions?api-version=2024-06-01",
    ],
)
def test_both_transcribers_cut_an_azure_endpoint_to_its_resource(endpoint):
    from gaik.software_components.transcriber.transcriber import (
        _azure_resource_endpoint as transcriber_cut,
    )

    assert pipeline._azure_resource_endpoint(endpoint) == _AUDIO
    assert transcriber_cut(endpoint) == _AUDIO


@pytest.mark.parametrize(
    "flags",
    [{"provider": "azure"}, {"use_azure": True}, {"provider": "azure", "use_azure": True}],
)
def test_the_whisper_client_goes_to_the_audio_resource(flags):
    config = {
        **flags,
        "api_key": "test-key",
        "azure_endpoint": _CHAT,
        "azure_audio_endpoint": f"{_AUDIO}/openai/v1",
        "api_version": "2025-03-01-preview",
    }
    transcriber = ParallelTranscriber(config)

    client_config = transcriber._whisper_client_config()
    assert client_config["azure_endpoint"] == _AUDIO
    assert client_config["use_azure"] is True
    client = transcriber._make_whisper_client()
    try:
        assert str(client.base_url).startswith(f"{_AUDIO}/openai/")
    finally:
        client.close()


def test_the_whisper_client_falls_back_to_the_chat_endpoint_and_a_default_api_version():
    config = {"provider": "azure", "api_key": "test-key", "azure_endpoint": f"{_CHAT}/openai/v1"}

    client_config = ParallelTranscriber(config)._whisper_client_config()

    assert client_config["azure_endpoint"] == _CHAT
    assert client_config["api_version"] == "2024-12-01-preview"


def test_a_v1_base_url_is_kept_unless_an_audio_endpoint_is_given():
    config = {
        "provider": "azure",
        "api_key": "test-key",
        "base_url": f"{_CHAT}/openai/v1",
        "azure_endpoint": "https://leftover.example.test",
        "api_version": "2025-03-01-preview",
    }

    kept = ParallelTranscriber(config)._whisper_client_config()
    audio = ParallelTranscriber(
        {**config, "azure_audio_endpoint": f"{_AUDIO}/openai/v1"}
    )._whisper_client_config()

    assert kept["base_url"] == f"{_CHAT}/openai/v1"
    assert "base_url" not in audio and audio["azure_endpoint"] == _AUDIO


def test_a_bare_openai_config_keeps_openai():
    client_config = ParallelTranscriber({"api_key": "test-key"})._whisper_client_config()

    assert client_config["provider"] == "openai"
    assert client_config["use_azure"] is False


def test_the_diarize_url_does_not_repeat_the_openai_path(tmp_path, monkeypatch):
    import httpx

    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"\x00" * 10)
    urls: list[str] = []

    def fake_post(url, **_kwargs):
        urls.append(url)
        return SimpleNamespace(status_code=200, json=lambda: {"segments": []})

    monkeypatch.setattr(httpx, "post", fake_post)
    transcriber = ParallelTranscriber(
        {
            "provider": "azure",
            "api_key": "test-key",
            "azure_audio_endpoint": f"{_AUDIO}/openai/v1",
            "api_version": "2025-03-01-preview",
        },
        TranscriptionConfig(model=TranscriptionModel.GPT4O_DIARIZE),
    )

    transcriber._call_gpt4o_api(str(audio))

    assert urls == [
        f"{_AUDIO}/openai/deployments/gpt-4o-transcribe/audio/transcriptions"
        "?api-version=2025-03-01-preview"
    ]


# -- the format each Whisper-backend model takes (#143 item 7) -----------------------


class _FakeAudioClient:
    """Answers each transcription request with the next reply; records the requests."""

    def __init__(self, replies: dict[str, object] | list[object]):
        self.replies = replies
        self.requests: list[dict] = []
        self.lock = threading.Lock()
        self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        name = Path(kwargs["file"].name).name
        with self.lock:
            self.requests.append({k: v for k, v in kwargs.items() if k != "file"} | {"_": name})
            reply = (
                self.replies[name]
                if isinstance(self.replies, dict)
                else self.replies[len(self.requests) - 1]
            )
        if isinstance(reply, BaseException):
            raise reply
        return reply


def _whisper(model: str, client: _FakeAudioClient, **config) -> ParallelTranscriber:
    transcriber = ParallelTranscriber(
        {"api_key": "test-key", "transcription_model": model},
        TranscriptionConfig(max_retries=0, max_429_retries=0, **config),
    )
    transcriber._make_whisper_client = lambda: client
    return transcriber


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("gpt-4o-transcribe", "json"),
        ("gpt-4o-mini-transcribe", "json"),
        ("my-gpt-4o-transcribe-deployment", "json"),
        ("whisper", "srt"),
        ("whisper-1", "srt"),
    ],
)
def test_each_model_is_asked_for_a_format_it_supports(model, expected):
    transcriber = _whisper(model, _FakeAudioClient([]))

    assert transcriber._whisper_request(model, file=None)["response_format"] == expected


def test_a_gpt4o_single_pass_becomes_one_srt_cue(tmp_path, monkeypatch):
    audio = tmp_path / "note.mp3"
    audio.write_bytes(b"\x00" * 10)
    monkeypatch.setattr(pipeline, "get_audio_duration", lambda _p: 12.5)
    client = _FakeAudioClient([SimpleNamespace(text="Hei, tässä muistio.")])

    srt = _whisper("gpt-4o-transcribe", client)._call_whisper_single(audio)

    assert client.requests[0]["response_format"] == "json"
    assert srt == "1\n00:00:00,000 --> 00:00:12,500\nHei, tässä muistio.\n"


def test_whisper_keeps_its_srt(tmp_path):
    audio = tmp_path / "note.mp3"
    audio.write_bytes(b"\x00" * 10)
    srt = "1\n00:00:00,000 --> 00:00:01,000\nHello\n"
    client = _FakeAudioClient([srt])

    assert _whisper("whisper", client)._call_whisper_single(audio) == srt
    assert client.requests[0]["response_format"] == "srt"


def test_a_gpt4o_answer_without_text_gives_an_empty_transcript(tmp_path, monkeypatch):
    audio = tmp_path / "note.mp3"
    audio.write_bytes(b"\x00" * 10)
    monkeypatch.setattr(pipeline, "get_audio_duration", lambda _p: 3.0)
    client = _FakeAudioClient([SimpleNamespace(text="")])

    assert _whisper("gpt-4o-transcribe", client)._call_whisper_single(audio) == ""


def _chunks(tmp_path: Path, count: int) -> tuple[list[str], list[dict]]:
    """``count`` chunk files of 20 minutes with 15 s overlaps, as split_audio gives them."""
    files, metadata = [], []
    for i in range(count):
        path = tmp_path / f"rec_chunk_{i + 1:02d}.mp3"
        path.write_bytes(b"\x00" * 10)
        files.append(str(path))
        metadata.append(
            {
                "index": i,
                "nominal_start": i * 1200.0,
                "actual_start": max(0.0, i * 1200.0 - 15.0),
                "overlap_start": 15.0 if i else 0.0,
                "overlap_end": 15.0 if i < count - 1 else 0.0,
            }
        )
    return files, metadata


def test_gpt4o_chunks_are_joined_without_their_shared_words(tmp_path, monkeypatch):
    files, metadata = _chunks(tmp_path, 2)
    monkeypatch.setattr(pipeline, "get_audio_duration", lambda _p: 31.0)
    client = _FakeAudioClient(
        {
            "rec_chunk_01.mp3": SimpleNamespace(
                text="Alku on tässä. Potilas tuli vastaanotolle ja hammas 36 oiretti, ja s"
            ),
            "rec_chunk_02.mp3": SimpleNamespace(
                text="tuli vastaanotolle ja hammas 36 oireili, joten se paikattiin."
            ),
        }
    )
    transcriber = _whisper("gpt-4o-transcribe", client)

    srt = transcriber._transcribe_chunks_whisper(files, metadata, 2, None, None)

    cues = parse_srt_content(srt)
    assert [(c["start_seconds"], c["end_seconds"]) for c in cues] == [
        (0.0, 1200.0),
        (1200.0, 1216.0),
    ]
    text = " ".join(c["text"] for c in cues)
    assert text == (
        "Alku on tässä. Potilas tuli vastaanotolle ja hammas 36 oireili, joten se paikattiin."
    )
    assert {r["response_format"] for r in client.requests} == {"json"}


def test_gpt4o_chunks_without_shared_words_are_both_kept_whole(tmp_path, monkeypatch):
    files, metadata = _chunks(tmp_path, 2)
    monkeypatch.setattr(pipeline, "get_audio_duration", lambda _p: 31.0)
    client = _FakeAudioClient(
        {
            "rec_chunk_01.mp3": SimpleNamespace(text="Ensimmäinen osa päättyy tähän."),
            "rec_chunk_02.mp3": SimpleNamespace(text="Toinen osa alkaa nyt."),
        }
    )

    srt = _whisper("gpt-4o-transcribe", client)._transcribe_chunks_whisper(
        files, metadata, 2, None, None
    )

    assert [c["text"] for c in parse_srt_content(srt)] == [
        "Ensimmäinen osa päättyy tähän.",
        "Toinen osa alkaa nyt.",
    ]


def test_shared_words_are_kept_once_and_nothing_else_is_dropped():
    previous = "a b c one two three four five x".split()
    following = "y one two three four five six seven".split()

    kept_previous, kept_following = pipeline._drop_repeated_words(previous, following, 30.0)

    assert kept_previous + kept_following == "a b c one two three four five six seven".split()


def test_three_shared_words_are_not_enough_to_drop_any():
    previous = "a b c one two three".split()
    following = "one two three d e".split()

    assert pipeline._drop_repeated_words(previous, following, 30.0) == (previous, following)


def test_whisper_chunks_still_go_through_the_srt_merge(tmp_path, monkeypatch):
    files, metadata = _chunks(tmp_path, 2)
    merged: list[tuple] = []
    monkeypatch.setattr(
        pipeline, "combine_srt_chunks", lambda texts, meta: merged.append((texts, meta)) or "ok"
    )
    client = _FakeAudioClient({Path(f).name: f"srt {i}" for i, f in enumerate(files)})

    result = _whisper("whisper", client)._transcribe_chunks_whisper(files, metadata, 2, None, None)

    assert result == "ok"
    assert merged == [(["srt 0", "srt 1"], metadata)]


# -- a failure stops the chunks not yet sent (#143 "Also seen") ----------------------


def test_a_failed_whisper_chunk_stops_the_queued_ones(tmp_path):
    files, metadata = _chunks(tmp_path, 5)
    replies: dict[str, object] = {
        Path(f).name: "1\n00:00:00,000 --> 00:00:01,000\nx\n" for f in files
    }
    replies["rec_chunk_02.mp3"] = PermissionError("wrong key")
    client = _FakeAudioClient(replies)
    transcriber = _whisper("whisper", client)

    with pytest.raises(PermissionError):
        transcriber._transcribe_chunks_whisper(files, metadata, 1, None, None)

    # With one worker the chunks run in order: chunks 3 to 5 are never sent.
    assert [r["_"] for r in client.requests] == ["rec_chunk_01.mp3", "rec_chunk_02.mp3"]


def test_a_failed_chunk_with_parallel_workers_stops_what_is_not_running_yet(tmp_path):
    files, metadata = _chunks(tmp_path, 8)
    first_failed = threading.Event()
    sent: list[str] = []
    lock = threading.Lock()

    def call_gpt4o_api(path):
        with lock:
            sent.append(Path(path).name)
        if Path(path).name == "rec_chunk_01.mp3":
            first_failed.set()
            raise RuntimeError("GPT-4o transcription failed (HTTP 401)")
        first_failed.wait(timeout=5)  # the other running chunk finishes after the failure
        return {"segments": []}

    transcriber = ParallelTranscriber(
        {"provider": "azure", "api_key": "k", "azure_endpoint": _AUDIO, "api_version": "v"},
        TranscriptionConfig(model=TranscriptionModel.GPT4O_DIARIZE),
    )
    transcriber._call_gpt4o_api = call_gpt4o_api

    with pytest.raises(RuntimeError, match="HTTP 401"):
        transcriber._transcribe_chunks_gpt4o(files, metadata, 2, None, None)

    # Two ran at once; at most one more could start before the failure was seen.
    assert len(sent) <= 3


def test_a_failed_whisper_local_chunk_stops_the_queued_ones(tmp_path):
    files, metadata = _chunks(tmp_path, 4)
    sent: list[str] = []

    def call_local(path):
        sent.append(Path(path).name)
        raise ConnectionError("server down")

    transcriber = ParallelTranscriber(
        {
            "api_base": "http://whisper.example.com:8080",
            "key": "k",
            "allowed_endpoint_hosts": ["http://whisper.example.com"],
        },
        TranscriptionConfig(model=TranscriptionModel.WHISPER_LOCAL),
    )
    transcriber._call_whisper_local_api = call_local

    with pytest.raises(ConnectionError):
        transcriber._transcribe_chunks_whisper_local(files, metadata, 1, None, None)

    assert sent == ["rec_chunk_01.mp3"]


def test_cancelling_stops_the_queued_chunks(tmp_path):
    from gaik.software_components.parallel_transcriber import (
        SimpleCancellation,
        TranscriptionCancelled,
    )

    files, metadata = _chunks(tmp_path, 4)
    cancel = SimpleCancellation()
    client = _FakeAudioClient([])

    def first_then_cancel(**kwargs):
        cancel.cancel()
        return "1\n00:00:00,000 --> 00:00:01,000\nx\n"

    client.audio.transcriptions.create = first_then_cancel
    transcriber = _whisper("whisper", client)

    with pytest.raises(TranscriptionCancelled):
        transcriber._transcribe_chunks_whisper(files, metadata, 1, cancel.check, None)
