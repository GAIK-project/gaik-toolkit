"""Transcriber sends ``language`` to cloud models (issue #101)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from gaik.software_components.transcriber.transcriber import (
    Transcriber,
    split_and_transcribe_with_context,
)

_MODULE = "gaik.software_components.transcriber.transcriber"


class _Chunk:
    def export(self, path, format):  # noqa: A002 - mirrors PyDub's signature
        Path(path).write_bytes(b"chunk")


class _Audio:
    def __init__(self, duration_ms: int) -> None:
        self.duration_ms = duration_ms

    def __len__(self) -> int:
        return self.duration_ms

    def __getitem__(self, item: slice) -> _Chunk:
        return _Chunk()


def _fake_client(requests: list[dict]):
    def create(**kwargs):
        requests.append({key: value for key, value in kwargs.items() if key != "file"})
        return SimpleNamespace(text=f"part {len(requests)}", usage=None)

    return create


def _transcribe(tmp_path: Path, language: str, duration_ms: int) -> list[dict]:
    audio = tmp_path / "talk.mp3"
    audio.write_bytes(b"tiny")
    transcriber = Transcriber(
        api_config={"use_azure": False, "api_key": "test-key"},
        transcription_model="gpt-4o-transcribe",
        language=language,
        max_size_mb=100,
        max_duration_seconds=60,
        enhanced_transcript=False,
    )
    requests: list[dict] = []
    with (
        patch(f"{_MODULE}.create_openai_client") as factory,
        patch(f"{_MODULE}._decode_audio", return_value=_Audio(duration_ms)),
        patch(f"{_MODULE}.time.sleep"),
    ):
        factory.return_value.audio.transcriptions.create.side_effect = _fake_client(requests)
        transcriber.transcribe(audio)
    return requests


# One request for a short file; 150 s in chunks of at most 60 s is three requests.
_REQUESTS = {10_000: 1, 150_000: 3}


@pytest.mark.parametrize("duration_ms", [10_000, 150_000], ids=["single", "chunked"])
def test_language_reaches_every_cloud_request(tmp_path: Path, duration_ms: int):
    requests = _transcribe(tmp_path, "fi", duration_ms)

    assert len(requests) == _REQUESTS[duration_ms]
    assert [request.get("language") for request in requests] == ["fi"] * len(requests)


@pytest.mark.parametrize("duration_ms", [10_000, 150_000], ids=["single", "chunked"])
def test_auto_sends_no_language(tmp_path: Path, duration_ms: int):
    requests = _transcribe(tmp_path, "auto", duration_ms)

    assert len(requests) == _REQUESTS[duration_ms]
    assert all("language" not in request for request in requests)


@pytest.mark.parametrize("language", ["finnish", "FI", "fin", "fi-FI"])
def test_a_language_that_is_not_iso_639_1_fails_before_any_request(tmp_path: Path, language: str):
    with pytest.raises(ValueError, match="ISO-639-1"):
        _transcribe(tmp_path, language, 10_000)


def test_language_is_not_reported_as_an_ignored_local_option(tmp_path: Path, capsys):
    _transcribe(tmp_path, "fi", 10_000)

    assert "ignored" not in capsys.readouterr().out


def test_split_and_transcribe_keeps_working_without_language(tmp_path: Path):
    audio = tmp_path / "long.mp3"
    audio.write_bytes(b"tiny")
    requests: list[dict] = []
    with (
        patch(f"{_MODULE}.create_openai_client") as factory,
        patch(f"{_MODULE}.time.sleep"),
    ):
        factory.return_value.audio.transcriptions.create.side_effect = _fake_client(requests)
        split_and_transcribe_with_context(
            str(audio),
            {"use_azure": False, "api_key": "test-key"},
            max_size_mb=100,
            max_duration_seconds=60,
            audio=_Audio(120_000),
            transcription_model="gpt-4o-transcribe",
        )

    assert len(requests) == 3
    assert all("language" not in request for request in requests)
