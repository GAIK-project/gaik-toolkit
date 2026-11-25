"""A reply the content filter blocked, or that the model declined, raises ContentBlockedError.

Before, each of these came back as empty text (or a parse error about the schema),
so a component returned an empty result as if the document held nothing.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import openai
import pytest
from gaik.software_components.llm import ContentBlockedError
from gaik.software_components.llm.blocked import (
    blocked_request_error,
    check_google_response,
    check_openai_choice,
)
from gaik.software_components.llm.openai_provider import OpenAIProvider
from pydantic import BaseModel

MESSAGES = [{"role": "user", "content": "q"}]


class Answer(BaseModel):
    value: str


def _completion(finish_reason="stop", content="text", refusal=None, parsed=None):
    message = SimpleNamespace(content=content, refusal=refusal, parsed=parsed)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], model="m", usage=None)


def _openai(create=None, parse=None) -> OpenAIProvider:
    provider = OpenAIProvider({"provider": "openai", "api_key": "test", "model": "gpt-4.1"})
    provider.raw = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
        beta=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse))),
    )
    return provider


def _azure_filter_error() -> openai.BadRequestError:
    request = httpx.Request("POST", "https://example.openai.azure.com/openai/deployments/x")
    body = {"code": "content_filter", "message": "The response was filtered", "param": "prompt"}
    return openai.BadRequestError(
        "filtered", response=httpx.Response(400, request=request), body=body
    )


def test_a_filtered_openai_reply_raises_instead_of_returning_empty_text():
    provider = _openai(create=lambda **_: _completion("content_filter", content=None))

    with pytest.raises(ContentBlockedError) as blocked:
        provider.chat(MESSAGES)

    assert blocked.value.reason == "content_filter"
    assert blocked.value.provider == "openai"


def test_a_refusal_in_chat_parsed_raises_instead_of_a_schema_error():
    provider = _openai(parse=lambda **_: _completion(refusal="I can't help with that."))

    with pytest.raises(ContentBlockedError) as blocked:
        provider.chat_parsed(MESSAGES, Answer)

    assert blocked.value.reason == "refusal"


def test_azures_prompt_filter_error_raises_content_blocked():
    def create(**_):
        raise _azure_filter_error()

    with pytest.raises(ContentBlockedError) as blocked:
        _openai(create=create).chat(MESSAGES)

    assert isinstance(blocked.value.__cause__, openai.BadRequestError)


def test_a_filter_stop_in_a_stream_raises():
    chunks = [
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="Hel"), finish_reason=None)]
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(delta=SimpleNamespace(content=None), finish_reason="content_filter")
            ]
        ),
    ]
    provider = _openai(create=lambda **_: iter(chunks))

    stream = provider.chat_stream(MESSAGES)
    assert next(stream) == "Hel"
    with pytest.raises(ContentBlockedError):
        next(stream)


def test_an_ordinary_reply_and_an_ordinary_400_are_unchanged():
    assert _openai(create=lambda **_: _completion()).chat(MESSAGES).text == "text"
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    other = openai.BadRequestError(
        "bad", response=httpx.Response(400, request=request), body={"code": "invalid_value"}
    )
    assert blocked_request_error(other, provider="openai", model="m") is None
    check_openai_choice(_completion("length").choices[0], provider="openai", model="m")


def test_claude_declining_raises():
    from gaik.software_components.llm.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider({"provider": "anthropic", "api_key": "test", "model": "claude-x"})
    response = SimpleNamespace(content=[], model="claude-x", stop_reason="refusal", usage=None)
    provider.raw = SimpleNamespace(messages=SimpleNamespace(create=lambda **_: response))

    with pytest.raises(ContentBlockedError) as blocked:
        provider.chat(MESSAGES)
    assert blocked.value.reason == "refusal"
    with pytest.raises(ContentBlockedError):
        provider.chat_parsed(MESSAGES, Answer)


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(prompt_feedback=SimpleNamespace(block_reason="SAFETY"), candidates=[]),
        SimpleNamespace(
            prompt_feedback=None, candidates=[SimpleNamespace(finish_reason="PROHIBITED_CONTENT")]
        ),
    ],
)
def test_gemini_blocking_raises(response):
    with pytest.raises(ContentBlockedError):
        check_google_response(response, provider="google", model="gemini")


def test_an_ordinary_gemini_reply_passes():
    response = SimpleNamespace(
        prompt_feedback=SimpleNamespace(block_reason=None),
        candidates=[SimpleNamespace(finish_reason="STOP")],
    )
    check_google_response(response, provider="google", model="gemini")


def test_litellms_content_policy_error_raises_content_blocked():
    class ContentPolicyViolationError(Exception):
        pass

    blocked = blocked_request_error(ContentPolicyViolationError("x"), provider="litellm", model="m")
    assert isinstance(blocked, ContentBlockedError)


@pytest.mark.parametrize(
    "module",
    [
        "gaik.software_components.tabular_agent.agent",
        "gaik.software_components.postgres_agent.agent",
        "gaik.software_components.extractor.schema",
        "gaik.software_components.RAG.embedder.embedder",
        "gaik.software_components.RAG.answer_generator.generator",
    ],
)
def test_a_filtered_request_is_not_sent_again(module, monkeypatch):
    import importlib

    target = importlib.import_module(module)
    monkeypatch.setattr(target.time, "sleep", lambda _: None)
    calls = []

    def call():
        calls.append(1)
        raise _azure_filter_error()

    with pytest.raises(openai.BadRequestError):
        target._with_retries(call)
    assert calls == [1]


# --- components that keep the raw OpenAI / Azure client ---------------------


def _raw_client(create=None, parse=None, name="AzureOpenAI"):
    completions = SimpleNamespace(create=create)
    parsing = SimpleNamespace(parse=parse)
    raw = type(name, (), {})()
    raw.chat = SimpleNamespace(completions=completions)
    raw.beta = SimpleNamespace(chat=SimpleNamespace(completions=parsing))
    return raw


def test_the_raw_azure_client_raises_on_a_filtered_reply():
    from gaik.software_components.llm.blocked import checked_openai

    raw = _raw_client(create=lambda **_: _completion("content_filter", content=None))

    with pytest.raises(ContentBlockedError) as blocked:
        checked_openai(raw).chat.completions.create(model="dep", messages=MESSAGES)
    assert blocked.value.provider == "azure"
    assert blocked.value.model == "dep"


def test_the_sdks_own_parse_filter_error_becomes_content_blocked():
    from gaik.software_components.llm.blocked import checked_openai

    def parse(**_):
        raise openai.ContentFilterFinishReasonError()

    with pytest.raises(ContentBlockedError):
        checked_openai(_raw_client(parse=parse)).beta.chat.completions.parse(
            model="dep", messages=MESSAGES, response_format=Answer
        )


def test_a_raw_stream_raises_at_the_filtered_chunk():
    from gaik.software_components.llm.blocked import checked_openai

    chunks = [
        SimpleNamespace(choices=[]),  # Azure's prompt_filter_results chunk
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="a"), finish_reason=None)]
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(delta=SimpleNamespace(content=None), finish_reason="content_filter")
            ]
        ),
    ]
    raw = _raw_client(create=lambda **_: iter(chunks))
    stream = checked_openai(raw).chat.completions.create(model="d", messages=MESSAGES, stream=True)

    assert next(stream).choices == []
    assert next(stream).choices[0].delta.content == "a"
    with pytest.raises(ContentBlockedError):
        next(stream)


def test_the_answer_generator_on_azure_no_longer_returns_empty_text(monkeypatch):
    from gaik.software_components.RAG.answer_generator import generator

    raw = _raw_client(create=lambda **_: _completion("content_filter", content=None))
    monkeypatch.setattr(generator, "build_compat_client", lambda config: raw)
    answers = generator.AnswerGenerator(
        config={"provider": "azure", "api_key": "k", "azure_endpoint": "https://x", "model": "d"},
        stream=False,
    )
    monkeypatch.setattr(answers, "client", raw, raising=False)

    with pytest.raises(ContentBlockedError):
        answers.generate("question?", [])


def test_the_refusal_text_stays_out_of_the_message():
    choice = _completion(refusal="Your document about Jane Doe ...").choices[0]
    with pytest.raises(ContentBlockedError) as blocked:
        check_openai_choice(choice, provider="openai", model="m")
    assert "Jane Doe" not in str(blocked.value)
    assert "Jane Doe" in blocked.value.refusal_text


def test_litellm_chat_raises_on_a_filtered_reply(monkeypatch):
    from gaik.software_components.llm import litellm_provider

    provider = litellm_provider.LiteLLMProvider({"provider": "litellm", "model": "azure/x"})
    monkeypatch.setattr(
        litellm_provider.litellm,
        "completion",
        lambda **_: _completion("content_filter", content=None),
    )
    with pytest.raises(ContentBlockedError):
        provider.chat(MESSAGES)


@pytest.mark.parametrize("status", [429, 500])
def test_a_rate_limit_or_server_error_is_still_tried_again(status, monkeypatch):
    from gaik.software_components.RAG.answer_generator import generator

    monkeypatch.setattr(generator.time, "sleep", lambda _: None)
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    error_class = openai.RateLimitError if status == 429 else openai.InternalServerError
    calls = []

    def call():
        calls.append(1)
        if len(calls) < 3:
            raise error_class("x", response=httpx.Response(status, request=request), body=None)
        return "ok"

    assert generator._with_retries(call) == "ok"
    assert len(calls) == 3
