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
