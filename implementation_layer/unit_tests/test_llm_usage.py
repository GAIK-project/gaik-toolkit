"""Offline tests of the token usage that providers count for ``chat`` and ``chat_parsed``."""

from __future__ import annotations

from types import SimpleNamespace

from gaik.software_components.llm import google_provider
from gaik.software_components.llm.base import UsageCounter, add_usage, usage_since
from gaik.software_components.llm.openai_provider import OpenAIProvider
from openai.types import CompletionUsage
from pydantic import BaseModel


class Answer(BaseModel):
    value: str


def test_usage_helpers():
    counter = UsageCounter()
    counter.add({"prompt_tokens": 5})
    before = counter.snapshot()
    counter.add({"prompt_tokens": 2, "completion_tokens": 1})
    assert usage_since(before, counter.snapshot()) == {"prompt_tokens": 2, "completion_tokens": 1}
    assert add_usage({"a": 1}, {"a": 2, "b": 3}) == {"a": 3, "b": 3}


def test_openai_counts_chat_and_chat_parsed():
    usage = CompletionUsage(prompt_tokens=7, completion_tokens=3, total_tokens=10)
    message = SimpleNamespace(content="text", parsed=Answer(value="x"))
    completion = SimpleNamespace(choices=[SimpleNamespace(message=message)], model="m", usage=usage)
    completions = SimpleNamespace(create=lambda **kwargs: completion)
    parse = SimpleNamespace(parse=lambda **kwargs: completion)
    provider = OpenAIProvider({"provider": "openai", "api_key": "test", "model": "gpt-4.1"})
    provider.raw = SimpleNamespace(
        chat=SimpleNamespace(completions=completions),
        beta=SimpleNamespace(chat=SimpleNamespace(completions=parse)),
    )

    assert provider.chat([{"role": "user", "content": "q"}]).usage == usage.model_dump(
        exclude_none=True
    )
    assert provider.chat_parsed([{"role": "user", "content": "q"}], Answer) == Answer(value="x")
    assert provider.usage.snapshot() == {
        "prompt_tokens": 14,
        "completion_tokens": 6,
        "total_tokens": 20,
    }


def test_google_usage_treats_missing_counts_as_zero():
    # genai declares every usage count Optional; None must not reach UsageCounter.add.
    metadata = SimpleNamespace(prompt_token_count=4, candidates_token_count=None)
    usage = google_provider._usage(SimpleNamespace(usage_metadata=metadata))
    assert usage == {"prompt_tokens": 4, "completion_tokens": 0}
    counter = UsageCounter()
    counter.add(usage)
    assert counter.snapshot() == usage
    assert google_provider._usage(SimpleNamespace(usage_metadata=None)) == {}


def test_google_usage_counts_thinking_tokens_as_output():
    # Gemini bills thinking as output but reports it apart from the answer's tokens.
    from google.genai import types as genai_types

    metadata = genai_types.GenerateContentResponseUsageMetadata(
        prompt_token_count=10, candidates_token_count=3, thoughts_token_count=40
    )
    usage = google_provider._usage(SimpleNamespace(usage_metadata=metadata))
    assert usage == {"prompt_tokens": 10, "completion_tokens": 43}


def test_the_judges_gemini_cost_includes_thinking(monkeypatch):
    from gaik.software_components.validators.llm_judge.llm_judge import LLMJudge
    from gaik.software_components.validators.llm_judge.pricing import compute_judge_cost_usd
    from google.genai import types as genai_types

    metadata = genai_types.GenerateContentResponseUsageMetadata(
        prompt_token_count=10, candidates_token_count=3, thoughts_token_count=40
    )

    class Client:
        def __init__(self, **kwargs):
            self.models = SimpleNamespace(
                generate_content=lambda **kw: SimpleNamespace(
                    text='{"flags": []}', usage_metadata=metadata, parsed=None
                )
            )

    monkeypatch.setattr(google_provider.genai, "Client", Client)
    monkeypatch.setattr(google_provider, "_NOT_SERVED", {})
    monkeypatch.setattr(google_provider, "_UNAVAILABLE_UNTIL", {})
    monkeypatch.setenv("GOOGLE_VERTEXAI_PROJECT", "project")
    monkeypatch.delenv("GOOGLE_VERTEXAI_LOCATION", raising=False)
    judge = LLMJudge(model_provider="google", model="gemini-3-flash-preview")
    result = judge.validate([b"png"], {"total": "12"})
    assert (result.usage.input_tokens, result.usage.output_tokens) == (10, 43)
    assert result.usage.cost_usd == compute_judge_cost_usd("gemini-3-flash-preview", 10, 43)


def test_the_judges_gemini_api_cost_includes_thinking(monkeypatch):
    """The Gemini Developer API path (use_vertexai=False) counts the same way."""
    from gaik.software_components.validators.llm_judge.llm_judge import LLMJudge
    from gaik.software_components.validators.llm_judge.pricing import compute_judge_cost_usd
    from google import genai
    from google.genai import types as genai_types

    metadata = genai_types.GenerateContentResponseUsageMetadata(
        prompt_token_count=10, candidates_token_count=3, thoughts_token_count=40
    )

    class Client:
        def __init__(self, **kwargs):
            assert "api_key" in kwargs
            self.models = SimpleNamespace(
                generate_content=lambda **kw: SimpleNamespace(
                    text='{"flags": []}', usage_metadata=metadata
                )
            )

    monkeypatch.setattr(genai, "Client", Client)
    monkeypatch.setenv("GOOGLE_GEMINI_API_KEY", "test-key")
    judge = LLMJudge(model_provider="google", model="gemini-3-flash-preview", use_vertexai=False)
    result = judge.validate([b"png"], {"total": "12"})
    assert (result.usage.input_tokens, result.usage.output_tokens) == (10, 43)
    assert result.usage.cost_usd == compute_judge_cost_usd("gemini-3-flash-preview", 10, 43)
