"""OpenTelemetry spans for gaik's LLM calls (optional ``gaik[otel]`` extra).

Each instrumented model call becomes one ``chat <model>`` span with the
OpenTelemetry GenAI names (``gen_ai.*``) and gaik's own (``gaik.*``): which
component made the call, the provider, model and settings, tokens, an estimated
cost and a configuration version. Only lengths of the input and output are
recorded, never their text, and an error is recorded by its type, never its
message.

Enabled by the standard environment variables only:

- ``OTEL_EXPORTER_OTLP_ENDPOINT``: where spans go, e.g. ``http://127.0.0.1:4318``.
- ``OTEL_SERVICE_NAME``: the service the spans belong to.
- ``OTEL_RESOURCE_ATTRIBUTES``: extra resource attributes, e.g.
  ``gaik.run.id=...,gaik.config.blueprint_version=3``.

Without the extra, or without an endpoint and with no tracer provider set by
the application, every call here is a no-op and gaik behaves as before. An
application that sets its own tracer provider gets gaik's spans in it. A fault
in the instrumentation is logged and never reaches the caller.

The ``gaik.*`` attribute names are a draft until the event schema v1.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import logging
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from .usage import UsageRecord

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_tracer: Any = None
_resolved = False


def _gaik_version() -> str:
    try:
        from gaik import __version__

        return __version__
    except Exception:  # pragma: no cover - only when gaik itself is half-imported
        return "unknown"


def _get_tracer() -> Any:
    """The tracer for gaik's spans, or ``None`` when tracing is off. Resolved once."""
    global _tracer, _resolved
    if _resolved:
        return _tracer
    with _lock:
        if _resolved:
            return _tracer
        try:
            _tracer = _resolve_tracer()
        except Exception:
            logger.debug("gaik tracing could not be set up", exc_info=True)
            _tracer = None
        _resolved = True
    return _tracer


def _resolve_tracer() -> Any:
    try:
        from opentelemetry import trace
    except ImportError:
        return None
    if not isinstance(trace.get_tracer_provider(), trace.ProxyTracerProvider):
        # The application set a provider: use it, whatever it exports to.
        return trace.get_tracer("gaik", _gaik_version())
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return None
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    # Resource.create() reads OTEL_SERVICE_NAME and OTEL_RESOURCE_ATTRIBUTES itself.
    provider = TracerProvider(resource=Resource.create({}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    # Short scripts (a PoC run) exit right after their last call: flush first.
    atexit.register(provider.shutdown)
    return trace.get_tracer("gaik", _gaik_version())


def config_version(**fields: Any) -> str:
    """A stable id for a configuration: the same fields give the same id.

    The id is the first 16 hex characters of the SHA-256 of the fields as
    canonical JSON (sorted keys). ``None`` values are left out, so adding an
    unset option does not change the id.
    """
    data = {k: v for k, v in fields.items() if v is not None}
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


class LLMCallSpan:
    """Handle for an open ``llm_span``; ``record`` adds the call's result."""

    def __init__(self, span: Any) -> None:
        self._span = span

    def record(self, usage: UsageRecord | None, *, output_length: int | None = None) -> None:
        """Add tokens, estimated cost and the output's length. Never raises."""
        if self._span is None:
            return
        try:
            attributes: dict[str, Any] = {"gaik.output.length": output_length}
            if usage is not None:
                attributes.update(
                    {
                        "gen_ai.response.model": usage.model,
                        "gen_ai.usage.input_tokens": usage.input_tokens,
                        "gen_ai.usage.output_tokens": usage.output_tokens,
                        "gaik.usage.thinking_tokens": usage.thinking_tokens,
                        "gaik.cost.usd": usage.cost_usd,
                        "gaik.cost.estimated": True,
                    }
                )
            self._span.set_attributes({k: v for k, v in attributes.items() if v is not None})
        except Exception:
            logger.debug("gaik tracing could not record a result", exc_info=True)


@contextmanager
def llm_span(
    component: str,
    *,
    provider: str,
    model: str,
    settings: dict[str, Any] | None = None,
    input_length: int | None = None,
    prompt_version: str | None = None,
) -> Iterator[LLMCallSpan]:
    """Wrap one model call in a ``chat <model>`` span.

    ``settings`` are the request's sampling options (``temperature``,
    ``max_tokens``, ``reasoning_effort`` ...); ``None`` values are left out.
    The call's own exception passes through unchanged; the span records only
    its type.
    """
    span = _start(component, provider, model, settings or {}, input_length, prompt_version)
    handle = LLMCallSpan(span)
    try:
        yield handle
    except BaseException as exc:
        _fail(span, exc)
        raise
    finally:
        _end(span)


def _start(
    component: str,
    provider: str,
    model: str,
    settings: dict[str, Any],
    input_length: int | None,
    prompt_version: str | None,
) -> Any:
    tracer = _get_tracer()
    if tracer is None:
        return None
    try:
        from opentelemetry.trace import SpanKind

        settings = {k: v for k, v in settings.items() if v is not None}
        version = _gaik_version()
        attributes: dict[str, Any] = {
            "gaik.event.class": "llm_call",
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": provider,
            "gen_ai.request.model": model,
            "gaik.component.name": component,
            "gaik.component.version": version,
            "gaik.prompt.version": prompt_version,
            "gaik.input.length": input_length,
            "gaik.config.version": config_version(
                component=component,
                version=version,
                provider=provider,
                model=model,
                settings=settings,
                prompt_version=prompt_version,
            ),
        }
        for key, value in settings.items():
            name = {
                "temperature": "gen_ai.request.temperature",
                "max_tokens": "gen_ai.request.max_tokens",
                "top_p": "gen_ai.request.top_p",
            }.get(key, f"gaik.request.{key}")
            attributes[name] = value if isinstance(value, (bool, int, float, str)) else str(value)
        return tracer.start_span(
            f"chat {model}",
            kind=SpanKind.CLIENT,
            attributes={k: v for k, v in attributes.items() if v is not None},
        )
    except Exception:
        logger.debug("gaik tracing could not start a span", exc_info=True)
        return None


def _fail(span: Any, exc: BaseException) -> None:
    if span is None:
        return
    try:
        from opentelemetry.trace import Status, StatusCode

        # The type only: an exception's message may quote the prompt or document.
        span.set_attribute("error.type", type(exc).__qualname__)
        span.set_status(Status(StatusCode.ERROR))
    except Exception:
        logger.debug("gaik tracing could not record an error", exc_info=True)


def _end(span: Any) -> None:
    if span is None:
        return
    try:
        span.end()
    except Exception:
        logger.debug("gaik tracing could not end a span", exc_info=True)


def _reset_for_tests() -> None:
    """Forget the resolved tracer so the next call resolves it again."""
    global _tracer, _resolved
    with _lock:
        _tracer = None
        _resolved = False
