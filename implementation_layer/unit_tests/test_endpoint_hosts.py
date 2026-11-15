"""A credential goes only to https on the provider's host, a deployment-set host or this machine."""

from __future__ import annotations

import logging

import pytest
from gaik.software_components import endpoints
from gaik.software_components.config import create_openai_client
from gaik.software_components.endpoints import (
    EndpointNotAllowedError,
    check_endpoint,
    foundry_host,
)

_ENDPOINT_ENVS = {name for names in endpoints.PROVIDER_ENDPOINT_ENVS.values() for name in names} | {
    endpoints.ALLOWED_HOSTS_ENV,
    "LLM_PROVIDER",
}


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    for name in _ENDPOINT_ENVS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(endpoints, "_logged", set())


@pytest.mark.parametrize(
    ("provider", "url"),
    [
        ("openai", "https://api.openai.com/v1"),
        ("azure", "https://res.openai.azure.com"),
        ("azure", "https://res.cognitiveservices.azure.com/openai/deployments/tts/audio/speech"),
        ("azure", "https://res.services.ai.azure.com"),
        ("aitta", "https://aitta-api.csc.fi/openai/v1"),
        ("vertex", "https://europe-north1-aiplatform.googleapis.com/v1/projects/p/models/m"),
        ("vertex", "https://aiplatform.googleapis.com/v1/projects/p/models/m"),
        ("jev", "https://api.typesafe.ai"),
        ("litellm", "https://res.openai.azure.com"),
    ],
)
def test_provider_hosts_over_https_are_accepted(provider, url):
    assert check_endpoint(url, provider=provider)


@pytest.mark.parametrize(
    ("provider", "url"),
    [
        ("openai", "https://other.example.test/v1"),
        ("azure", "https://openai.azure.com.example.test"),
        ("azure", "https://evilopenai.azure.com"),
        ("azure", "https://res.openai.azure.com@other.example.test"),
        ("openai_compatible", "https://inference.example.test/v1"),
        ("docling", "https://docling.example.test"),
        ("vertex", "https://aiplatform.googleapis.com.example.test/v1"),
        ("openai", "ftp://api.openai.com"),
        ("openai", "api.openai.com"),
        ("openai", ""),
    ],
)
def test_other_hosts_and_schemes_are_refused(provider, url):
    with pytest.raises(EndpointNotAllowedError):
        check_endpoint(url, provider=provider)


def test_plain_http_is_refused_even_for_a_provider_host():
    with pytest.raises(EndpointNotAllowedError, match="https"):
        check_endpoint("http://res.openai.azure.com", provider="azure")


@pytest.mark.parametrize(
    "url", ["http://localhost:11434/v1", "http://127.0.0.1:8000", "http://[::1]:8080"]
)
def test_this_machine_is_accepted_over_http_for_local_models(url):
    assert check_endpoint(url, provider="openai_compatible")


def test_allowed_hosts_env_accepts_names_and_patterns(monkeypatch):
    monkeypatch.setenv("GAIK_ALLOWED_ENDPOINT_HOSTS", "llm.example.test, *.corp.example.test")
    assert check_endpoint("https://llm.example.test/v1", provider="openai_compatible")
    assert check_endpoint("https://a.corp.example.test", provider="docling")
    with pytest.raises(EndpointNotAllowedError):
        check_endpoint("https://corp.example.test", provider="docling")
    with pytest.raises(EndpointNotAllowedError, match="https"):
        check_endpoint("http://llm.example.test", provider="openai_compatible")


def test_an_http_entry_accepts_plain_http_for_that_host_only(monkeypatch):
    monkeypatch.setenv("GAIK_ALLOWED_ENDPOINT_HOSTS", "http://docling.internal:8080")
    assert check_endpoint("http://docling.internal:8080", provider="docling") == "docling.internal"
    with pytest.raises(EndpointNotAllowedError):
        check_endpoint("http://other.internal", provider="docling")


def test_application_allow_list_is_accepted_beside_the_env():
    assert check_endpoint(
        "https://llm.example.test", provider="openai_compatible", allowed_hosts=["llm.example.test"]
    )


def test_a_host_set_in_the_provider_env_is_trusted_for_that_provider_only(monkeypatch):
    monkeypatch.setenv("AZURE_ENDPOINT", "https://gateway.example.test")
    assert check_endpoint("https://gateway.example.test/openai", provider="azure")
    with pytest.raises(EndpointNotAllowedError):
        check_endpoint("https://gateway.example.test", provider="openai")


def test_openai_client_refuses_a_forwarded_base_url_for_the_environment_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    with pytest.raises(EndpointNotAllowedError, match="other.example.test"):
        create_openai_client(
            {"provider": "openai", "api_key": "env-key", "base_url": "https://other.example.test"}
        )


def test_azure_client_refuses_an_endpoint_outside_azure():
    with pytest.raises(EndpointNotAllowedError):
        create_openai_client(
            {
                "provider": "azure",
                "api_key": "k",
                "api_version": "v",
                "azure_endpoint": "https://other.example.test",
            }
        )


def test_client_construction_logs_provider_and_host_without_the_key(caplog):
    with caplog.at_level(logging.INFO, logger="gaik.software_components.endpoints"):
        create_openai_client(
            {
                "provider": "azure",
                "api_key": "secret-value",
                "api_version": "v",
                "azure_endpoint": "https://res.openai.azure.com",
            }
        )
        create_openai_client(
            {
                "provider": "azure",
                "api_key": "secret-value",
                "api_version": "v",
                "azure_endpoint": "https://res.openai.azure.com",
            }
        )
    lines = [r.getMessage() for r in caplog.records if "endpoint host" in r.getMessage()]
    assert lines == ["gaik client: provider=azure endpoint host=res.openai.azure.com"]
    assert "secret-value" not in caplog.text


def test_default_provider_choice_is_logged(caplog, monkeypatch):
    from gaik.software_components.llm import providers

    monkeypatch.setattr(providers, "_logged", set())
    with caplog.at_level(logging.INFO, logger="gaik.software_components.llm.providers"):
        assert providers.resolve_provider() == "azure"
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        assert providers.resolve_provider() == "openai"
    assert "chosen by default" in caplog.text
    assert "'openai' chosen by LLM_PROVIDER" in caplog.text


@pytest.mark.parametrize("resource", ["my-resource", "Res1"])
def test_foundry_resource_names_one_azure_host(resource):
    assert foundry_host(resource) == f"{resource.lower()}.services.ai.azure.com"


@pytest.mark.parametrize(
    "resource", ["other.example.test/#", "other.example.test?", "a.b", "user@host", "", "-x"]
)
def test_foundry_resource_that_names_another_host_is_refused(resource):
    with pytest.raises(EndpointNotAllowedError):
        foundry_host(resource)


def test_litellm_refuses_a_base_url_outside_known_providers():
    pytest.importorskip("litellm")
    from gaik.software_components.llm.litellm_provider import LiteLLMProvider

    with pytest.raises(EndpointNotAllowedError):
        LiteLLMProvider({"model": "azure/x", "api_key": "k", "base_url": "https://o.example.test"})


def test_vision_parser_refuses_an_openai_base_url_elsewhere():
    from gaik.software_components.parsers.vision import VisionParser

    with pytest.raises(EndpointNotAllowedError):
        VisionParser(
            {"provider": "openai", "model": "m", "api_key": "k", "base_url": "https://o.test"}
        )


def test_docling_client_checks_api_base_when_built():
    from gaik.software_components.parsers.docling_api_client import DoclingApiClientParser

    with pytest.raises(EndpointNotAllowedError, match="https"):
        DoclingApiClientParser(api_base="http://docling.example.test", password="p")
    parser = DoclingApiClientParser(
        api_base="https://docling.example.test",
        password="p",
        allowed_endpoint_hosts="docling.example.test",
    )
    assert parser.api_base == "https://docling.example.test"


def test_jev_classifier_refuses_an_unknown_base_url():
    pytest.importorskip("typesafe_sdk")
    from gaik.software_components.jev_classifier import JevClassifier

    with pytest.raises(EndpointNotAllowedError):
        JevClassifier(api_key="k", base_url="https://other.example.test")


def test_jev_classifier_trusts_the_decide_url_from_the_environment(monkeypatch):
    pytest.importorskip("typesafe_sdk")
    from gaik.software_components.jev_classifier import JevClassifier

    monkeypatch.setenv("GAIK_DECIDE_URL", "https://decide.example.test")
    assert JevClassifier(api_key="k", base_url="https://decide.example.test").client


def test_transcriber_refuses_a_local_api_base_when_built(tmp_path):
    from gaik.software_components.transcriber import Transcriber

    with pytest.raises(EndpointNotAllowedError):
        Transcriber(
            {"provider": "openai", "api_key": "k"},
            output_dir=tmp_path,
            transcription_model="whisper_local",
            local_api_base="http://whisper.example.test",
            local_api_key="k",
        )


def test_whisper_local_function_refuses_before_reading_the_file(tmp_path):
    from gaik.software_components.transcriber import whisper_local

    with pytest.raises(EndpointNotAllowedError):
        whisper_local.transcribe(tmp_path / "missing.wav", api_base="http://w.test", key="k")


def test_parallel_transcriber_refuses_an_audio_endpoint_outside_azure():
    from gaik.software_components.parallel_transcriber import ParallelTranscriber

    with pytest.raises(EndpointNotAllowedError):
        ParallelTranscriber(
            {
                "provider": "azure",
                "api_key": "k",
                "azure_endpoint": "https://res.openai.azure.com",
                "azure_audio_endpoint": "https://audio.example.test",
            }
        )


def test_parallel_transcriber_refuses_a_whisper_server_over_plain_http():
    from gaik.software_components.parallel_transcriber import (
        ParallelTranscriber,
        TranscriptionConfig,
        TranscriptionModel,
    )

    with pytest.raises(EndpointNotAllowedError):
        ParallelTranscriber(
            {"api_base": "http://whisper.example.test", "key": "k"},
            TranscriptionConfig(model=TranscriptionModel.WHISPER_LOCAL),
        )


class _Response:
    content = b"audio"

    def raise_for_status(self):
        return None


def test_azure_speech_uses_the_callers_endpoint_and_key(monkeypatch):
    from gaik.software_components.text_to_speech import text_to_speech

    monkeypatch.setenv("TTS_ENDPOINT", "https://env-res.openai.azure.com/speech")
    monkeypatch.setenv("AZURE_API_KEY", "env-key")
    seen = {}

    def post(url, headers=None, json=None, timeout=None):
        seen["url"], seen["key"] = url, headers["api-key"]
        return _Response()

    monkeypatch.setattr(text_to_speech.requests, "post", post)
    speaker = text_to_speech.TextToSpeech(
        {
            "use_azure": True,
            "api_key": "caller-key",
            "tts_endpoint": "https://caller-res.openai.azure.com/speech",
        }
    )
    speaker.synthesize("Hei")
    assert seen == {"url": "https://caller-res.openai.azure.com/speech", "key": "caller-key"}


def test_azure_speech_refuses_an_endpoint_outside_azure_when_built():
    from gaik.software_components.text_to_speech import TextToSpeech

    with pytest.raises(EndpointNotAllowedError):
        TextToSpeech(
            {"use_azure": True, "api_key": "k", "tts_endpoint": "https://other.example.test/s"}
        )
