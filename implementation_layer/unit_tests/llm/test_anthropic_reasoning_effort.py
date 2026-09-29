"""OpenAI's reasoning_effort must not break a shared Anthropic client."""

import json

import httpx
import pytest
from gaik.software_components.llm.config import get_llm_config
from gaik.software_components.llm.factory import create_llm_client
from pydantic import BaseModel

pytest.importorskip("anthropic")


class Receipt(BaseModel):
    total: float


def _response(content):
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-test",
        "content": content,
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 8, "output_tokens": 3},
    }


@pytest.mark.parametrize("method", ["chat", "chat_parsed"])
def test_reasoning_effort_is_ignored(method):
    # LLMJudge, VisionParser and TranscriptEnhancer forward an explicit effort to any provider.
    bodies = []

    def handle(request):
        bodies.append(json.loads(request.content))
        if method == "chat_parsed":
            content = [{"type": "tool_use", "id": "t", "name": "Receipt", "input": {"total": 1}}]
        else:
            content = [{"type": "text", "text": "OK"}]
        return httpx.Response(200, json=_response(content))

    client = create_llm_client(
        get_llm_config(
            "anthropic",
            api_key="test-key",
            model="claude-test",
            max_retries=0,
            http_client=httpx.Client(transport=httpx.MockTransport(handle)),
        )
    )
    kwargs = {"reasoning_effort": "high", "max_tokens": 50}
    if method == "chat_parsed":
        kwargs["response_format"] = Receipt
    getattr(client, method)([{"role": "user", "content": "Hi"}], **kwargs)

    assert "reasoning_effort" not in bodies[0]
    assert bodies[0]["max_tokens"] == 50


def _client_for(model, bodies):
    def handle(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=_response([{"type": "text", "text": "OK"}]))

    return create_llm_client(
        get_llm_config(
            "anthropic",
            api_key="test-key",
            model=model,
            max_retries=0,
            http_client=httpx.Client(transport=httpx.MockTransport(handle)),
        )
    )


@pytest.mark.parametrize("model", ["claude-sonnet-5", "claude-opus-5-5", "claude-opus-4-6"])
def test_reasoning_effort_becomes_output_config_effort(model):
    # MultimodalParser(api_config=...) and LLMJudge(config=...) pass the
    # component's effort here; dropping it left Claude on its default.
    bodies = []
    _client_for(model, bodies).chat([{"role": "user", "content": "Hi"}], reasoning_effort="low")

    assert "reasoning_effort" not in bodies[0]
    assert bodies[0]["output_config"] == {"effort": "low"}


@pytest.mark.parametrize(
    ("model", "effort"),
    [
        ("claude-haiku-4-5", "low"),
        ("claude-sonnet-4-5", "high"),
        ("claude-sonnet-5", "none"),
        # Levels a model lacks: xhigh arrived with Opus 4.7, max with 4.6.
        ("claude-sonnet-4-6", "xhigh"),
        ("claude-opus-4-5", "max"),
    ],
)
def test_effort_is_dropped_where_claude_would_reject_it(model, effort):
    bodies = []
    _client_for(model, bodies).chat([{"role": "user", "content": "Hi"}], reasoning_effort=effort)

    assert "reasoning_effort" not in bodies[0]
    assert "output_config" not in bodies[0]


def test_effort_merges_into_a_caller_output_config():
    bodies = []
    fmt = {"type": "json_schema", "schema": {"type": "object"}}
    _client_for("claude-sonnet-5", bodies).chat(
        [{"role": "user", "content": "Hi"}],
        reasoning_effort="high",
        output_config={"format": fmt},
    )

    assert bodies[0]["output_config"] == {"format": fmt, "effort": "high"}


@pytest.mark.parametrize(
    ("model", "kept"), [("claude-sonnet-5", False), ("claude-sonnet-4-6", True)]
)
def test_sampling_is_dropped_only_where_claude_rejects_it(model, kept):
    # Sonnet 5 answers 400 "temperature is deprecated for this model";
    # DataExtractor sends temperature=0 on every call.
    bodies = []
    _client_for(model, bodies).chat([{"role": "user", "content": "Hi"}], temperature=0)

    assert ("temperature" in bodies[0]) is kept


def test_models_without_forced_tools_are_asked_instead():
    # Opus 5.5 answers 400 to tool_choice "tool"; it gets "auto" and an instruction.
    bodies = []

    def handle(request):
        bodies.append(json.loads(request.content))
        content = [{"type": "tool_use", "id": "t", "name": "Receipt", "input": {"total": 1}}]
        return httpx.Response(200, json=_response(content))

    client = create_llm_client(
        get_llm_config(
            "anthropic",
            api_key="test-key",
            model="claude-opus-5-5",
            max_retries=0,
            http_client=httpx.Client(transport=httpx.MockTransport(handle)),
        )
    )
    result = client.chat_parsed(
        [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Hi"}],
        response_format=Receipt,
    )

    assert result.total == 1
    assert bodies[0]["tool_choice"] == {"type": "auto"}
    assert bodies[0]["system"].endswith("Answer only by calling the Receipt tool.")


def test_model_families_match_on_a_version_boundary():
    from gaik.software_components.llm.anthropic_provider import _is_family

    assert _is_family("claude-opus-5", ("claude-opus-5",))
    assert _is_family("claude-opus-5-5", ("claude-opus-5",))
    assert _is_family("claude-opus-4-5-20251101", ("claude-opus-4-5",))
    assert not _is_family("claude-opus-50", ("claude-opus-5",))
    assert not _is_family("claude-opus-4-70", ("claude-opus-4-7",))
