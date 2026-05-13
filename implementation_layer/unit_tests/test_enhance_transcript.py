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
    PASS1_SYSTEM_PROMPT,
    PASS2_SYSTEM_PROMPT,
    TranscriptEnhancer,
    TranscriptEnhancerResult,
    apply_domain_rules,
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
    result = enhancer.enhance_text("Some sample transcript text.")
    assert isinstance(result, TranscriptEnhancerResult)
    assert result.original_text == "Some sample transcript text."
    assert result.enhanced_text == "enhanced output"


def test_progress_callback_fires_in_order():
    enhancer, _ = _build_enhancer()
    events: list[tuple[str, dict[str, Any]]] = []

    enhancer.enhance_text(
        "Some sample transcript text.",
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
    result = enhancer.enhance_text("Some sample transcript text.", progress_callback=boom)
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


# --- domain_rules parameter tests ---


def testapply_domain_rules_none_removes_placeholder_cleanly():
    """When domain_rules is None, the {DOMAIN_RULES} placeholder must be
    removed without leaving stray blank lines — keeps the prompt
    byte-identical to the pre-feature shape for backward compat."""
    result = apply_domain_rules(PASS1_SYSTEM_PROMPT, None)
    assert "{DOMAIN_RULES}" not in result
    # No double-blank-line artifact where the placeholder used to live
    assert "\n\n\n" not in result
    assert "DOMAIN-SPECIFIC RULES" not in result


def testapply_domain_rules_empty_string_removes_placeholder():
    """An empty or whitespace-only string is treated like None."""
    for empty in ["", "   ", "\n\n", "\t"]:
        result = apply_domain_rules(PASS1_SYSTEM_PROMPT, empty)
        assert "{DOMAIN_RULES}" not in result
        assert "DOMAIN-SPECIFIC RULES" not in result


def testapply_domain_rules_with_text_injects_at_placeholder():
    rule = "DOMAIN OVERRIDE: normalize tooth refs like 'ykskakkonen' to '#12'."
    result = apply_domain_rules(PASS1_SYSTEM_PROMPT, rule)
    assert "{DOMAIN_RULES}" not in result
    assert "DOMAIN-SPECIFIC RULES" in result
    assert rule in result
    # The block lands BEFORE the Output: section, so the LLM reads
    # domain exceptions after the general safety rules — last instruction
    # in the conflict wins.
    assert result.index("DOMAIN-SPECIFIC RULES") < result.index("Output:")


def testapply_domain_rules_works_on_pass2_prompt_too():
    rule = "test rule"
    result = apply_domain_rules(PASS2_SYSTEM_PROMPT, rule)
    assert "{DOMAIN_RULES}" not in result
    assert "DOMAIN-SPECIFIC RULES" in result
    assert rule in result


def test_enhance_text_threads_domain_rules_through_both_passes():
    """When domain_rules is passed, it must reach _enhance_pass1 AND
    _enhance_pass2 — otherwise pass1's number safety rule wins."""
    enhancer, _chat_stub = _build_enhancer()
    pass1_calls: list[str | None] = []
    pass2_calls: list[str | None] = []

    # Capture which domain_rules each pass receives
    orig_pass1 = TranscriptEnhancer._enhance_pass1
    orig_pass2 = TranscriptEnhancer._enhance_pass2

    def spy_pass1(self, text, *, domain_rules=None):
        pass1_calls.append(domain_rules)
        return orig_pass1(self, text, domain_rules=domain_rules)

    def spy_pass2(self, text, *, additional_instructions=None, domain_rules=None):
        pass2_calls.append(domain_rules)
        return orig_pass2(
            self,
            text,
            additional_instructions=additional_instructions,
            domain_rules=domain_rules,
        )

    enhancer._enhance_pass1 = spy_pass1.__get__(enhancer)
    enhancer._enhance_pass2 = spy_pass2.__get__(enhancer)

    enhancer.enhance_text("Some sample text.", domain_rules="MY_DOMAIN_RULE")

    assert pass1_calls == ["MY_DOMAIN_RULE"]
    assert pass2_calls == ["MY_DOMAIN_RULE"]


def test_enhance_text_domain_rules_default_none_remains_backward_compatible():
    """Existing callers (no domain_rules) must still get the bare PASS prompts."""
    enhancer, chat_stub = _build_enhancer()
    enhancer.enhance_text("Some sample text.")

    # Both pass1 and pass2 stub-calls should have system prompts without DOMAIN-SPECIFIC RULES
    for call in chat_stub.call_args_list:
        messages = call.args[0] if call.args else call.kwargs.get("messages", [])
        sys_msg = next((m for m in messages if m["role"] == "system"), None)
        assert sys_msg is not None
        assert "DOMAIN-SPECIFIC RULES" not in sys_msg["content"]
        assert "{DOMAIN_RULES}" not in sys_msg["content"]


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
