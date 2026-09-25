"""Audio credentials belong to one operation, never the global OpenAI SDK."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Lock
from unittest.mock import MagicMock

import httpx
import openai
import pytest
from gaik.software_components.transcriber import transcriber as module


class _Audio:
    def __len__(self):
        return 2000

    def __getitem__(self, _slice):
        return self

    def export(self, path, format):  # noqa: A002 - PyDub signature
        Path(path).write_bytes(b"synthetic audio")


@pytest.mark.parametrize("chunked", [False, True])
def test_concurrent_audio_requests_keep_keys_isolated(tmp_path, monkeypatch, chunked):
    monkeypatch.setattr(openai, "api_key", "unchanged-global-key")
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    barrier = Barrier(2)
    lock = Lock()
    observed = []

    def respond(request):
        barrier.wait(timeout=5)
        authorization = request.headers["authorization"]
        with lock:
            observed.append(authorization)
        return httpx.Response(200, json={"text": authorization.removeprefix("Bearer ")})

    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"synthetic audio")
    # An injected transport is owned by the caller and may span more than one
    # attachment or a following transcript-enhancement call.
    with httpx.Client(transport=httpx.MockTransport(respond)) as transport:

        def transcribe(key):
            config = {
                "provider": "openai",
                "api_key": key,
                "base_url": "https://api.openai.com/v1",
                "http_client": transport,
                "max_retries": 0,
            }
            if chunked:
                return module.split_and_transcribe_with_context(
                    str(audio),
                    config,
                    max_duration_seconds=1,
                    audio=_Audio(),
                    transcription_model="whisper-1",
                )
            transcriber = module.Transcriber(config, output_dir=tmp_path / key)
            return transcriber._single_pass_transcription(audio, "", "whisper-1")

        with ThreadPoolExecutor(max_workers=2) as executor:
            first, second = executor.map(transcribe, ["first-key", "second-key"])
        assert "first-key" in first and "second-key" not in first
        assert "second-key" in second and "first-key" not in second
        assert set(observed) == {"Bearer first-key", "Bearer second-key"}
        assert not transport.is_closed
    assert openai.api_key == "unchanged-global-key"


def test_azure_audio_uses_explicit_provider_endpoint_and_transport(tmp_path):
    observed = []

    def respond(request):
        observed.append(request)
        return httpx.Response(200, json={"text": "synthetic transcript"})

    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"synthetic audio")
    with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
        config = {
            "provider": "azure",
            "use_azure": False,  # Explicit provider takes precedence.
            "api_key": "azure-test-key",
            "azure_endpoint": "https://chat-resource.openai.azure.com",
            "azure_audio_endpoint": "https://audio-resource.openai.azure.com/openai/v1",
            "base_url": "https://unused-resource.openai.azure.com/openai/v1",
            "api_version": "2025-03-01-preview",
            "http_client": transport,
            "timeout": 17.0,
            "max_retries": 0,
        }
        transcriber = module.Transcriber(config, output_dir=tmp_path)
        result = transcriber._single_pass_transcription(audio, "", "audio-deployment")
        assert result == "synthetic transcript"
        assert not transport.is_closed
        assert len(observed) == 1
        request = observed[0]
        assert request.url.host == "audio-resource.openai.azure.com"
        assert "/deployments/audio-deployment/audio/transcriptions" in request.url.path
        assert request.url.params["api-version"] == "2025-03-01-preview"
        assert request.headers["api-key"] == "azure-test-key"
        assert request.extensions["timeout"]["read"] == 17.0


def test_audio_retries_honor_request_config(tmp_path):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(500, json={"error": {"message": "synthetic failure"}})

    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"synthetic audio")
    with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
        transcriber = module.Transcriber(
            {
                "provider": "openai",
                "api_key": "test-key",
                "http_client": transport,
                "max_retries": 0,
            },
            output_dir=tmp_path,
        )
        with pytest.raises(openai.InternalServerError):
            transcriber._single_pass_transcription(audio, "", "whisper-1")
        assert len(requests) == 1
        assert not transport.is_closed


@pytest.mark.parametrize("chunked", [False, True])
def test_owned_audio_client_is_closed_on_failure(tmp_path, monkeypatch, capsys, chunked):
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"synthetic audio")
    client = MagicMock()
    client.audio.transcriptions.create.side_effect = RuntimeError("do-not-log-this-key")
    monkeypatch.setattr(module, "create_openai_client", lambda _: client)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    config = {"provider": "openai", "api_key": "test-key"}
    if chunked:
        module.split_and_transcribe_with_context(str(audio), config, audio=_Audio())
        assert "do-not-log-this-key" not in capsys.readouterr().out
    else:
        transcriber = module.Transcriber(config, output_dir=tmp_path)
        with pytest.raises(RuntimeError):
            transcriber._single_pass_transcription(audio, "", "whisper-1")
    client.close.assert_called_once()


def test_chunked_audio_rejects_aitta_before_opening_a_client(monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr(module, "create_openai_client", factory)
    with pytest.raises(NotImplementedError, match="only supports OpenAI/Azure"):
        module.split_and_transcribe_with_context(
            "not-needed.wav", {"provider": "aitta", "api_key": "test-key"}
        )
    factory.assert_not_called()
