"""ParallelTranscriber backends: the Azure audio client, the request format each model
takes, stopping the queued chunks after a failure, and refusing a file that is not media.

No test calls a provider: the SDK client and the HTTP posts are fakes.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from gaik.software_components.input_limits import InputLimitError, InputLimits
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
    ("endpoint", "expected"),
    [
        # A gateway keeps its own path; only the SDK's part at the end is cut.
        (
            "https://gw.example.com/openai/azure-prod/openai/v1",
            "https://gw.example.com/openai/azure-prod",
        ),
        (
            "https://gw.example.com/openai/prod/openai/deployments/whisper/audio/transcriptions"
            "?api-version=2024-06-01",
            "https://gw.example.com/openai/prod",
        ),
        # A bare /openai is cut on an Azure host only: elsewhere it can be the gateway's.
        ("https://gw.example.com/openai", "https://gw.example.com/openai"),
        ("https://gw.example.com/openai/", "https://gw.example.com/openai"),
        ("https://gw.example.com/openai-proxy", "https://gw.example.com/openai-proxy"),
        ("https://R.OPENAI.AZURE.COM/OpenAI/V1", "https://R.OPENAI.AZURE.COM"),
        ("https://r.cognitiveservices.azure.com/OPENAI", "https://r.cognitiveservices.azure.com"),
        # Azure Government, Azure China and API Management are Azure hosts too.
        ("https://x.openai.azure.us/openai", "https://x.openai.azure.us"),
        ("https://x.openai.azure.cn/openai/", "https://x.openai.azure.cn"),
        ("https://x.azure-api.net/openai", "https://x.azure-api.net"),
        ("https://x.azure-api.net/team/openai", "https://x.azure-api.net/team"),
    ],
)
def test_both_transcribers_keep_a_gateway_path(endpoint, expected):
    from gaik.software_components.transcriber.transcriber import (
        _azure_resource_endpoint as transcriber_cut,
    )

    assert pipeline._azure_resource_endpoint(endpoint) == expected
    assert transcriber_cut(endpoint) == expected


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


def test_a_v1_base_url_gives_the_resource_unless_another_endpoint_is_given():
    config = {
        "provider": "azure",
        "api_key": "test-key",
        "base_url": f"{_CHAT}/openai/v1",
        "api_version": "2025-03-01-preview",
    }

    from_base_url = ParallelTranscriber(config)._whisper_client_config()
    audio = ParallelTranscriber(
        {**config, "azure_audio_endpoint": f"{_AUDIO}/openai/v1"}
    )._whisper_client_config()

    assert "base_url" not in from_base_url and from_base_url["azure_endpoint"] == _CHAT
    assert "base_url" not in audio and audio["azure_endpoint"] == _AUDIO


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        ({}, _CHAT),
        ({"azure_endpoint": _AUDIO}, _AUDIO),
        ({"azure_endpoint": _CHAT, "azure_audio_endpoint": _AUDIO}, _AUDIO),
    ],
)
def test_both_transcribers_pick_the_same_azure_address(extra, expected):
    # Audio endpoint, then azure_endpoint, then base_url, in both.
    from gaik.software_components.transcriber import transcriber as module

    config = {
        "provider": "azure",
        "api_key": "test-key",
        "base_url": f"{_CHAT}/openai/v1",
        "api_version": "2025-03-01-preview",
        **extra,
    }

    parallel = ParallelTranscriber(config)._make_whisper_client()
    sequential = module._create_audio_client(config)
    try:
        assert str(parallel.base_url) == str(sequential.base_url) == f"{expected}/openai/"
    finally:
        parallel.close()
        sequential.close()


def _transcription_requests(respond):
    import httpx

    requests: list = []

    def record(request):
        requests.append(request)
        return respond(request)

    return requests, httpx.Client(transport=httpx.MockTransport(record))


def test_a_v1_base_url_sends_whisper_to_the_deployment_route(tmp_path):
    import httpx

    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"\x00" * 10)
    srt = "1\n00:00:00,000 --> 00:00:01,000\nHei\n"
    requests, transport = _transcription_requests(
        lambda _r: httpx.Response(200, text=srt, headers={"content-type": "text/plain"})
    )
    with transport:
        transcriber = ParallelTranscriber(
            {
                "provider": "azure",
                "api_key": "test-key",
                "base_url": f"{_CHAT}/openai/v1",
                "api_version": "2025-03-01-preview",
                "transcription_model": "whisper",
                "http_client": transport,
                "max_retries": 0,
            },
            TranscriptionConfig(max_retries=0, max_429_retries=0),
        )
        assert transcriber._call_whisper_single(audio) == srt

    assert requests[0].url.host == "chat-resource.openai.azure.com"
    assert requests[0].url.path == "/openai/deployments/whisper/audio/transcriptions"
    assert requests[0].url.params["api-version"] == "2025-03-01-preview"


def test_the_transcriber_sends_a_v1_base_url_to_the_deployment_route(tmp_path):
    import httpx
    from gaik.software_components.transcriber.transcriber import Transcriber

    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"\x00" * 10)
    requests, transport = _transcription_requests(
        lambda _r: httpx.Response(200, json={"text": "Hei"})
    )
    with transport:
        transcriber = Transcriber(
            {
                "provider": "azure",
                "api_key": "test-key",
                "base_url": f"{_CHAT}/openai/v1",
                "api_version": "2025-03-01-preview",
                "http_client": transport,
                "max_retries": 0,
            },
            output_dir=tmp_path / "w",
        )
        assert transcriber._single_pass_transcription(audio, None, "whisper") == "Hei"

    assert requests[0].url.host == "chat-resource.openai.azure.com"
    assert requests[0].url.path == "/openai/deployments/whisper/audio/transcriptions"


def test_an_api_version_of_none_gets_the_default():
    from gaik.software_components.transcriber import transcriber as module

    config = {"provider": "azure", "api_key": "k", "azure_endpoint": _AUDIO, "api_version": None}

    assert ParallelTranscriber(config)._whisper_client_config()["api_version"] == (
        "2024-12-01-preview"
    )
    client = module._create_audio_client(config)
    try:
        assert client._api_version == "2024-12-01-preview"
    finally:
        client.close()


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
        # A Whisper deployment with gpt in its name keeps its timestamps.
        ("gpt-whisper", "srt"),
        ("transcribe-prod", "srt"),
    ],
)
def test_each_model_is_asked_for_a_format_it_supports(model, expected):
    transcriber = _whisper(model, _FakeAudioClient([]))

    assert transcriber._whisper_request(model, file=None)["response_format"] == expected


@pytest.mark.parametrize(
    ("model", "chosen", "expected"),
    [("transcribe-prod", "json", "json"), ("gpt-4o-transcribe", "srt", "srt")],
)
def test_the_request_format_can_be_set_for_a_name_that_says_neither(model, chosen, expected):
    transcriber = _whisper(model, _FakeAudioClient([]), whisper_request_format=chosen)

    assert transcriber._whisper_request(model, file=None)["response_format"] == expected


def test_a_request_format_other_than_srt_or_json_is_refused():
    with pytest.raises(ValueError, match="whisper_request_format"):
        ParallelTranscriber({"api_key": "k"}, TranscriptionConfig(whisper_request_format="vtt"))


def test_the_request_format_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("WHISPER_REQUEST_FORMAT", "json")

    assert TranscriptionConfig.from_env().whisper_request_format == "json"


def _long_whisper_run(tmp_path, monkeypatch, model: str, seconds: float, **config):
    """Transcribe a small file of ``seconds`` on the Whisper backend; returns the
    split_audio keyword arguments, or None when it went in a single request."""
    audio = tmp_path / "meeting.mp3"
    audio.write_bytes(b"\x00" * 1000)
    monkeypatch.setattr(pipeline, "get_audio_duration", lambda _p: seconds)
    monkeypatch.setattr(pipeline, "has_video_stream", lambda _p: False)
    splits: list[dict] = []

    def split(path, **kwargs):
        splits.append(kwargs)
        return ["c1.mp3", "c2.mp3"], [{"nominal_start": 0}, {"nominal_start": 1200}]

    monkeypatch.setattr(pipeline, "split_audio", split)
    transcriber = ParallelTranscriber(
        {"api_key": "k", "transcription_model": model},
        TranscriptionConfig(**config),
        limits=InputLimits.unlimited(),
    )
    srt = "1\n00:00:00,000 --> 00:00:01,000\nx\n"
    transcriber._transcribe_single = lambda *a: SimpleNamespace(single=True)
    transcriber._transcribe_chunks_whisper = lambda *a: srt
    transcriber._cleanup_chunks = lambda *a: None
    result = transcriber.transcribe(audio)
    return None if getattr(result, "single", False) else splits[0]


def test_a_gpt4o_model_on_the_whisper_backend_is_split_under_1400_seconds(tmp_path, monkeypatch):
    # 30 minutes in a small file: one request would be over GPT-4o's 1400 s limit.
    split = _long_whisper_run(
        tmp_path, monkeypatch, "gpt-4o-transcribe", 1800.0, chunk_duration_minutes=30
    )

    assert split is not None
    # A middle chunk is chunk + 2 x 15 s of overlap: 22 minutes keeps it under 1400 s.
    assert split["chunk_duration_minutes"] == 22


def test_whisper_still_sends_a_long_small_file_in_one_request(tmp_path, monkeypatch):
    assert _long_whisper_run(tmp_path, monkeypatch, "whisper", 1800.0) is None


@pytest.mark.parametrize("model", [None, ""], ids=["none", "empty"])
def test_a_transcription_model_left_empty_in_the_config_is_whisper(tmp_path, monkeypatch, model):
    # {"transcription_model": None} is what a config built from an unset variable has.
    assert _long_whisper_run(tmp_path, monkeypatch, model, 1800.0) is None

    audio = tmp_path / "note.mp3"
    audio.write_bytes(b"\x00" * 10)
    srt = "1\n00:00:00,000 --> 00:00:01,000\nHello\n"
    client = _FakeAudioClient([srt])

    # On OpenAI the Whisper model id is whisper-1, as Transcriber sends it.
    assert _whisper(model, client)._call_whisper_single(audio) == srt
    assert client.requests[0]["model"] == "whisper-1"
    assert client.requests[0]["response_format"] == "srt"


@pytest.mark.parametrize("model", [None, ""], ids=["none", "empty"])
def test_an_empty_transcription_model_on_azure_is_the_whisper_deployment(model):
    azure = ParallelTranscriber(
        {"provider": "azure", "api_key": "k", "azure_endpoint": _CHAT, "transcription_model": model}
    )
    left_out = ParallelTranscriber({"provider": "azure", "api_key": "k", "azure_endpoint": _CHAT})

    assert azure._get_whisper_deployment() == "whisper"
    assert left_out._get_whisper_deployment() == "whisper"


def test_a_named_whisper_model_is_sent_as_named():
    openai = ParallelTranscriber({"api_key": "k", "transcription_model": "whisper"})

    # An explicit name is the caller's: a self-hosted server may serve "whisper".
    assert openai._get_whisper_deployment() == "whisper"


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
            # The shared speech ends chunk 1 with a word cut in half ("s").
            "rec_chunk_01.mp3": SimpleNamespace(
                text="Alku on tässä. Potilas tuli vastaanotolle aamulla ja kertoi, että "
                "hammas 36 oireili kylmälle ja kuumalle, joten se tutkittiin ja s"
            ),
            "rec_chunk_02.mp3": SimpleNamespace(
                text="tuli vastaanotolle aamulla ja kertoi, että hammas 36 oireili "
                "kylmälle ja kuumalle, joten se tutkittiin ja paikattiin."
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
        "Alku on tässä. Potilas tuli vastaanotolle aamulla ja kertoi, että hammas 36 "
        "oireili kylmälle ja kuumalle, joten se tutkittiin ja paikattiin."
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


def test_the_following_chunks_version_of_the_overlap_is_kept():
    # x and y are the words cut in half where the chunks end and start.
    previous = "a b c one two three four five x".split()
    following = "y one two three four five six seven".split()

    kept_previous, kept_following = pipeline._drop_repeated_words(previous, following, 30.0)

    assert (kept_previous, kept_following) == ("a b c".split(), following)


def test_one_word_heard_differently_in_the_overlap_does_not_repeat_it():
    # 10 s shared; the two chunks heard the year differently.
    previous = (
        "alpha we agreed that the report would be in 2023 and then we moved on to the budget"
    ).split()
    following = (
        "we agreed that the report would be in 2024 and then we moved on to the budget next item"
    ).split()

    kept_previous, kept_following = pipeline._drop_repeated_words(previous, following, 10.0)

    assert (kept_previous, kept_following) == (["alpha"], following)


def test_a_phrase_said_again_elsewhere_is_not_taken_for_the_overlap():
    # The longest common run is "sanotaan tämä on tärkeä asia", said twice, but the
    # chunks' shared speech is "loppu on tässä lopussa", at the edges where they meet.
    previous = "alku keskellä sanotaan tämä on tärkeä asia ja loppu on tässä lopussa".split()
    following = "loppu on tässä lopussa sitten sanotaan tämä on tärkeä asia taas".split()

    kept_previous, kept_following = pipeline._drop_repeated_words(previous, following, 30.0)

    assert kept_previous + kept_following == previous + following[4:]


def test_a_phrase_repeated_far_from_the_edges_drops_nothing():
    # Silence in the overlap, and one phrase said before it and again after it.
    phrase = "kuten me aiemmin sovittiin".split()
    previous = [f"a{i}" for i in range(45)] + phrase + [f"p{i}" for i in range(10)]
    following = [f"n{i}" for i in range(10)] + phrase + [f"b{i}" for i in range(45)]

    assert pipeline._drop_repeated_words(previous, following, 30.0) == (previous, following)


def test_a_short_overlap_of_three_words_is_kept_once_when_they_line_up_exactly():
    previous = "a b c one two three".split()
    following = "one two three d e".split()

    assert pipeline._drop_repeated_words(previous, following, 30.0) == ("a b c".split(), following)


def test_three_words_in_common_need_a_ratio_of_0_85():
    # "one two three" are in both, but with "x" and "y" between: a ratio of 0.75.
    previous = "a b c one two three x".split()
    following = "one two y three d".split()

    assert pipeline._drop_repeated_words(previous, following, 30.0) == (previous, following)


def test_a_word_before_the_lined_up_stretch_is_not_dropped():
    # The best-scoring alignment starts at "kauppa", which the next chunk does not have.
    previous = "x kauppa oli päivä yksi hän minä tai kaksi minä".split()
    following = "oli päivä yksi hän minä tai kaksi X minä yksi aika".split()

    kept_previous, kept_following = pipeline._drop_repeated_words(previous, following, 3.0)

    assert (kept_previous, kept_following) == (["x", "kauppa"], following)


def test_a_last_word_heard_differently_and_said_again_next_drops_nothing_real():
    # The previous chunk ends "perjantaina", the next hears "maanantaina" there and then
    # says "perjantaina": only the shared stretch is taken from the next chunk.
    previous = "alku ja sitten sovimme että kokous on perjantaina".split()
    following = "sitten sovimme että kokous on maanantaina perjantaina ja muuta".split()

    kept_previous, kept_following = pipeline._drop_repeated_words(previous, following, 5.0)

    assert (kept_previous, kept_following) == (["alku", "ja"], following)


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

    # Chunks 1 and 2 may run at once; a worker that frees up after chunk 1 failed
    # finds the run stopped, so no later chunk is sent.
    assert sent[0] == "rec_chunk_01.mp3"
    assert set(sent) <= {"rec_chunk_01.mp3", "rec_chunk_02.mp3"}


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


def test_a_cancellation_raised_in_a_chunk_stops_the_queued_ones(tmp_path):
    from gaik.software_components.parallel_transcriber import TranscriptionCancelled

    files, metadata = _chunks(tmp_path, 4)
    client = _FakeAudioClient([])
    sent: list[str] = []

    def cancelled_while_the_first_runs(**kwargs):
        sent.append(Path(kwargs["file"].name).name)
        raise TranscriptionCancelled("cancelled")

    client.audio.transcriptions.create = cancelled_while_the_first_runs
    transcriber = _whisper("whisper", client)

    # No check_cancelled callback, so only the executor can keep chunks 2-4 from
    # being sent after chunk 1 raised.
    with pytest.raises(TranscriptionCancelled):
        transcriber._transcribe_chunks_whisper(files, metadata, 1, None, None)

    assert sent == ["rec_chunk_01.mp3"]


# -- a file that is not media (#227) -----------------------------------------------


def _diarize(limits: InputLimits) -> ParallelTranscriber:
    return ParallelTranscriber(
        {"provider": "azure", "api_key": "k", "azure_endpoint": _AUDIO, "api_version": "v"},
        TranscriptionConfig(model=TranscriptionModel.GPT4O_DIARIZE),
        limits=limits,
    )


def _not_media(tmp_path: Path) -> Path:
    path = tmp_path / "notes.mp3"
    path.write_text("This is a text file, not a recording.\n" * 20, encoding="utf-8")
    return path


def _no_transcription_calls(transcriber, monkeypatch):
    import httpx

    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("a transcription was sent"))
    transcriber._transcribe_single = lambda *a: pytest.fail("a transcription was sent")


@pytest.mark.parametrize(
    ("limits", "error"),
    [(InputLimits(), InputLimitError), (InputLimits.unlimited(), ValueError)],
)
def test_gpt4o_refuses_a_file_ffprobe_cannot_read(tmp_path, monkeypatch, limits, error):
    def unreadable(_path):
        raise subprocess.CalledProcessError(1, ["ffprobe", str(tmp_path)])

    monkeypatch.setattr(pipeline, "get_audio_duration", unreadable)
    monkeypatch.setattr(pipeline, "has_video_stream", lambda _p: False)
    monkeypatch.setattr(pipeline, "has_audio_stream", lambda _p: False)
    # ffprobe is there but cannot read the file (CI has no ffprobe at all).
    monkeypatch.setattr(pipeline.shutil, "which", lambda _name: "/usr/bin/ffprobe")
    transcriber = _diarize(limits)
    _no_transcription_calls(transcriber, monkeypatch)

    with pytest.raises(error, match="cannot read it as audio or video") as raised:
        transcriber.transcribe(_not_media(tmp_path))

    assert not isinstance(raised.value, subprocess.CalledProcessError)
    assert isinstance(raised.value.__cause__, subprocess.CalledProcessError)


def test_a_timeout_reading_the_length_is_named_as_one(tmp_path, monkeypatch):
    def slow(_path):
        raise subprocess.TimeoutExpired("ffprobe", 60)

    monkeypatch.setattr(pipeline, "get_audio_duration", slow)
    monkeypatch.setattr(pipeline, "has_video_stream", lambda _p: False)
    monkeypatch.setattr(pipeline, "has_audio_stream", lambda _p: True)
    monkeypatch.setattr(pipeline.shutil, "which", lambda _name: "/usr/bin/ffprobe")
    transcriber = _diarize(InputLimits.unlimited())
    _no_transcription_calls(transcriber, monkeypatch)

    with pytest.raises(ValueError, match="reading its length timed out"):
        transcriber.transcribe(_not_media(tmp_path))


def test_a_missing_ffprobe_is_named_as_such_not_blamed_on_the_file(tmp_path, monkeypatch):
    def no_ffprobe(_path):
        raise FileNotFoundError(2, "The system cannot find the file specified", "ffprobe")

    monkeypatch.setattr(pipeline, "get_audio_duration", no_ffprobe)
    monkeypatch.setattr(pipeline, "has_video_stream", lambda _p: False)
    monkeypatch.setattr(pipeline, "has_audio_stream", lambda _p: True)
    monkeypatch.setattr(pipeline.shutil, "which", lambda _name: None)
    transcriber = _diarize(InputLimits.unlimited())
    _no_transcription_calls(transcriber, monkeypatch)

    with pytest.raises(ValueError, match="ffprobe is not installed") as raised:
        transcriber.transcribe(_not_media(tmp_path))
    assert "cannot read it as audio or video" not in str(raised.value)


@pytest.mark.skipif(
    shutil.which("ffprobe") is None or shutil.which("ffmpeg") is None,
    reason="needs ffmpeg and ffprobe on PATH",
)
@pytest.mark.parametrize(
    ("limits", "error"),
    [(InputLimits(), InputLimitError), (InputLimits.unlimited(), ValueError)],
)
def test_gpt4o_refuses_a_text_file_with_the_real_ffprobe(tmp_path, monkeypatch, limits, error):
    transcriber = _diarize(limits)
    _no_transcription_calls(transcriber, monkeypatch)

    with pytest.raises(error, match="notes.mp3 cannot be read"):
        transcriber.transcribe(_not_media(tmp_path))
