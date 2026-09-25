from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ValidationError

pytest.importorskip("litellm")
from gaik.software_components.llm import (  # noqa: E402
    create_llm_client,
    get_llm_config,
    litellm_provider,  # noqa: E402
)


class Answer(BaseModel):
    count: int


def test_requests_scope_credentials_translate_sampling_and_validate_schema(monkeypatch):
    calls = []

    def completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            model=kwargs["model"],
            usage=None,
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"count":7}'))],
        )

    monkeypatch.setattr(litellm_provider.litellm, "completion", completion)
    client = create_llm_client(
        get_llm_config(
            "litellm",
            model="azure/gpt-6-luna",
            api_key="private-key",
            base_url="https://resource.openai.azure.com",
            api_version="version",
        )
    )
    assert (
        client.chat_parsed(
            [{"role": "user", "content": "Seven"}],
            response_format=Answer,
            temperature=0,
            max_tokens=128,
            reasoning_effort="low",
        ).count
        == 7
    )
    assert calls[0]["model"] == "azure/gpt-6-luna"
    assert calls[0]["api_key"] == "private-key"
    assert calls[0]["api_base"] == "https://resource.openai.azure.com"
    assert calls[0]["api_version"] == "version"
    assert calls[0]["reasoning_effort"] == "low"
    assert calls[0]["max_completion_tokens"] == 128
    assert "max_tokens" not in calls[0]
    assert "temperature" not in calls[0]
    assert calls[0]["response_format"] is Answer
    second = create_llm_client({"provider": "litellm", "model": "openai/gpt-6-luna"})
    second.chat([{"role": "user", "content": "Hello"}])
    assert "api_key" not in calls[1]
    assert "api_base" not in calls[1]


def test_client_options_use_litellm_names_for_chat_and_embeddings(monkeypatch):
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
        return SimpleNamespace(data=[{"index": 0, "embedding": [1.0]}])

    monkeypatch.setattr(litellm_provider.litellm, "completion", completion)
    monkeypatch.setattr(litellm_provider.litellm, "embedding", embedding)
    client = create_llm_client(
        {
            "provider": "litellm",
            "model": "vertex_ai/gemini-2.5-flash",
            "embedding_model": "vertex_ai/gemini-embedding-001",
            "timeout": 30.0,
            "max_retries": 2,
            "vertex_project": "project",
            "vertex_location": "europe-north1",
        }
    )
    client.chat([{"role": "user", "content": "Hello"}])
    client.embed(["Hello"])
    client.chat([{"role": "user", "content": "Hello"}], timeout=5.0)

    for call in calls[:2]:
        assert call["timeout"] == 30.0
        assert call["num_retries"] == 2
        assert "max_retries" not in call
        assert call["vertex_project"] == "project"
        assert call["vertex_location"] == "europe-north1"
    assert calls[0]["model"] == "vertex_ai/gemini-2.5-flash"
    assert calls[1]["model"] == "vertex_ai/gemini-embedding-001"
    assert calls[1]["input"] == ["Hello"]
    assert calls[2]["timeout"] == 5.0


@pytest.mark.parametrize("model", ["", "gpt-6-luna"])
def test_model_must_name_its_litellm_provider(model):
    with pytest.raises(ValueError, match="provider-prefixed"):
        create_llm_client({"provider": "litellm", "model": model})


def test_invalid_structured_response_is_not_silently_accepted(monkeypatch):
    monkeypatch.setattr(
        litellm_provider.litellm,
        "completion",
        lambda **kw: SimpleNamespace(
            model=kw["model"],
            usage=None,
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"count":"invalid"}'))],
        ),
    )
    client = create_llm_client({"provider": "litellm", "model": "openai/model"})
    with pytest.raises(ValidationError):
        client.chat_parsed([], response_format=Answer)


def test_embeddings_require_model_and_restore_order(monkeypatch):
    client = create_llm_client({"provider": "litellm", "model": "openai/model"})
    with pytest.raises(ValueError, match="embedding_model"):
        client.embed(["first"])
    monkeypatch.setattr(
        litellm_provider.litellm,
        "embedding",
        lambda **kw: SimpleNamespace(
            data=[{"index": 1, "embedding": [2.0]}, {"index": 0, "embedding": [1.0]}]
        ),
    )
    assert client.embed(["first", "second"], model="openai/embedding") == [[1.0], [2.0]]


def test_stream_yields_content_and_closes(monkeypatch):
    class Stream:
        closed = False

        def __iter__(self):
            yield SimpleNamespace(choices=[])
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="ok"))])

        def close(self):
            self.closed = True

    stream = Stream()
    monkeypatch.setattr(litellm_provider.litellm, "completion", lambda **kw: stream)
    client = create_llm_client({"provider": "litellm", "model": "openai/model"})
    assert list(client.chat_stream([])) == ["ok"]
    assert stream.closed
