"""Google adapter contract tests using the installed SDK types and a fake transport."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

pytest.importorskip("google.genai")

from gaik.software_components.llm import google_provider  # noqa: E402
from gaik.software_components.llm.config import get_llm_config  # noqa: E402


def test_vertex_user_adc_is_left_to_google_auth(monkeypatch, tmp_path):
    import json

    import google.auth
    from google.oauth2.credentials import Credentials

    adc = tmp_path / "application_default_credentials.json"
    adc.write_text(
        json.dumps(
            {
                "type": "authorized_user",
                "client_id": "test-client",
                "client_secret": "test-secret",
                "refresh_token": "test-refresh-token",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(adc))
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    calls = []

    def client(**kwargs):
        calls.append(kwargs)
        # The provider must leave ADC resolution to the Google SDK. A user ADC
        # file is valid google-auth input, but is not service-account JSON.
        credentials, _ = google.auth.default()
        assert isinstance(credentials, Credentials)
        return SimpleNamespace()

    monkeypatch.setattr(google_provider.genai, "Client", client)
    config = get_llm_config("vertex", project_id="project", model="gemini-test")
    google_provider.GoogleProvider(config)
    assert calls[0]["credentials"] is None


class _Answer(BaseModel):
    answer: str


class _Models:
    def __init__(self):
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text='{"answer":"ok"}', parsed=None, usage_metadata=None)

    def generate_content_stream(self, **kwargs):
        self.calls.append(kwargs)
        return iter([SimpleNamespace(text="ok")])

    def embed_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[0.1, 0.2])])


@pytest.fixture
def client(monkeypatch):
    models = _Models()
    monkeypatch.setattr(
        google_provider.genai, "Client", lambda **kwargs: SimpleNamespace(models=models)
    )
    return google_provider.GoogleProvider({"api_key": "test", "model": "gemini-test"})


@pytest.mark.parametrize("method", ["chat", "chat_parsed", "chat_stream"])
@pytest.mark.parametrize(
    "token_option", ["max_tokens", "max_completion_tokens", "max_output_tokens"]
)
def test_common_token_limit_is_translated_to_google_config(client, method, token_option):
    kwargs = {token_option: 123}
    if method == "chat_parsed":
        kwargs["response_format"] = _Answer
    result = getattr(client, method)([{"role": "user", "content": "Hello"}], **kwargs)
    if method == "chat_stream":
        assert list(result) == ["ok"]

    assert client.raw.models.calls[0]["config"].max_output_tokens == 123


def test_conflicting_token_limits_are_rejected_before_request(client):
    with pytest.raises(ValueError, match="Use only one token limit"):
        client.chat([{"role": "user", "content": "Hello"}], max_tokens=20, max_output_tokens=30)
    assert client.raw.models.calls == []


def test_text_parts_and_roles_preserve_message_content(client):
    client.chat(
        [
            {"role": "system", "content": [{"type": "text", "text": "Be brief."}]},
            {"role": "user", "content": [{"type": "text", "text": "Hello"}]},
            {"role": "assistant", "content": "Hi"},
            {"role": "user", "content": "How are you?"},
        ]
    )
    call = client.raw.models.calls[0]
    assert call["config"].system_instruction == "Be brief."
    assert [content.role for content in call["contents"]] == ["user", "model", "user"]
    assert [content.parts[0].text for content in call["contents"]] == [
        "Hello",
        "Hi",
        "How are you?",
    ]


@pytest.mark.parametrize(
    "message",
    [
        {
            "role": "user",
            "content": [{"type": "image_url", "image_url": {"url": "https://example.test/a.png"}}],
        },
        {"role": "system", "content": [{"type": "input_audio", "input_audio": {}}]},
        {"role": "tool", "content": "result", "tool_call_id": "one"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "one"}]},
    ],
)
def test_unsupported_content_fails_without_sending_a_textual_repr(client, message):
    with pytest.raises(ValueError, match="GoogleProvider supports"):
        client.chat([message])
    assert client.raw.models.calls == []


def test_default_embedding_model_matches_config_loader(client):
    assert client.embed(["hello"]) == [[0.1, 0.2]]
    assert client.raw.models.calls[0]["model"] == "gemini-embedding-001"


@pytest.mark.parametrize("provider", ["google", "vertex"])
@pytest.mark.parametrize("retries", [0, 2])
def test_http_timeout_and_retry_budget_reach_google_sdk(monkeypatch, provider, retries):
    captured = {}
    monkeypatch.setattr(google_provider.genai, "Client", lambda **kwargs: captured.update(kwargs))
    google_provider.GoogleProvider(
        {
            "provider": provider,
            "model": "gemini-test",
            "api_key": "test",
            "project_id": "test-project",
            "timeout": 1.5,
            "max_retries": retries,
        }
    )

    assert captured["http_options"].timeout == 1500
    assert captured["http_options"].retry_options.attempts == retries + 1


def test_google_retry_budget_works_without_explicit_timeout(monkeypatch):
    captured = {}
    monkeypatch.setattr(google_provider.genai, "Client", lambda **kwargs: captured.update(kwargs))
    google_provider.GoogleProvider({"model": "gemini-test", "api_key": "test", "max_retries": 0})
    assert captured["http_options"].retry_options.attempts == 1
    assert captured["http_options"].timeout is None


@pytest.mark.parametrize("retries", [-1, 1.5])
def test_invalid_google_retry_budget_fails_before_client_creation(retries):
    with pytest.raises(ValueError, match="non-negative integer"):
        google_provider.GoogleProvider(
            {"model": "gemini-test", "api_key": "test", "max_retries": retries}
        )


def test_inline_image_is_sent_as_bytes_not_text(client):
    client.chat(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Read this"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,YWJj"}},
                ],
            }
        ]
    )
    image = client.raw.models.calls[0]["contents"][0].parts[1].inline_data
    assert image.data == b"abc"
    assert image.mime_type == "image/png"


def test_vertex_uses_explicit_project_location_and_credentials(monkeypatch):
    captured = {}

    def build(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(models=_Models())

    monkeypatch.setattr(google_provider.genai, "Client", build)
    credentials = object()
    google_provider.GoogleProvider(
        {
            "provider": "vertex",
            "project_id": "project",
            "location": "europe-north1",
            "model": "gemini-test",
            "credentials": credentials,
            "timeout": 30,
        }
    )
    assert captured["vertexai"] is True
    assert captured["project"] == "project"
    assert captured["location"] == "europe-north1"
    assert captured["credentials"] is credentials
    assert captured["http_options"].timeout == 30000
    assert "api_key" not in captured


def test_recursive_schema_is_rejected_before_request(client):
    class Node(BaseModel):
        name: str
        children: list[Node] = []

    with pytest.raises(ValueError, match="Recursive schemas are not supported"):
        client.chat_parsed([{"role": "user", "content": "Tree"}], response_format=Node)
    assert client.raw.models.calls == []


def test_repeated_nested_schema_references_are_not_treated_as_cycles():
    class Pair(BaseModel):
        first: _Answer
        second: _Answer

    schema = google_provider.GoogleProvider._gemini_schema(Pair)
    assert schema["properties"]["first"] == schema["properties"]["second"]
    assert schema["properties"]["first"]["properties"]["answer"]["type"] == "string"
