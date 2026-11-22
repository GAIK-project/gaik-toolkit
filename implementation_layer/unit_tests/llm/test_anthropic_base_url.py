"""An Anthropic ``base_url`` in the config is used, after the endpoint check (#146)."""

import httpx
import pytest
from gaik.software_components import endpoints
from gaik.software_components.endpoints import EndpointNotAllowedError
from gaik.software_components.llm.config import get_llm_config
from gaik.software_components.llm.factory import create_llm_client

pytest.importorskip("anthropic")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for name in ("ANTHROPIC_BASE_URL", endpoints.ALLOWED_HOSTS_ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(endpoints, "_logged", set())


def _reply():
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-test",
        "content": [{"type": "text", "text": "OK"}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


def _client(urls, **config):
    def handle(request):
        urls.append(str(request.url))
        return httpx.Response(200, json=_reply())

    return create_llm_client(
        get_llm_config(
            "anthropic",
            api_key="test-key",
            model="claude-test",
            max_retries=0,
            http_client=httpx.Client(transport=httpx.MockTransport(handle)),
            **config,
        )
    )


def test_a_base_url_in_the_config_receives_the_request(monkeypatch):
    monkeypatch.setenv(endpoints.ALLOWED_HOSTS_ENV, "gateway.example.test")
    urls = []
    client = _client(urls, base_url="https://gateway.example.test/anthropic")
    client.chat([{"role": "user", "content": "Hi"}])
    assert urls == ["https://gateway.example.test/anthropic/v1/messages"]


def test_the_config_base_url_wins_over_the_environment(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://env.example.test")
    monkeypatch.setenv(endpoints.ALLOWED_HOSTS_ENV, "config.example.test")
    urls = []
    _client(urls, base_url="https://config.example.test").chat([{"role": "user", "content": "x"}])
    assert urls[0].startswith("https://config.example.test/")


def test_a_base_url_on_an_unknown_host_is_refused_before_a_request():
    urls = []
    with pytest.raises(EndpointNotAllowedError, match="other.example.test"):
        _client(urls, base_url="https://other.example.test")
    assert urls == []


def test_the_host_of_anthropic_base_url_in_the_environment_is_allowed(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://proxy.example.test")
    urls = []
    _client(urls, base_url="https://proxy.example.test/v2").chat([{"role": "user", "content": "x"}])
    assert urls == ["https://proxy.example.test/v2/v1/messages"]


def test_without_a_base_url_the_default_host_is_used():
    urls = []
    _client(urls).chat([{"role": "user", "content": "Hi"}])
    assert urls == ["https://api.anthropic.com/v1/messages"]


def test_anthropic_base_url_in_the_environment_is_used_after_the_check(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://proxy.example.test")
    urls = []
    _client(urls).chat([{"role": "user", "content": "Hi"}])
    assert urls == ["https://proxy.example.test/v1/messages"]


def test_plain_http_in_anthropic_base_url_to_a_public_host_is_warned_about(monkeypatch, caplog):
    import logging

    monkeypatch.setattr(endpoints, "_warned_http", set())
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://public.example.test")
    with caplog.at_level(logging.WARNING):
        _client([])
    assert "without encryption" in caplog.text and "public.example.test" in caplog.text


@pytest.mark.parametrize(
    "url", ["https://user:secret@proxy.example.test", "ftp://proxy.example.test"]
)
def test_a_malformed_anthropic_base_url_is_refused_before_a_request(monkeypatch, url):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", url)
    urls = []
    with pytest.raises(EndpointNotAllowedError, match="ANTHROPIC_BASE_URL"):
        _client(urls)
    assert urls == []
