"""Optional, bounded demo telemetry. Never sends user content or affects a request.

This adapter belongs to the demo, not the gaik library. Both OPS_URL and
OPS_INGEST_KEY must be set. Delivery runs in daemon threads, with no retries,
at most four in flight and 60 attempts per minute per process. Excess events
are dropped. Request bodies, headers, URLs, exception messages and responses
are never inspected. Only matched route templates, status, timings and explicit
usage records are reported.
"""

from __future__ import annotations

import contextlib
import math
import os
import re
import threading
import time
import uuid
from collections import deque
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

_slots = threading.BoundedSemaphore(4)
_lock = threading.Lock()
_attempts: deque[float] = deque()
_MAX_MS = 3_600_000
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}\Z")


def enabled() -> bool:
    return bool(os.getenv("OPS_URL") and os.getenv("OPS_INGEST_KEY"))


def report(kind: str, message: str, data: dict, trace_id: str) -> None:
    """Best effort, bounded and non-blocking, including setup/serialization failure."""
    with contextlib.suppress(Exception):
        url = os.getenv("OPS_URL", "").rstrip("/")
        key = os.getenv("OPS_INGEST_KEY")
        if not url or not key:
            return
        now = time.monotonic()
        with _lock:
            while _attempts and _attempts[0] <= now - 60:
                _attempts.popleft()
            if len(_attempts) >= 60 or not _slots.acquire(blocking=False):
                return
            _attempts.append(now)

        def send() -> None:
            try:
                import httpx

                httpx.post(
                    f"{url}/api/ingest",
                    headers={"authorization": f"Bearer {key}"},
                    json={
                        "app": "gaik-demo-api",
                        "kind": kind,
                        "message": message,
                        "data": data,
                        "trace_id": trace_id,
                    },
                    timeout=3,
                    follow_redirects=False,
                )
            except Exception:
                pass
            finally:
                _slots.release()

        try:
            threading.Thread(target=send, daemon=True, name="demo-ops").start()
        except Exception:
            _slots.release()


@dataclass
class RequestTrace:
    started: float = field(default_factory=time.monotonic)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    calls: list[dict[str, Any]] = field(default_factory=list)


_trace: ContextVar[RequestTrace | None] = ContextVar("demo_ops_trace", default=None)


def _number(value: Any) -> float | None:
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    ):
        return value
    return None


def record_llm(usage: dict[str, Any]) -> None:
    """Accept only numeric usage and model/provider identifiers, never free text."""
    with contextlib.suppress(Exception):
        trace = _trace.get()
        if trace is None or len(trace.calls) >= 63:
            return
        data: dict[str, Any] = {}
        for key in ("model", "provider"):
            value = usage.get(key)
            if isinstance(value, str) and _IDENTIFIER.fullmatch(value):
                data[key] = value
        for key in ("input_tokens", "output_tokens"):
            value = _number(usage.get(key))
            if value is not None:
                data[key] = value
        duration = min((_number(usage.get("duration_s")) or 0) * 1000, _MAX_MS)
        elapsed = min((time.monotonic() - trace.started) * 1000, _MAX_MS)
        data["duration_ms"] = round(duration)
        data["start_ms"] = round(max(0, elapsed - duration))
        trace.calls.append(data)


class OpsMiddleware:
    """Keep streaming intact; record only completed operations and server failures."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not enabled():
            return await self.app(scope, receive, send)
        trace = RequestTrace()
        token = _trace.set(trace)
        status = 500
        failed = False
        completed = False

        async def tracked_send(message):
            nonlocal status, completed
            if message["type"] == "http.response.start":
                status = message["status"]
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                completed = True
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        except Exception:
            failed = True
            raise
        finally:
            _trace.reset(token)
            # Telemetry must not mask an exception or invalidate a successful response.
            with contextlib.suppress(Exception):
                route = getattr(scope.get("route"), "path", None)
                if route and (
                    failed
                    or status >= 500
                    or (
                        completed
                        and status < 400
                        and scope["method"] in {"POST", "PUT", "PATCH", "DELETE"}
                    )
                ):
                    duration = min(round((time.monotonic() - trace.started) * 1000), _MAX_MS)
                    root = {
                        "name": "HTTP request",
                        "kind": "step",
                        "start_ms": 0,
                        "dur_ms": duration,
                        "ok": not failed and status < 500,
                    }
                    spans = [root]
                    for call in trace.calls:
                        span = {
                            "name": "LLM judge",
                            "kind": "llm",
                            "parent": 0,
                            "start_ms": call["start_ms"],
                            "dur_ms": call["duration_ms"],
                            "ok": True,
                            **{
                                k: call[k]
                                for k in ("model", "input_tokens", "output_tokens")
                                if k in call
                            },
                        }
                        spans.append(span)
                        report(
                            "llm",
                            "LLM judge usage",
                            {
                                **{k: v for k, v in call.items() if k != "start_ms"},
                                "route": route,
                                "trace": [root, span],
                            },
                            trace.id,
                        )
                    report(
                        "error" if failed or status >= 500 else "log",
                        f"{scope['method']} {route}",
                        {
                            "route": route,
                            "status": 500 if failed else status,
                            "duration_ms": duration,
                            "trace": spans,
                        },
                        trace.id,
                    )
