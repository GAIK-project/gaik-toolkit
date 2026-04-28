"""Provider-specific helpers that normalize raw SDK usage payloads.

Each provider returns token counts in a slightly different shape; these
helpers map those shapes onto the canonical dict that
:func:`gaik.observability.build_usage_record` consumes:

    {"input_tokens", "output_tokens", "thinking_tokens", "total_tokens"}

Only OpenAI is currently promoted here — Anthropic and Google variants
still live in ``multimodal_parser`` and can move when a second consumer
needs them.
"""

from __future__ import annotations

from typing import Any


def openai_usage_to_dict(response: Any) -> dict[str, int]:
    """Normalize a usage payload from the OpenAI SDK.

    Handles both the chat completions shape (``prompt_tokens`` /
    ``completion_tokens``) and the Responses API shape (``input_tokens`` /
    ``output_tokens``). When the response carries reasoning-token details
    (o-series, gpt-5.x), they are surfaced as ``thinking_tokens``.

    A response without a usage object yields all-zero counts so callers
    can still build a UsageRecord and report duration without raising.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "thinking_tokens": 0,
            "total_tokens": 0,
        }
    input_tok = getattr(usage, "input_tokens", None) or getattr(usage, "prompt_tokens", 0) or 0
    output_tok = (
        getattr(usage, "output_tokens", None) or getattr(usage, "completion_tokens", 0) or 0
    )
    total_tok = getattr(usage, "total_tokens", 0) or (input_tok + output_tok)
    details = getattr(usage, "output_tokens_details", None) or getattr(
        usage, "completion_tokens_details", None
    )
    thinking_tok = getattr(details, "reasoning_tokens", 0) or 0 if details else 0
    return {
        "input_tokens": int(input_tok),
        "output_tokens": int(output_tok),
        "thinking_tokens": int(thinking_tok),
        "total_tokens": int(total_tok),
    }
