"""Unit tests for the new TranscriptEnhancer parameters.

Covers:
- ``reasoning_effort`` is forwarded to the underlying chat call only when set,
  so existing callers and providers without that parameter are unaffected.
- ``progress_callback`` fires the four documented events around pass1/pass2
  in order, with monotonic char counts.
- A misbehaving callback never breaks the enhancement run.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from gaik.software_components.enhance_transcript.enhance_transcript import (
    TranscriptEnhancer,
    TranscriptEnhancerResult,
)


def _build_enhancer(
    *,
    reasoning_effort: str | None = None,
    chat_return: str = "enhanced output",
) -> tuple[TranscriptEnhancer, MagicMock]:
    """Build an enhancer with ``_chat_text`` stubbed to return a real string.

    Stubbing _chat_text directly avoids the brittleness of mocking the
    full client.chat.completions.create chain (pydantic 2.13+ rejects
    the auto-attribute MagicMock that would otherwise leak into
    TranscriptEnhancerResult.enhanced_text).
    """
    enhancer = TranscriptEnhancer.__new__(TranscriptEnhancer)
    enhancer.api_config = {"api_key": "test", "use_azure": True}
    enhancer.model = "gpt-test"
    enhancer.reasoning_effort = reasoning_effort
    enhancer.client = MagicMock()
    chat_stub = MagicMock(return_value=chat_return)
    enhancer._chat_text = chat_stub  # type: ignore[method-assign]
    return enhancer, chat_stub


def test_enhance_text_returns_pydantic_result():
    enhancer, _ = _build_enhancer()
    result = enhancer.enhance_text("Joku teksti tähän.")
    assert isinstance(result, TranscriptEnhancerResult)
    assert result.original_text == "Joku teksti tähän."
    assert result.enhanced_text == "enhanced output"


def test_progress_callback_fires_in_order():
    enhancer, _ = _build_enhancer()
    events: list[tuple[str, dict[str, Any]]] = []

    enhancer.enhance_text(
        "Joku teksti tähän.",
        progress_callback=lambda evt, payload: events.append((evt, payload)),
    )

    assert [e[0] for e in events] == [
        "pass1_started",
        "pass1_completed",
        "pass2_started",
        "pass2_completed",
    ]
    for _evt, payload in events:
        assert isinstance(payload.get("chars"), int)
        assert payload["chars"] > 0


def test_progress_callback_failure_is_swallowed():
    enhancer, _ = _build_enhancer()
    calls: list[str] = []

    def boom(event: str, _payload: dict[str, Any]) -> None:
        calls.append(event)
        raise RuntimeError("observer exploded")

    # Must not raise — observer errors are isolated from the pipeline
    result = enhancer.enhance_text("Joku teksti tähän.", progress_callback=boom)
    assert isinstance(result, TranscriptEnhancerResult)
    assert calls == ["pass1_started", "pass1_completed", "pass2_started", "pass2_completed"]


# --- _chat_text-level tests: confirm reasoning_effort actually reaches the API ---
#
# NB: ProviderClient is a ``@runtime_checkable`` Protocol, and a bare
# ``MagicMock()`` satisfies its hasattr-based instance check (every
# attribute is auto-mocked). That made _chat_text take the ProviderClient
# branch on Python 3.11 (CI) even though the test wanted the raw-OpenAI
# branch. We use a concrete dummy class so isinstance(client, ProviderClient)
# is unambiguously False — chat is a regular attribute, the protocol's other
# required members (chat_parsed, chat_stream, embed, provider, model, raw)
# are deliberately absent.


class _FakeRawOpenAIClient:
    """Stand-in for the openai.OpenAI client (NOT a ProviderClient)."""

    def __init__(self):
        self.chat = MagicMock()


def test_reasoning_effort_omitted_by_default_in_chat_call():
    """With reasoning_effort=None, the kwarg must NOT be passed to the API
    so providers/models that don't support it are unaffected."""
    enhancer = TranscriptEnhancer.__new__(TranscriptEnhancer)
    enhancer.api_config = {"api_key": "test", "use_azure": True}
    enhancer.model = "gpt-test"
    enhancer.reasoning_effort = None

    fake_response = MagicMock()
    choice = MagicMock()
    choice.message.content = "enhanced output"
    fake_response.choices = [choice]
    enhancer.client = _FakeRawOpenAIClient()
    enhancer.client.chat.completions.create.return_value = fake_response

    enhancer._chat_text([{"role": "user", "content": "hi"}], fallback="x")

    call_kwargs = enhancer.client.chat.completions.create.call_args.kwargs
    assert "reasoning_effort" not in call_kwargs


def test_reasoning_effort_forwarded_to_chat_call_when_set():
    enhancer = TranscriptEnhancer.__new__(TranscriptEnhancer)
    enhancer.api_config = {"api_key": "test", "use_azure": True}
    enhancer.model = "gpt-test"
    enhancer.reasoning_effort = "minimal"

    fake_response = MagicMock()
    choice = MagicMock()
    choice.message.content = "enhanced output"
    fake_response.choices = [choice]
    enhancer.client = _FakeRawOpenAIClient()
    enhancer.client.chat.completions.create.return_value = fake_response

    enhancer._chat_text([{"role": "user", "content": "hi"}], fallback="x")

    call_kwargs = enhancer.client.chat.completions.create.call_args.kwargs
    assert call_kwargs.get("reasoning_effort") == "minimal"


def test_reasoning_effort_forwarded_through_provider_client_path():
    """The ProviderClient branch (LiteLLM-style adapter) must also thread
    reasoning_effort through, otherwise providers that do support it would
    silently ignore the user's setting."""
    from gaik.software_components.llm.base import ProviderClient

    enhancer = TranscriptEnhancer.__new__(TranscriptEnhancer)
    enhancer.api_config = {"api_key": "test", "use_azure": True}
    enhancer.model = "gpt-test"
    enhancer.reasoning_effort = "medium"

    provider = MagicMock(spec=ProviderClient)
    provider.chat.return_value = MagicMock(text="enhanced output")
    enhancer.client = provider

    enhancer._chat_text([{"role": "user", "content": "hi"}], fallback="x")

    call_kwargs = provider.chat.call_args.kwargs
    assert call_kwargs.get("reasoning_effort") == "medium"
    assert call_kwargs.get("model") == "gpt-test"
    assert call_kwargs.get("temperature") == 0.0
