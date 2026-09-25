"""Exercise the real OpenAI SDK against a local mock transport, with no live keys."""

import json

import httpx
import pytest
from gaik.software_components.config import create_openai_client
from gaik.software_components.llm import build_compat_client, create_llm_client, get_llm_config
from openai import AzureOpenAI, OpenAI
from pydantic import BaseModel


@pytest.fixture(autouse=True)
def _isolated_provider_environment(monkeypatch):
    for key in ("AITTA_BASE_URL", "AITTA_EMBEDDING_MODEL", "EMBEDDING_MODEL", "LLM_PROVIDER"):
        monkeypatch.delenv(key, raising=False)


def completion(content):
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "served-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
    }


@pytest.mark.parametrize("provider", ["aitta", "openai_compatible"])
def test_compatible_chat_and_structured_output_use_configured_endpoint(provider):
    requests = []

    def handle(request):
        requests.append(request)
        body = json.loads(request.content)
        content = '{"name":"Ada"}' if "response_format" in body else "Hello"
        return httpx.Response(200, json=completion(content))

    class Person(BaseModel):
        name: str

    with httpx.Client(transport=httpx.MockTransport(handle)) as http_client:
        config = get_llm_config(
            provider,
            api_key="test-token",
            base_url="https://inference.example/openai/v1",
            model="served-model",
            timeout=73,
            max_retries=0,
            http_client=http_client,
        )
        client = create_llm_client(config)
        response = client.chat([{"role": "user", "content": "Hello"}])
        parsed = client.chat_parsed([{"role": "user", "content": "Ada"}], Person)
        assert response.text == "Hello"
        assert response.provider == provider
        assert response.usage["total_tokens"] == 3
        assert parsed.name == "Ada"
        assert client.raw.max_retries == 0
        assert client.raw.timeout == 73
    assert len(requests) == 2
    for request in requests:
        assert str(request.url) == "https://inference.example/openai/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-token"
        assert json.loads(request.content)["model"] == "served-model"
        assert request.extensions["timeout"]["read"] == 73


def test_aitta_stream_uses_chat_endpoint_and_skips_usage_chunks():
    def handle(request):
        assert json.loads(request.content)["stream"] is True
        assert str(request.url) == "https://aitta-api.csc.fi/openai/v1/chat/completions"
        chunks = [
            {"choices": [{"index": 0, "delta": {"content": "Hei"}}]},
            {"choices": [{"index": 0, "delta": {"content": "!"}}]},
            {"choices": [], "usage": {"total_tokens": 3}},
        ]
        events = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks)
        return httpx.Response(
            200, text=events + "data: [DONE]\n\n", headers={"content-type": "text/event-stream"}
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as http_client:
        client = create_llm_client(
            get_llm_config("aitta", api_key="token", http_client=http_client)
        )
        assert "".join(client.chat_stream([{"role": "user", "content": "Hei"}])) == "Hei!"


@pytest.mark.parametrize("provider", ["aitta", "openai_compatible"])
def test_compatible_embedding_requires_served_model(provider):
    requests = []

    def handle(request):
        requests.append(request)
        assert json.loads(request.content)["model"] == "served-embedding"
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})

    with httpx.Client(transport=httpx.MockTransport(handle)) as http_client:
        client = create_llm_client(
            get_llm_config(
                provider,
                api_key="token",
                model="chat-model",
                base_url="https://inference.example/v1",
                http_client=http_client,
            )
        )
        with pytest.raises(ValueError, match="explicit embedding_model"):
            client.embed(["hello"])
        assert requests == []
        assert client.embed(["hello"], model="served-embedding") == [[0.1, 0.2]]
        assert len(requests) == 1


def test_embedding_response_is_ordered_by_input_index():
    def handle(request):
        assert json.loads(request.content)["input"] == ["first", "second"]
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.3, 0.4]},
                    {"index": 0, "embedding": [0.1, 0.2]},
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as http_client:
        client = create_llm_client(
            get_llm_config(
                "aitta",
                api_key="token",
                embedding_model="served-embedding",
                http_client=http_client,
            )
        )
        assert client.embed(["first", "second"]) == [[0.1, 0.2], [0.3, 0.4]]


@pytest.mark.parametrize("factory", [create_openai_client, create_llm_client, build_compat_client])
@pytest.mark.parametrize("legacy_flag", [None, False])
def test_explicit_azure_selects_azure_sdk_across_factories(factory, legacy_flag):
    config = {
        "provider": "  AZURE  ",
        "api_key": "test-key",
        "api_version": "2025-03-01-preview",
        "azure_endpoint": "https://example.openai.azure.com",
        "model": "deployment",
        "timeout": 41,
        "max_retries": 0,
    }
    if legacy_flag is not None:
        config["use_azure"] = legacy_flag
    client = factory(config)
    raw = getattr(client, "raw", client)
    try:
        assert isinstance(raw, AzureOpenAI)
        assert raw.base_url.host == "example.openai.azure.com"
        assert raw.timeout == 41
        assert raw.max_retries == 0
    finally:
        raw.close()


@pytest.mark.parametrize("factory", [create_openai_client, create_llm_client, build_compat_client])
def test_explicit_openai_wins_over_legacy_azure_flag(factory):
    client = factory(
        {
            "provider": "OPENAI",
            "use_azure": True,
            "api_key": "test-key",
            "model": "custom-model",
            "base_url": "https://inference.example/v1",
            "timeout": 32,
            "max_retries": 1,
        }
    )
    raw = getattr(client, "raw", client)
    try:
        assert isinstance(raw, OpenAI)
        assert not isinstance(raw, AzureOpenAI)
        assert raw.base_url.host == "inference.example"
        assert raw.timeout == 32
        assert raw.max_retries == 1
    finally:
        raw.close()


@pytest.mark.parametrize("factory", [create_openai_client, create_llm_client, build_compat_client])
def test_legacy_config_keeps_provider_when_environment_changes(monkeypatch, factory):
    monkeypatch.setenv("LLM_PROVIDER", "google")
    client = factory({"use_azure": False, "api_key": "test-key", "model": "model"})
    raw = getattr(client, "raw", client)
    try:
        assert isinstance(raw, OpenAI)
        assert not isinstance(raw, AzureOpenAI)
    finally:
        raw.close()


def test_azure_custom_base_url_is_forwarded_without_conflicting_endpoint():
    client = create_openai_client(
        {
            "provider": "azure",
            "api_key": "test-key",
            "api_version": "2025-03-01-preview",
            "base_url": "https://example.openai.azure.com/openai/deployments/my-deployment",
            "azure_endpoint": "https://ignored.example",
        }
    )
    try:
        assert str(client.base_url).endswith("/openai/deployments/my-deployment/")
    finally:
        client.close()


def test_bare_legacy_raw_config_still_selects_openai(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "google")
    client = create_openai_client({"api_key": "test-key"})
    try:
        assert isinstance(client, OpenAI)
        assert not isinstance(client, AzureOpenAI)
    finally:
        client.close()


def test_raw_aitta_endpoint_is_not_overridden_by_openai_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://unrelated.example/v1")
    client = create_openai_client({"provider": "aitta", "api_key": "test-key"})
    try:
        assert str(client.base_url) == "https://aitta-api.csc.fi/openai/v1/"
        assert client.timeout == 600.0
    finally:
        client.close()
