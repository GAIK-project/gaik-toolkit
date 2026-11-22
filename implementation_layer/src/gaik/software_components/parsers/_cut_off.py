"""Whether a model's reply stopped at its output-token cap.

A reply cut off there ends mid-document and looks complete. The parsers read the
provider's stop reason from the raw response and fall back or report it.
"""

from __future__ import annotations

from typing import Any

# Anthropic's stop reasons for a reply cut off by a limit rather than finished.
_ANTHROPIC_CUT_OFF = frozenset({"max_tokens", "model_context_window_exceeded"})


class Reply(str):
    """A model's text, with ``cut_off`` true when it stopped at the output-token cap."""

    cut_off: bool

    def __new__(cls, text: str, cut_off: bool = False) -> Reply:
        reply = super().__new__(cls, text)
        reply.cut_off = cut_off
        return reply


def _field(source: Any, name: str) -> Any:
    if isinstance(source, dict):
        return source.get(name)
    return getattr(source, name, None)


def _first(items: Any) -> Any:
    return items[0] if isinstance(items, (list, tuple)) and items else None


def reply_cut_off(raw: Any) -> bool:
    """True when a provider's raw response says its output stopped at the token cap.

    Reads OpenAI Chat Completions and LiteLLM (``finish_reason == "length"``), the
    OpenAI Responses API (``status == "incomplete"`` for ``max_output_tokens``),
    Anthropic (``stop_reason == "max_tokens"``) and Gemini (``finish_reason`` or
    ``finishReason`` ``MAX_TOKENS``), as SDK objects or as REST JSON. Anything else,
    including a response without a stop reason, is not cut off.
    """
    if raw is None:
        return False
    choice = _first(_field(raw, "choices"))
    if choice is not None and _field(choice, "finish_reason") == "length":
        return True
    if _field(raw, "status") == "incomplete":
        reason = _field(_field(raw, "incomplete_details"), "reason")
        if reason in (None, "max_output_tokens"):
            return True
    if _field(raw, "stop_reason") in _ANTHROPIC_CUT_OFF:
        return True
    candidate = _first(_field(raw, "candidates"))
    if candidate is not None:
        reason = _field(candidate, "finish_reason") or _field(candidate, "finishReason")
        if str(getattr(reason, "name", reason)).upper().endswith("MAX_TOKENS"):
            return True
    return False
