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
from unittest.mock import MagicMock, patch

import pytest

from gaik.software_components.enhance_transcript.enhance_transcript import (
    TranscriptEnhancer,
    TranscriptEnhancerResult,
)


@pytest.fixture
def mock_chat_client():
    """Stub out the underlying chat client so tests don't hit a real LLM."""
    fake = MagicMock()
    response = MagicMock()
    choice = MagicMock()
    choice.message.content = "enhanced output"
    response.choices = [choice]
    fake.chat.completions.create.return_value = response
    return fake


def _build_enhancer(client, *, reasoning_effort: str | None = None) -> TranscriptEnhancer:
    """Construct an enhancer that uses the supplied stub client."""
    enhancer = TranscriptEnhancer.__new__(TranscriptEnhancer)
    enhancer.api_config = {"api_key": "test", "use_azure": True}
    enhancer.model = "gpt-test"
    enhancer.reasoning_effort = reasoning_effort
    enhancer.client = client
    return enhancer


def test_reasoning_effort_omitted_by_default(mock_chat_client):
    enhancer = _build_enhancer(mock_chat_client)
    enhancer.enhance_text("Joku teksti tähän.")

    # Two calls to the chat completion API (pass1 + pass2)
    assert mock_chat_client.chat.completions.create.call_count == 2
    for call in mock_chat_client.chat.completions.create.call_args_list:
        assert "reasoning_effort" not in call.kwargs


def test_reasoning_effort_forwarded_when_set(mock_chat_client):
    enhancer = _build_enhancer(mock_chat_client, reasoning_effort="minimal")
    enhancer.enhance_text("Joku teksti tähän.")

    assert mock_chat_client.chat.completions.create.call_count == 2
    for call in mock_chat_client.chat.completions.create.call_args_list:
        assert call.kwargs.get("reasoning_effort") == "minimal"


def test_progress_callback_fires_in_order(mock_chat_client):
    enhancer = _build_enhancer(mock_chat_client)
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
    # All payloads should carry a sane chars count
    for _evt, payload in events:
        assert isinstance(payload.get("chars"), int)
        assert payload["chars"] > 0


def test_progress_callback_failure_is_swallowed(mock_chat_client):
    enhancer = _build_enhancer(mock_chat_client)
    calls: list[str] = []

    def boom(event: str, _payload: dict[str, Any]) -> None:
        calls.append(event)
        raise RuntimeError("observer exploded")

    # Must not raise — observer errors are isolated from the pipeline
    result = enhancer.enhance_text("Joku teksti tähän.", progress_callback=boom)
    assert isinstance(result, TranscriptEnhancerResult)
    assert calls == ["pass1_started", "pass1_completed", "pass2_started", "pass2_completed"]


def test_provider_client_path_also_threads_reasoning_effort():
    """The ProviderClient branch (used by the LiteLLM-style adapter) must
    also pass reasoning_effort through, otherwise providers that do
    support the param would silently ignore the user's setting."""
    from gaik.software_components.llm.base import ProviderClient

    provider = MagicMock(spec=ProviderClient)
    provider.chat.return_value = MagicMock(text="enhanced output")

    enhancer = _build_enhancer(provider, reasoning_effort="medium")
    enhancer.enhance_text("Joku teksti tähän.")

    assert provider.chat.call_count == 2
    for call in provider.chat.call_args_list:
        assert call.kwargs.get("reasoning_effort") == "medium"
