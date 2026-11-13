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


def sdk_usage(response: Any) -> dict[str, int]:
    """Token counts from any provider SDK's response, for a trace span.

    Reads OpenAI and Azure (Chat Completions, Responses, embeddings and
    transcription), LiteLLM, Anthropic and Google responses, and a Gemini REST
    ``generateContent`` payload. Returns ``input_tokens`` and ``output_tokens``
    and, when the response reports them, ``thinking_tokens``,
    ``cache_read_input_tokens`` and ``cache_creation_input_tokens``. Input
    counts include cached input; output counts include thinking. An empty dict
    means the response reports no tokens. Only integers are read.
    """
    meta = _child(response, "usage_metadata") or _child(response, "usageMetadata")
    if meta is not None and (
        _count(meta, "prompt_token_count", "promptTokenCount") is not None
        or _count(meta, "candidates_token_count", "candidatesTokenCount") is not None
    ):
        thoughts = _count(meta, "thoughts_token_count", "thoughtsTokenCount")
        counts = {
            "input_tokens": _count(meta, "prompt_token_count", "promptTokenCount") or 0,
            # Gemini counts thinking apart from the answer and bills it as output.
            "output_tokens": (_count(meta, "candidates_token_count", "candidatesTokenCount") or 0)
            + (thoughts or 0),
            "thinking_tokens": thoughts,
            "cache_read_input_tokens": _count(
                meta, "cached_content_token_count", "cachedContentTokenCount"
            ),
        }
        return _kept(counts)
    usage = _child(response, "usage")
    if usage is None:
        return {}
    prompt = _count(usage, "prompt_tokens")
    output = _count(usage, "output_tokens", "completion_tokens")
    details = _child(usage, "output_tokens_details") or _child(usage, "completion_tokens_details")
    cached = _child(usage, "input_tokens_details") or _child(usage, "prompt_tokens_details")
    if prompt is not None:
        # Chat Completions style (OpenAI, Azure, LiteLLM): cached input is
        # already part of prompt_tokens.
        counts = {
            "input_tokens": prompt,
            "cache_read_input_tokens": _count(usage, "cache_read_input_tokens")
            if _count(usage, "cache_read_input_tokens") is not None
            else _count(cached, "cached_tokens"),
            "cache_creation_input_tokens": _count(usage, "cache_creation_input_tokens"),
        }
    else:
        # Responses API (input includes cache) or Anthropic (input excludes the
        # cache reads and writes, which it reports apart).
        read = _count(usage, "cache_read_input_tokens")
        write = _count(usage, "cache_creation_input_tokens")
        counts = {
            "input_tokens": (_count(usage, "input_tokens") or 0) + (read or 0) + (write or 0),
            "cache_read_input_tokens": read
            if read is not None
            else _count(cached, "cached_tokens"),
            "cache_creation_input_tokens": write,
        }
    counts["output_tokens"] = output or 0
    counts["thinking_tokens"] = _count(details, "reasoning_tokens")
    return _kept(counts)


def _child(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _count(obj: Any, *names: str) -> int | None:
    """The first of ``names`` on ``obj`` that holds an integer, else ``None``."""
    for name in names:
        value = _child(obj, name)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def _kept(counts: dict[str, int | None]) -> dict[str, int]:
    if not (counts.get("input_tokens") or counts.get("output_tokens")):
        return {}
    return {k: v for k, v in counts.items() if v is not None}
