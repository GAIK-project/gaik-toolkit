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
