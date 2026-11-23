"""Endpoint allow-list follow-ups (#229): LiteLLM call-time addresses are checked, and
a refusal names the provider's own variable."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from gaik.software_components import endpoints
from gaik.software_components.endpoints import EndpointNotAllowedError, check_endpoint

_ENVS = {name for names in endpoints.PROVIDER_ENDPOINT_ENVS.values() for name in names} | {
    endpoints.ALLOWED_HOSTS_ENV
}


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    for name in _ENVS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(endpoints, "_logged", set())
    monkeypatch.setattr(endpoints, "_warned_http", set())


# ── LiteLLM call-time api_base ──────────────────────────────────────


@pytest.fixture
def litellm_calls(monkeypatch):
    pytest.importorskip("litellm")
    from gaik.software_components.llm import litellm_provider

    calls = []

    def completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            model=kwargs["model"],
            usage=None,
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
        )

    def embedding(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(data=[{"index": 0, "embedding": [0.5]}])

    monkeypatch.setattr(litellm_provider.litellm, "completion", completion)
    monkeypatch.setattr(litellm_provider.litellm, "embedding", embedding)
    return calls


def _litellm(**config):
    from gaik.software_components.llm.litellm_provider import LiteLLMProvider

    return LiteLLMProvider(
        {"model": "azure/gpt-test", "api_key": "k", "embedding_model": "azure/emb", **config}
    )


USER = [{"role": "user", "content": "hi"}]


@pytest.mark.parametrize("name", ["api_base", "base_url"])
@pytest.mark.parametrize("call", ["chat", "stream", "embed"])
def test_a_call_time_address_on_an_unknown_host_is_refused_before_a_request(
    litellm_calls, name, call
):
    provider = _litellm(base_url="https://resource.openai.azure.com")
    url = "https://collector.example.test/v1"
    with pytest.raises(EndpointNotAllowedError, match="collector.example.test") as refused:
        if call == "chat":
            provider.chat(USER, **{name: url})
        elif call == "stream":
            list(provider.chat_stream(USER, **{name: url}))
        else:
            provider.embed(["text"], **{name: url})
    assert name in str(refused.value)
    assert litellm_calls == []


@pytest.mark.parametrize(
    "url", ["http://resource.openai.azure.com", "https://u:p@x.openai.azure.com"]
)
def test_a_call_time_address_is_held_to_https_and_no_user_info(litellm_calls, url):
    with pytest.raises(EndpointNotAllowedError):
        _litellm().chat(USER, api_base=url)
    assert litellm_calls == []


def test_a_call_time_address_on_an_allowed_host_is_used(litellm_calls, monkeypatch):
    provider = _litellm(allowed_endpoint_hosts=["gateway.example.test"])
    provider.chat(USER, api_base="https://gateway.example.test/v1")
    provider.chat(USER, api_base="https://other.openai.azure.com")
    assert [c["api_base"] for c in litellm_calls] == [
        "https://gateway.example.test/v1",
        "https://other.openai.azure.com",
    ]
    monkeypatch.setenv("LITELLM_BASE_URL", "http://litellm-proxy:4000")
    provider.chat(USER, api_base="http://litellm-proxy:4000")
    assert litellm_calls[-1]["api_base"] == "http://litellm-proxy:4000"


def test_a_call_without_an_address_keeps_the_configured_one(litellm_calls):
    _litellm(base_url="https://resource.openai.azure.com").chat(USER, temperature=0.2)
    assert litellm_calls[0]["api_base"] == "https://resource.openai.azure.com"


# ── The provider's own variable in the message ──────────────────────


def test_an_unknown_azure_host_names_azure_endpoint():
    with pytest.raises(EndpointNotAllowedError) as refused:
        check_endpoint("https://apim.example.test", provider="azure", what="azure_endpoint")
    message = str(refused.value)
    assert "set the address in AZURE_ENDPOINT (or AZURE_OPENAI_ENDPOINT" in message
    assert endpoints.ALLOWED_HOSTS_ENV in message


def test_plain_http_names_the_providers_variable():
    with pytest.raises(EndpointNotAllowedError, match="https") as refused:
        check_endpoint("http://docling.internal", provider="docling", what="api_base")
    message = str(refused.value)
    assert "set the address in DOCLING_API_BASE (or API_BASE)" in message
    assert "'http://docling.internal'" in message


def test_this_machine_names_the_providers_variable():
    with pytest.raises(EndpointNotAllowedError, match="this machine") as refused:
        check_endpoint("https://localhost:8443", provider="aitta", what="base_url")
    assert "set the address in AITTA_BASE_URL, or list 'localhost'" in str(refused.value)


def test_a_provider_without_a_variable_names_only_the_list():
    with pytest.raises(EndpointNotAllowedError) as refused:
        check_endpoint("https://other.example.test", provider="google", what="base_url")
    message = str(refused.value)
    assert "set the address" not in message
    assert endpoints.ALLOWED_HOSTS_ENV in message


@pytest.mark.parametrize(
    ("provider", "variable"),
    [(p, names[0]) for p, names in endpoints.PROVIDER_ENDPOINT_ENVS.items()],
)
def test_setting_the_named_variable_lets_the_address_through(monkeypatch, provider, variable):
    """The message's advice works: the host of the variable it names is accepted."""
    url = "https://named.example.test/v1"
    with pytest.raises(EndpointNotAllowedError, match=variable):
        check_endpoint(url, provider=provider)
    monkeypatch.setenv(variable, url)
    assert check_endpoint(url, provider=provider) == "named.example.test"
