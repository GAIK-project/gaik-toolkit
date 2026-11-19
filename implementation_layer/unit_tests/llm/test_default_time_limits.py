"""A model request stops and retries at the same point on every provider.

When a config sets no ``timeout`` or ``max_retries``, every client gets
``DEFAULT_TIMEOUT_SECONDS`` and ``DEFAULT_MAX_RETRIES``; a value the caller gives
stands. No test reaches a network or a model.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from gaik.software_components.config import create_openai_client
from gaik.software_components.llm.base import DEFAULT_MAX_RETRIES, DEFAULT_TIMEOUT_SECONDS


def test_the_defaults_match_the_openai_and_anthropic_sdks():
    assert (DEFAULT_TIMEOUT_SECONDS, DEFAULT_MAX_RETRIES) == (600.0, 2)


@pytest.mark.parametrize(
    "config",
    [
        {"provider": "openai", "api_key": "test-key"},
        {
            "provider": "azure",
            "api_key": "test-key",
            "azure_endpoint": "https://resource.openai.azure.com",
            "api_version": "2025-03-01-preview",
        },
        {"provider": "aitta", "api_key": "test-key"},
    ],
)
def test_an_openai_client_gets_the_default_time_limit(config):
    client = create_openai_client(config)
    assert client.timeout == DEFAULT_TIMEOUT_SECONDS
    assert client.max_retries == DEFAULT_MAX_RETRIES


def test_a_callers_time_limit_stands_on_an_openai_client():
    client = create_openai_client(
        {"provider": "openai", "api_key": "test-key", "timeout": 30.0, "max_retries": 0}
    )
    assert (client.timeout, client.max_retries) == (30.0, 0)


def test_an_anthropic_client_gets_the_default_time_limit():
    from gaik.software_components.llm.anthropic_provider import AnthropicProvider

    client = AnthropicProvider._build_client({"provider": "anthropic", "api_key": "test-key"})
    assert client.timeout == DEFAULT_TIMEOUT_SECONDS
    assert client.max_retries == DEFAULT_MAX_RETRIES
    own = AnthropicProvider._build_client(
        {"provider": "anthropic", "api_key": "test-key", "timeout": 30.0, "max_retries": 0}
    )
    assert (own.timeout, own.max_retries) == (30.0, 0)


def test_a_litellm_request_gets_the_default_time_limit(monkeypatch):
    pytest.importorskip("litellm")
    from gaik.software_components.llm import create_llm_client, litellm_provider

    calls = []

    def completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            model=kwargs["model"],
            usage=None,
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
        )

    monkeypatch.setattr(litellm_provider.litellm, "completion", completion)
    create_llm_client({"provider": "litellm", "model": "openai/test"}).chat(
        [{"role": "user", "content": "Hello"}]
    )
    assert calls[0]["timeout"] == DEFAULT_TIMEOUT_SECONDS
    assert calls[0]["num_retries"] == DEFAULT_MAX_RETRIES


def test_the_judges_gemini_client_gets_the_default_time_limit(monkeypatch):
    pytest.importorskip("google.genai")
    from gaik.software_components.validators.llm_judge import llm_judge as judge_module
    from google import genai

    clients = []

    def client(**kwargs):
        clients.append(kwargs)
        return SimpleNamespace(
            models=SimpleNamespace(
                generate_content=lambda **_: SimpleNamespace(text="{}", usage_metadata=None)
            )
        )

    monkeypatch.setattr(genai, "Client", client)
    monkeypatch.setenv("GOOGLE_GEMINI_API_KEY", "test-key")
    judge = SimpleNamespace(use_vertexai=False, model="gemini-test", max_tokens=64)
    judge_module.LLMJudge._call_google(judge, [], "user", "system")

    (options,) = clients
    assert options["http_options"].timeout == int(DEFAULT_TIMEOUT_SECONDS * 1000)
    assert options["http_options"].retry_options.attempts == DEFAULT_MAX_RETRIES + 1
