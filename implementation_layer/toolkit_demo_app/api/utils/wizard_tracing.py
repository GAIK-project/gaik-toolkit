"""Optional, opt-in Solution Wizard diagnostics; no other demo is instrumented.

The CLI exposes streamed model usage, not raw HTTP requests. Turn input and
tool results provide context; individual generations never invent an input
transcript. Aggregate ResultMessage usage is metadata, avoiding double billing.
"""

from __future__ import annotations

import contextlib
import os
import re
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

_MAX_TEXT = 32_000
_MAX_OBSERVATIONS = 200
_KEY = re.compile(r"(?i)(?:sk-(?:ant-|proj-|lf-)?[\w-]{12,}|Bearer\s+[\w.=-]{12,})")
_SECRET_NAME = re.compile(r"(?i)key|token|secret|password|credential")
_SECRET_FIELD = re.compile(
    r"(?i)api[-_]?key|authorization|password|secret|access_token|refresh_token|credential"
)


def available() -> bool:
    url = urlparse(os.getenv("LANGFUSE_BASE_URL", ""))
    return (
        os.getenv("WIZARD_LANGFUSE_ENABLED") == "true"
        and url.scheme in {"http", "https"}
        and bool(url.hostname)
        and bool(os.getenv("LANGFUSE_PUBLIC_KEY"))
        and bool(os.getenv("LANGFUSE_SECRET_KEY"))
    )


def redact(value: Any, **_kwargs: Any) -> Any:
    """Bound content and remove known runtime credentials before export."""
    if isinstance(value, str):
        value = _KEY.sub("[redacted]", value[:_MAX_TEXT])
        for name, secret in os.environ.items():
            if _SECRET_NAME.search(name) and len(secret) >= 8:
                value = value.replace(secret, "[redacted]")
        return value
    if isinstance(value, dict):
        return {
            str(k): "[redacted]" if _SECRET_FIELD.search(str(k)) else redact(v)
            for k, v in list(value.items())[:100]
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value[:100]]
    return value


@lru_cache(maxsize=1)
def _client():
    from langfuse import Langfuse
    from opentelemetry.sdk.trace import TracerProvider

    # Dedicated provider: unrelated libraries and demos cannot export spans.
    return Langfuse(
        base_url=os.environ["LANGFUSE_BASE_URL"],
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        environment="wizard-pilot",
        tracer_provider=TracerProvider(),
        timeout=3,
        mask=redact,
    )


def _counts(raw: dict) -> dict[str, int]:
    # Anthropic input excludes cache reads/writes; keep exclusive buckets.
    mapping = {
        "input_tokens": "input",
        "output_tokens": "output",
        "cache_read_input_tokens": "cache_read_input_tokens",
        "cache_creation_input_tokens": "cache_creation_input_tokens",
    }
    return {
        target: raw[key]
        for key, target in mapping.items()
        if isinstance(raw.get(key), int) and not isinstance(raw[key], bool) and raw[key] >= 0
    }


class WizardTrace:
    """One user turn, its streamed generations and bounded tool observations."""

    def __init__(self, session_id: str, enabled: bool, prompt: str):
        self.root = None
        self.generations: dict[str, dict] = {}
        self.tools: dict[str, Any] = {}
        self.seen = 0
        self.session_id = session_id
        self.trace_id = None
        self.output: list[str] = []
        if enabled and available():
            with contextlib.suppress(Exception):
                from langfuse import propagate_attributes

                with propagate_attributes(session_id=session_id, tags=["solution-wizard-pilot"]):
                    self.root = _client().start_observation(
                        name="Solution Wizard turn", as_type="agent", input=redact(prompt)
                    )
                self.trace_id = self.root.trace_id

    def _child(self, **kwargs):
        if self.root is None or self.seen >= _MAX_OBSERVATIONS:
            return None
        from langfuse import propagate_attributes

        self.seen += 1
        with propagate_attributes(session_id=self.session_id, tags=["solution-wizard-pilot"]):
            return self.root.start_observation(**kwargs)

    def observe(self, message: Any) -> None:
        if self.root is None:
            return
        with contextlib.suppress(Exception):
            event = getattr(message, "event", None)
            if isinstance(event, dict):
                self._stream(event, getattr(message, "parent_tool_use_id", None) or "main")
            # Full messages carry tool inputs/results and final visible text.
            for block in getattr(message, "content", []) or []:
                if hasattr(block, "tool_use_id"):
                    span = self.tools.pop(block.tool_use_id, None)
                    if span:
                        span.update(
                            output=redact(block.content),
                            level="ERROR" if block.is_error else "DEFAULT",
                        )
                        span.end()
                elif hasattr(block, "name") and hasattr(block, "input"):
                    if block.id not in self.tools:
                        span = self._child(
                            name=block.name, as_type="tool", input=redact(block.input)
                        )
                        if span:
                            self.tools[block.id] = span
                elif hasattr(block, "text"):
                    if sum(map(len, self.output)) < _MAX_TEXT:
                        self.output.append(block.text[:_MAX_TEXT])
            if hasattr(message, "usage") and hasattr(message, "is_error"):
                self.root.update(
                    metadata={
                        "agent_usage": redact(message.usage),
                        "agent_cost_usd": getattr(message, "total_cost_usd", None),
                        "usage_scope": "aggregate turn; generation usage is counted separately",
                        "observation_limit": _MAX_OBSERVATIONS,
                    }
                )
                if message.is_error:
                    self.error("Agent returned an error")

    def _stream(self, event: dict, channel: str) -> None:
        kind = event.get("type")
        if kind == "message_start":
            self._end_generation(channel)
            msg = event.get("message", {})
            span = self._child(
                name="Claude model call",
                as_type="generation",
                model=msg.get("model"),
                metadata={
                    "input_context": (
                        "See parent turn and preceding tools; raw CLI prompt is unavailable"
                    )
                },
            )
            if span:
                self.generations[channel] = {
                    "span": span,
                    "usage": dict(msg.get("usage") or {}),
                    "text": "",
                }
        state = self.generations.get(channel)
        if not state:
            return
        if kind == "content_block_delta":
            delta = event.get("delta", {})
            # Do not persist extended thinking, signatures or binary payloads.
            text = delta.get("text", "") or delta.get("partial_json", "")
            state["text"] = (state["text"] + text)[:_MAX_TEXT]
        if kind == "message_delta":
            state["usage"].update(event.get("usage") or {})
        if kind == "message_stop":
            self._end_generation(channel)

    def _end_generation(self, channel: str) -> None:
        state = self.generations.pop(channel, None)
        if state:
            with contextlib.suppress(Exception):
                state["span"].update(
                    output=redact(state["text"]), usage_details=_counts(state["usage"])
                )
            with contextlib.suppress(Exception):
                state["span"].end()

    def error(self, reason: str) -> None:
        if self.root:
            with contextlib.suppress(Exception):
                self.root.update(level="ERROR", status_message=reason)

    def finish(self) -> None:
        if self.root is None:
            return
        for channel in list(self.generations):
            self._end_generation(channel)
        for span in self.tools.values():
            with contextlib.suppress(Exception):
                span.update(level="WARNING", status_message="Tool result unavailable at turn end")
            with contextlib.suppress(Exception):
                span.end()
        self.tools.clear()
        with contextlib.suppress(Exception):
            self.root.update(output=redact("\n".join(self.output)))
        with contextlib.suppress(Exception):
            self.root.end()
        # Bounded SDK exporter; network waits never hold the SSE response open.
