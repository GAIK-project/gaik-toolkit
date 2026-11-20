"""The given local file is decoded by gaik's own ffmpeg call, which opens only that file.

The real pydub code runs; only the ffmpeg and ffprobe processes it starts are
replaced, so each test sees the exact command lines and stdin pydub would use.
The provider is an ``httpx.MockTransport``, so no request leaves the test.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import wave
from pathlib import Path

import httpx
import pydub.utils
import pytest
from gaik.software_components import input_limits
from gaik.software_components.input_limits import InputLimitError, InputLimits
from gaik.software_components.transcriber import transcriber as module

# A relative name that ffmpeg and ffprobe would read as a protocol address.
RECORDING_NAME = "http:recording.mp3"
SECONDS = 3


def _wav_bytes(seconds: int = SECONDS) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(b"\x00\x00" * 8000 * seconds)
    return buffer.getvalue()


class _MediaTools:
    """Stands in for every ffmpeg and ffprobe process and records how it was started."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], bytes | None]] = []

    def popen(self, args, stdin=None, stdout=None, stderr=None, **kwargs):
        tools = self

        class _Process:
            returncode = 0

            def __init__(self) -> None:
                self.args = list(args)

            def communicate(self, input=None, timeout=None):  # noqa: A002 - Popen signature
                tools.calls.append((self.args, input))
                if Path(self.args[0]).name.startswith(("ffprobe", "avprobe")):
                    return b"{}", b""
                if self.args[-1] == "-":  # a decode to WAV on stdout
                    return _wav_bytes(), b""
                return b"", b""  # an export to a file pydub names itself

            def poll(self):
                return self.returncode

            def wait(self, timeout=None):
                return self.returncode

            def kill(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        return _Process()

    def media(self) -> list[tuple[list[str], bytes | None]]:
        """The ffmpeg and ffprobe calls only (other processes, e.g. uname, are left out)."""
        return [
            (args, data)
            for args, data in self.calls
            if Path(args[0]).name.startswith(("ffmpeg", "ffprobe", "avconv", "avprobe"))
        ]

    def decodes(self) -> list[tuple[list[str], bytes | None]]:
        return [(args, data) for args, data in self.media() if args[-1] == "-"]


@pytest.fixture
def media_tools(monkeypatch, tmp_path) -> _MediaTools:
    tools = _MediaTools()
    monkeypatch.setattr(subprocess, "Popen", tools.popen)
    monkeypatch.setattr(pydub.utils, "Popen", tools.popen)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    monkeypatch.chdir(tmp_path)
    return tools


@pytest.fixture
def provider():
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"text": "synthetic transcript"})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        config = {
            "provider": "openai",
            "api_key": "test-key",
            "base_url": "https://api.openai.com/v1",
            "http_client": client,
            "max_retries": 0,
        }
        yield config, requests


def _recording() -> Path:
    path = Path(RECORDING_NAME)
    path.write_bytes(b"synthetic recording bytes")
    return path


def _assert_decodes_open_only_the_absolute_local_path(tools: _MediaTools) -> None:
    """Every decode of the recording opens its absolute path under the file protocol.

    The other media calls are pydub's exports of the chunks, which read a WAV pydub
    wrote itself; they never name the recording.
    """
    absolute = str(Path(RECORDING_NAME).absolute())
    assert tools.decodes(), "nothing was decoded"
    for args, data in tools.decodes():
        assert args[args.index("-protocol_whitelist") + 1] == "file", args
        assert args[args.index("-i") + 1] == absolute, args
        assert data is None  # no pipe input: the whitelist applies to the file
        assert not any(a.startswith(("pipe:", "cache:")) for a in args), args
    for args, _data in tools.media():
        assert not any(a == RECORDING_NAME for a in args), args  # never the bare name
        if args not in [d for d, _ in tools.decodes()]:
            assert absolute not in args, args  # exports read pydub's own files


def test_transcribe_decodes_only_the_absolute_local_path(media_tools, provider):
    config, requests = provider
    transcriber = module.Transcriber(
        config, output_dir="workspace", limits=InputLimits(max_media_seconds=None)
    )
    _recording()

    result = transcriber.transcribe(RECORDING_NAME)

    _assert_decodes_open_only_the_absolute_local_path(media_tools)
    # The duration read and the chunking check each decode the file once.
    assert len(media_tools.decodes()) == 2
    assert result.audio_duration_s == SECONDS
    assert result.raw_transcript == "synthetic transcript"
    assert len(requests) == 1


def test_chunked_transcribe_decodes_only_the_absolute_local_path(media_tools, provider):
    config, requests = provider
    transcriber = module.Transcriber(
        config,
        output_dir="workspace",
        max_duration_seconds=1,
        limits=InputLimits(max_media_seconds=None),
    )
    _recording()

    result = transcriber.transcribe(RECORDING_NAME)

    _assert_decodes_open_only_the_absolute_local_path(media_tools)
    # Duration read, chunking check and the decode the chunks are cut from.
    assert len(media_tools.decodes()) == 3
    assert "synthetic transcript" in result.raw_transcript
    assert len(requests) > 1


def test_split_and_transcribe_decodes_only_the_absolute_local_path(media_tools, provider):
    config, requests = provider
    _recording()

    transcript = module.split_and_transcribe_with_context(
        RECORDING_NAME, config, max_duration_seconds=1, transcription_model="whisper-1"
    )

    _assert_decodes_open_only_the_absolute_local_path(media_tools)
    assert len(media_tools.decodes()) == 1
    assert "synthetic transcript" in transcript
    assert requests


@pytest.mark.parametrize(
    "content",
    [
        b"#EXTM3U\n#EXTINF:1,\nother.mp3\n",
        b"ffconcat version 1.0\nfile other.mp3\n",
        b'<?xml version="1.0"?>\n<MPD xmlns="urn:mpeg:dash:schema:mpd:2011"></MPD>\n',
    ],
    ids=["hls-playlist", "ffconcat-list", "dash-manifest"],
)
def test_split_and_transcribe_refuses_a_playlist_before_any_decode_or_request(
    media_tools, provider, content
):
    config, requests = provider
    Path("talk.mp3").write_bytes(content)

    with pytest.raises(ValueError, match="playlist or file list"):
        module.split_and_transcribe_with_context("talk.mp3", config)

    assert media_tools.calls == []
    assert requests == []


def test_transcribe_refuses_a_name_that_is_not_a_local_file(media_tools, provider):
    config, requests = provider
    transcriber = module.Transcriber(config, output_dir="workspace")

    with pytest.raises(FileNotFoundError):
        transcriber.transcribe("http://example.invalid/recording.mp3")

    assert media_tools.calls == []
    assert requests == []


FFMPEG = shutil.which("ffmpeg")


@pytest.mark.skipif(FFMPEG is None, reason="needs ffmpeg on PATH")
def test_real_ffmpeg_decodes_a_wav_and_opens_no_stream_a_file_names(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("speech.wav").write_bytes(_wav_bytes(2))
    assert len(module._decode_audio("speech.wav")) == 2000

    # A session description names network streams; under the file-only whitelist
    # ffmpeg refuses to open them instead of connecting.
    Path("call.mp3").write_text(
        "v=0\no=- 0 0 IN IP4 127.0.0.1\ns=x\nc=IN IP4 127.0.0.1\nt=0 0\nm=audio 9 RTP/AVP 0\n"
    )
    with pytest.raises(subprocess.CalledProcessError) as refused:
        module._decode_audio("call.mp3")
    assert b"whitelist" in refused.value.stderr or b"not on whitelist" in refused.value.stderr


def test_a_wav_over_the_duration_limit_is_refused_without_ffmpeg(tmp_path, monkeypatch, provider):
    # Neither ffprobe nor ffmpeg is installed: the WAV is still read in Python, so
    # its duration is known and the limit holds before any request.
    config, requests = provider
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(input_limits.shutil, "which", lambda _name: None)
    monkeypatch.setattr(module.AudioSegment, "converter", str(tmp_path / "no-ffmpeg"))
    Path("speech.wav").write_bytes(_wav_bytes(3))
    transcriber = module.Transcriber(
        config, output_dir="workspace", limits=InputLimits(max_media_seconds=2)
    )

    with pytest.raises(InputLimitError, match="max_media_seconds"):
        transcriber.transcribe("speech.wav")

    assert requests == []


def test_a_wav_is_read_without_ffmpeg(tmp_path, monkeypatch):
    monkeypatch.setattr(module.AudioSegment, "converter", str(tmp_path / "no-ffmpeg"))
    wav = tmp_path / "speech.mp3"  # the content decides, not the extension
    wav.write_bytes(_wav_bytes(2))

    assert len(module._decode_audio(wav)) == 2000
