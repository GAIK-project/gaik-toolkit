"""Structured output on Claude: strict tools, forced-tool models and truncation."""

import json

import httpx
import pytest
from gaik.software_components.llm.config import get_llm_config
from gaik.software_components.llm.factory import create_llm_client
from pydantic import BaseModel, Field, ValidationError

pytest.importorskip("anthropic")


class Item(BaseModel):
    name: str
    note: str | None = None


class Curation(BaseModel):
    units: list[Item]
    missing: list[str] = []


def _message(content, stop_reason="tool_use"):
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-test",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 8, "output_tokens": 3},
    }


def _tool_use(data):
    return [{"type": "tool_use", "id": "t", "name": "Curation", "input": data}]


ANSWER = {"units": [{"name": "a", "note": None}], "missing": []}


def _client(model, responses, bodies, **config):
    replies = iter(responses)

    def handle(request):
        bodies.append(json.loads(request.content))
        return next(replies)

    return create_llm_client(
        get_llm_config(
            "anthropic",
            api_key="test-key",
            model=model,
            max_retries=0,
            http_client=httpx.Client(transport=httpx.MockTransport(handle)),
            **config,
        )
    )


def _ask(client):
    return client.chat_parsed([{"role": "user", "content": "Hi"}], response_format=Curation)


def test_strict_tool_closes_every_object():
    bodies = []
    client = _client(
        "claude-sonnet-5", [httpx.Response(200, json=_message(_tool_use(ANSWER)))], bodies
    )

    assert _ask(client) == Curation.model_validate(ANSWER)
    tool = bodies[0]["tools"][0]
    assert tool["strict"] is True
    schema = tool["input_schema"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["units", "missing"]
    item = schema["$defs"]["Item"]
    assert item["additionalProperties"] is False
    assert item["required"] == ["name", "note"]


class Scored(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    confidence: float = Field(ge=0, le=1)
    maximum: int = Field(gt=0, multiple_of=2)


def test_strict_tool_drops_bounds_and_pydantic_still_checks_them():
    bodies = []
    answer = {"label": "invoice", "confidence": 0.9, "maximum": 4}
    reply = [{"type": "tool_use", "id": "t", "name": "Scored", "input": answer}]
    client = _client("claude-sonnet-5-5", [httpx.Response(200, json=_message(reply))], bodies)

    result = client.chat_parsed([{"role": "user", "content": "Hi"}], response_format=Scored)

    assert result == Scored.model_validate(answer)
    schema = bodies[0]["tools"][0]["input_schema"]
    assert schema["properties"] == {
        "label": {"title": "Label", "type": "string"},
        "confidence": {"title": "Confidence", "type": "number"},
        "maximum": {"title": "Maximum", "type": "integer"},
    }
    with pytest.raises(ValidationError):
        Scored.model_validate({**answer, "confidence": 2})


def test_model_without_strict_support_gets_plain_tool():
    bodies = []
    client = _client(
        "claude-sonnet-4-6", [httpx.Response(200, json=_message(_tool_use(ANSWER)))], bodies
    )

    _ask(client)
    tool = bodies[0]["tools"][0]
    assert "strict" not in tool
    assert tool["input_schema"] == Curation.model_json_schema()


def test_schema_rejected_by_strict_mode_is_resent_plain():
    bodies = []
    rejection = {
        "type": "error",
        "error": {
            "type": "invalid_request_error",
            "message": "Schema is not supported by strict mode",
        },
    }
    client = _client(
        "claude-sonnet-5",
        [
            httpx.Response(400, json=rejection),
            httpx.Response(200, json=_message(_tool_use(ANSWER))),
        ],
        bodies,
    )

    assert _ask(client) == Curation.model_validate(ANSWER)
    assert bodies[0]["tools"][0]["strict"] is True
    assert "strict" not in bodies[1]["tools"][0]


def test_other_bad_request_is_not_retried():
    import anthropic

    bodies = []
    rejection = {
        "type": "error",
        "error": {"type": "invalid_request_error", "message": "prompt too long"},
    }
    client = _client("claude-sonnet-5", [httpx.Response(400, json=rejection)], bodies)

    with pytest.raises(anthropic.BadRequestError):
        _ask(client)
    assert len(bodies) == 1


@pytest.mark.parametrize("model", ["claude-sonnet-5-5", "claude-opus-5-5"])
def test_models_that_reject_forced_tools_get_auto(model):
    bodies = []
    client = _client(model, [httpx.Response(200, json=_message(_tool_use(ANSWER)))], bodies)

    _ask(client)
    assert bodies[0]["tool_choice"] == {"type": "auto"}
    assert "Curation" in bodies[0]["system"]


def test_truncated_tool_input_names_the_limit():
    bodies = []
    cut = _message(_tool_use({}), stop_reason="max_tokens")
    client = _client("claude-sonnet-5", [httpx.Response(200, json=cut)], bodies)

    with pytest.raises(ValueError, match="ANTHROPIC_MAX_TOKENS"):
        _ask(client)


def test_default_max_tokens_fits_large_structured_output(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_MAX_TOKENS", raising=False)
    bodies = []
    client = _client(
        "claude-sonnet-5", [httpx.Response(200, json=_message(_tool_use(ANSWER)))], bodies
    )

    _ask(client)
    assert bodies[0]["max_tokens"] == 16000
