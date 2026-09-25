"""Canonical messages and token limits reach Anthropic's real HTTP boundary."""

import copy
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


def _client(handler):
    return create_llm_client(
        get_llm_config(
            "anthropic",
            api_key="test-key",
            model="claude-test",
            max_retries=0,
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
    )


@pytest.mark.parametrize("token_key", ["max_tokens", "max_completion_tokens", "max_output_tokens"])
def test_chat_converts_inline_images_system_lists_and_token_aliases(token_key):
    requests = []

    def handle(request):
        assert request.url.path == "/v1/messages"
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=_response([{"type": "text", "text": "OK"}]))

    messages = [
        {"role": "system", "content": [{"type": "text", "text": "Read receipts."}]},
        {"role": "system", "content": "Preserve decimal amounts."},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What is the total?"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,aW1hZ2U="}},
            ],
        },
    ]
    before = copy.deepcopy(messages)
    client = _client(handle)
    try:
        result = client.chat(messages, **{token_key: 123})
    finally:
        client.raw.close()

    assert result.text == "OK"
    assert result.usage == {"prompt_tokens": 8, "completion_tokens": 3}
    assert messages == before
    payload = requests[0]
    assert payload["system"] == "Read receipts.\n\nPreserve decimal amounts."
    assert payload["max_tokens"] == 123
    assert "max_completion_tokens" not in payload
    assert "max_output_tokens" not in payload
    assert payload["messages"] == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What is the total?"},
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": "aW1hZ2U="},
                },
            ],
        }
    ]


def test_parsed_call_keeps_image_and_forced_tool_schema():
    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        block = {"type": "tool_use", "id": "tool_test", "name": "Receipt", "input": {"total": 9.5}}
        return httpx.Response(200, json=_response([block]))

    client = _client(handle)
    try:
        result = client.chat_parsed(
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/png;base64,aW1hZ2U=",
                            },
                        }
                    ],
                }
            ],
            Receipt,
            max_output_tokens=321,
        )
    finally:
        client.raw.close()

    assert result == Receipt(total=9.5)
    assert requests[0]["max_tokens"] == 321
    assert requests[0]["tool_choice"] == {"type": "tool", "name": "Receipt"}
    assert requests[0]["tools"][0]["input_schema"]["properties"]["total"]["type"] == "number"
    assert requests[0]["messages"][0]["content"][0]["source"]["media_type"] == "image/png"


def test_stream_translates_token_alias_at_http_boundary():
    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        events = [
            ("message_start", {"type": "message_start", "message": _response([])}),
            (
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                },
            ),
            (
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "OK"},
                },
            ),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            ("message_stop", {"type": "message_stop"}),
        ]
        sse = "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=sse)

    client = _client(handle)
    try:
        result = list(
            client.chat_stream(
                [
                    {"role": "system", "content": [{"type": "text", "text": "Be brief."}]},
                    {"role": "user", "content": "Say OK"},
                ],
                max_completion_tokens=17,
            )
        )
    finally:
        client.raw.close()
    assert result == ["OK"]
    assert requests[0]["stream"] is True
    assert requests[0]["max_tokens"] == 17
    assert requests[0]["system"] == "Be brief."


@pytest.mark.parametrize(
    ("messages", "options", "error"),
    [
        (
            [{"role": "user", "content": "Hi"}],
            {"max_tokens": 1, "max_output_tokens": 2},
            "only one token limit",
        ),
        (
            [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/png;base64,aW1hZ2U=",
                            },
                        }
                    ],
                }
            ],
            {},
            "system messages require text",
        ),
        (
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "https://example.com/private.png",
                            },
                        }
                    ],
                }
            ],
            {},
            "base64 data:image",
        ),
    ],
)
def test_invalid_messages_and_conflicting_token_limits_fail_before_http(messages, options, error):
    def unexpected_request(request):
        pytest.fail("Invalid input must fail before an HTTP request")

    client = _client(unexpected_request)
    try:
        with pytest.raises(ValueError, match=error):
            client.chat(messages, **options)
    finally:
        client.raw.close()
