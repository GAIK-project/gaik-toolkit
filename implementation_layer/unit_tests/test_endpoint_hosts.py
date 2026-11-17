"""A credential goes only to https on the provider's host, a deployment-set host or this machine."""

from __future__ import annotations

import logging
from urllib.parse import urlsplit

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
    monkeypatch.setattr(endpoints, "_warned_http", set())


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


@pytest.mark.parametrize(
    ("env", "url", "provider"),
    [
        ("DOCLING_API_BASE", "http://docling.example.test:5001", "docling"),
        ("LOCAL_TRANSCRIBER_API_BASE", "http://whisper.example.test:8080", "whisper_local"),
        ("OPENAI_BASE_URL", "http://llm.example.test/v1", "openai_compatible"),
    ],
)
def test_an_http_address_set_in_the_provider_env_is_used_as_set(monkeypatch, env, url, provider):
    monkeypatch.setenv(env, url)
    assert check_endpoint(url, provider=provider) == urlsplit(url).hostname
    with pytest.raises(EndpointNotAllowedError):
        check_endpoint("http://other.example.test", provider=provider)


def _http_warnings(caplog):
    return [r for r in caplog.records if "without encryption" in r.getMessage()]


@pytest.mark.parametrize(
    "address",
    [
        "http://10.1.2.3:5001",
        "http://172.20.0.4",
        "http://192.168.1.10:8080",
        "http://169.254.10.1",
        "http://[fd12:3456::1]:5001",
        "http://[fe80::1]",
        "http://docling:5001",
        "http://host.docker.internal:5001",
    ],
)
def test_an_http_env_address_on_a_private_network_is_used_without_a_warning(
    monkeypatch, caplog, address
):
    monkeypatch.setenv("DOCLING_API_BASE", address)
    with caplog.at_level(logging.WARNING, logger=endpoints.__name__):
        assert check_endpoint(address, provider="docling") == urlsplit(address).hostname
    assert _http_warnings(caplog) == []


def test_an_http_env_address_on_a_public_name_is_used_with_one_warning(monkeypatch, caplog):
    monkeypatch.setenv("DOCLING_API_BASE", "http://docling.example.test:5001")
    with caplog.at_level(logging.WARNING, logger=endpoints.__name__):
        for _ in range(3):
            assert check_endpoint("http://docling.example.test:5001", provider="docling")
    warnings = _http_warnings(caplog)
    assert len(warnings) == 1
    assert "docling.example.test" in warnings[0].getMessage()


def test_an_https_env_address_is_used_without_a_warning(monkeypatch, caplog):
    monkeypatch.setenv("DOCLING_API_BASE", "https://docling.example.test")
    with caplog.at_level(logging.WARNING, logger=endpoints.__name__):
        assert check_endpoint("https://docling.example.test", provider="docling")
    assert _http_warnings(caplog) == []


def test_an_http_allow_list_entry_is_used_without_a_warning(monkeypatch, caplog):
    monkeypatch.setenv("GAIK_ALLOWED_ENDPOINT_HOSTS", "http://docling.example.test")
    with caplog.at_level(logging.WARNING, logger=endpoints.__name__):
        assert check_endpoint("http://docling.example.test", provider="docling")
    assert _http_warnings(caplog) == []


def test_an_http_address_in_one_provider_env_is_not_used_for_another(monkeypatch):
    monkeypatch.setenv("DOCLING_API_BASE", "http://docling.example.test")
    with pytest.raises(EndpointNotAllowedError):
        check_endpoint("http://docling.example.test", provider="openai_compatible")


def test_openai_base_url_set_with_http_reaches_the_openai_client(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://llm.example.test/v1")
    client = create_openai_client({"provider": "openai", "api_key": "k", "model": "m"})
    assert str(client.base_url).startswith("http://llm.example.test")


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


def test_parallel_transcriber_diarize_refuses_an_audio_endpoint_outside_azure():
    from gaik.software_components.parallel_transcriber import (
        ParallelTranscriber,
        TranscriptionConfig,
        TranscriptionModel,
    )

    with pytest.raises(EndpointNotAllowedError):
        ParallelTranscriber(
            {
                "provider": "azure",
                "api_key": "k",
                "azure_endpoint": "https://res.openai.azure.com",
                "azure_audio_endpoint": "https://audio.example.test",
            },
            TranscriptionConfig(model=TranscriptionModel.GPT4O_DIARIZE),
        )


def test_parallel_transcriber_whisper_checks_the_address_its_client_uses():
    from gaik.software_components.parallel_transcriber import ParallelTranscriber

    # With a base_url the SDK ignores azure_endpoint, so a leftover one does not matter.
    transcriber = ParallelTranscriber(
        {
            "provider": "azure",
            "use_azure": True,
            "api_key": "k",
            "api_version": "2025-03-01-preview",
            "base_url": "https://res.openai.azure.com/openai/v1",
            "azure_endpoint": "https://old.example.test",
        }
    )
    assert transcriber._make_whisper_client()
    other = ParallelTranscriber(
        {
            "provider": "azure",
            "use_azure": True,
            "api_key": "k",
            "api_version": "2025-03-01-preview",
            "azure_endpoint": "https://res.openai.azure.com",
            "azure_audio_endpoint": "https://audio.example.test",
        }
    )
    with pytest.raises(EndpointNotAllowedError):
        other._make_whisper_client()


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


def test_this_machine_is_refused_for_a_cloud_provider_unless_allowed(monkeypatch):
    with pytest.raises(EndpointNotAllowedError, match="this machine"):
        check_endpoint("http://127.0.0.1:9000", provider="openai")
    monkeypatch.setenv("GAIK_ALLOWED_ENDPOINT_HOSTS", "127.0.0.1")
    assert check_endpoint("http://127.0.0.1:9000", provider="openai") == "127.0.0.1"


def test_an_entry_with_a_port_allows_its_host():
    assert check_endpoint(
        "https://llm.example.test:8443/v1",
        provider="openai_compatible",
        allowed_hosts="llm.example.test:8443",
    )


def test_an_http_pattern_entry_accepts_plain_http_for_matching_hosts():
    allowed = "http://*.internal.example.test"
    assert check_endpoint(
        "http://docling.internal.example.test", provider="docling", allowed_hosts=allowed
    )
    with pytest.raises(EndpointNotAllowedError):
        check_endpoint("http://docling.example.test", provider="docling", allowed_hosts=allowed)


def test_the_docling_address_set_in_the_environment_is_trusted(monkeypatch):
    monkeypatch.setenv("DOCLING_API_BASE", "https://docling.example.test")
    assert check_endpoint("https://docling.example.test", provider="docling")


def test_the_older_docling_api_base_name_is_trusted_for_docling_only(monkeypatch):
    monkeypatch.setenv("API_BASE", "http://docling.example.test:8080")
    assert check_endpoint("http://docling.example.test:8080", provider="docling")
    with pytest.raises(EndpointNotAllowedError):
        check_endpoint("http://docling.example.test:8080", provider="openai_compatible")


def test_azure_speech_from_the_environment_keeps_the_environment_key(monkeypatch):
    from gaik.software_components.text_to_speech import text_to_speech

    monkeypatch.setenv("TTS_ENDPOINT", "https://speech-res.openai.azure.com/speech")
    monkeypatch.setenv("AZURE_API_KEY", "speech-key")
    seen = {}

    def post(url, headers=None, json=None, timeout=None):
        seen["url"], seen["key"] = url, headers["api-key"]
        return _Response()

    monkeypatch.setattr(text_to_speech.requests, "post", post)
    speaker = text_to_speech.TextToSpeech({"use_azure": True, "api_key": "chat-key"})
    speaker.synthesize("Hei")
    assert seen == {"url": "https://speech-res.openai.azure.com/speech", "key": "speech-key"}


def test_cloud_transcriber_ignores_an_unused_local_api_base(tmp_path):
    from gaik.software_components.transcriber import Transcriber

    transcriber = Transcriber(
        {"provider": "openai", "api_key": "k"},
        output_dir=tmp_path,
        local_api_base="http://whisper.example.test:8080",
        local_api_key="k",
    )
    assert transcriber.local_api_base == "http://whisper.example.test:8080"


def test_jev_classifier_checks_the_sdk_environment_address(monkeypatch, caplog):
    pytest.importorskip("typesafe_sdk")
    from gaik.software_components.jev_classifier import JevClassifier

    monkeypatch.setenv("TYPESAFE_BASE_URL", "https://typesafe-proxy.example.test")
    with caplog.at_level(logging.INFO, logger="gaik.software_components.endpoints"):
        JevClassifier(api_key="k")
    assert "endpoint host=typesafe-proxy.example.test" in caplog.text


@pytest.mark.parametrize(
    ("provider", "url"),
    [
        ("azure", "https://other.example.test\\@res.openai.azure.com/"),
        ("vertex", "https://other.example.test\\@aiplatform.googleapis.com/v1/x"),
        ("docling", "https://other.example.test\\@localhost"),
        ("azure", "https://user:pw@res.openai.azure.com"),
        ("azure", "https://res.openai.azure.com /x"),
        ("azure", "https://res.openai.azure.com\t/x"),
        ("azure", "https://rés.openai.azure.com"),
    ],
)
def test_urls_that_http_libraries_could_read_differently_are_refused(provider, url):
    with pytest.raises(EndpointNotAllowedError):
        check_endpoint(url, provider=provider)


@pytest.mark.parametrize(
    ("location", "host"),
    [
        ("global", "aiplatform.googleapis.com"),
        ("europe-north1", "europe-north1-aiplatform.googleapis.com"),
    ],
)
def test_vertex_location_names_a_google_host(location, host):
    assert endpoints.vertex_host(location) == host


@pytest.mark.parametrize("location", ["other.example.test?", "x/y", "", "europe north1"])
def test_vertex_location_that_names_another_host_is_refused(location):
    with pytest.raises(EndpointNotAllowedError):
        endpoints.vertex_host(location)
