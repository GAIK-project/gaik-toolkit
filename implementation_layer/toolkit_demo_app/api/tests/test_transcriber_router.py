"""The transcribe endpoint passes on the timing, subtitles and usage the component makes."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from api.routers import transcriber as route
from fastapi import FastAPI
from fastapi.testclient import TestClient

SEGMENTS = [
    {"start": 0.0, "end": 1.5, "speaker": "UNKNOWN", "text": "Hei"},
    {"start": 1.5, "end": 3.0, "speaker": "UNKNOWN", "text": "maailma"},
]


@pytest.fixture
def client(monkeypatch) -> TestClient:
    class FakeTranscriber:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def transcribe(self, file_path, custom_context=""):
            local = self.kwargs.get("transcription_model") == "whisper_local"
            return SimpleNamespace(
                raw_transcript="Hei maailma",
                enhanced_transcript=None,
                job_id="job-1",
                segments=SEGMENTS if local else None,
                srt_content="1\n00:00:00,000 --> 00:00:01,500\nHei\n" if local else None,
                vtt_content="WEBVTT\n" if local else None,
                duration_s=1.2,
                audio_duration_s=3.0,
                usage={} if local else {"total_tokens": 20},
            )

    monkeypatch.setenv("AZURE_API_KEY", "key")
    monkeypatch.setenv("LOCAL_TRANSCRIBER_API_BASE", "http://local")
    monkeypatch.setenv("LOCAL_TRANSCRIBER_API_KEY", "key")
    monkeypatch.setattr("gaik.software_components.transcriber.Transcriber", FakeTranscriber)
    monkeypatch.setattr(
        "gaik.software_components.transcriber.get_openai_config",
        lambda use_azure=True: {"transcription_model": "cloud-model"},
    )
    app = FastAPI()
    app.include_router(route.router, prefix="/transcribe")
    return TestClient(app)


def _post(client: TestClient, local: bool):
    return client.post(
        "/transcribe",
        files={"file": ("a.mp3", b"audio", "audio/mpeg")},
        data={"prefer_local_first": str(local).lower(), "diarization": "false"},
    )


def test_timed_segments_come_back_without_speaker_detection(client) -> None:
    body = _post(client, True).json()

    assert body["transcription_model"] == "whisper_local"
    assert [s["text"] for s in body["segments"]] == ["Hei", "maailma"]
    assert body["srt_content"].startswith("1\n")
    assert body["vtt_content"] == "WEBVTT\n"
    assert body["audio_duration_s"] == 3.0
    assert body["duration_s"] == 1.2
    assert body["usage"] is None


def test_the_cloud_model_returns_text_and_usage_only(client) -> None:
    body = _post(client, False).json()

    assert body["transcription_model"] == "cloud-model"
    assert body["segments"] is None
    assert body["srt_content"] is None
    assert body["usage"] == {"total_tokens": 20}
