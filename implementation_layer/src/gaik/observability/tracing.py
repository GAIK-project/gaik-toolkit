"""OpenTelemetry spans for gaik's LLM calls (optional ``gaik[otel]`` extra).

Each instrumented model call becomes one ``chat <model>`` span with the
OpenTelemetry GenAI names (``gen_ai.*``) and gaik's own (``gaik.*``): which
component made the call, the provider, model and settings, tokens, an estimated
cost and a configuration version. Only lengths of the input and output are
recorded, never their text, and an error is recorded by its type, never its
message.

Enabled by the standard environment variables:

- ``OTEL_EXPORTER_OTLP_ENDPOINT`` (or ``OTEL_EXPORTER_OTLP_TRACES_ENDPOINT``):
  where spans go, e.g. ``http://127.0.0.1:4318``. gaik then exports its spans
  through a tracer provider of its own; it never sets the process-wide one, so
  an application keeps its own OpenTelemetry setup.
- ``OTEL_SERVICE_NAME``: the service the spans belong to.
- ``OTEL_RESOURCE_ATTRIBUTES``: extra resource attributes, e.g.
  ``gaik.run.id=...,gaik.config.blueprint_version=3``.
- ``OTEL_SDK_DISABLED=true`` turns gaik's spans off.

Without an endpoint, gaik's spans go to the application's tracer provider if it
has set one, at any time, and are otherwise dropped at no cost. Without the
extra, every call here is a no-op and gaik behaves as before. A fault in the
instrumentation is logged and never reaches the caller.

If the collector cannot be reached, a short script waits up to the exporter's
timeout (``OTEL_EXPORTER_OTLP_TIMEOUT``, 10 s by default) when it exits, while
the spans still queued are flushed.

The ``gaik.*`` attribute names are a draft until the event schema v1.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from typing import Any

from .pricing import lookup_price
from .usage import UsageRecord

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_tracer: Any = None
_provider: Any = None  # gaik's own provider, when it exports by itself
_resolved = False

#: The request settings a span records, by attribute name; any other key is left out.
_SETTINGS = {
    "temperature": "gen_ai.request.temperature",
    "max_tokens": "gen_ai.request.max_tokens",
    "top_p": "gen_ai.request.top_p",
    "reasoning_effort": "gaik.request.reasoning_effort",
}

#: gaik's provider names mapped to the GenAI convention's well-known values.
_GEN_AI_PROVIDER = {
    "openai": "openai",
    "azure": "azure.ai.openai",
    "anthropic": "anthropic",
    "anthropic_foundry": "anthropic",
    "claude": "anthropic",
    "google": "gcp.gemini",
    "vertex": "gcp.vertex_ai",
}


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
    global _provider
    try:
        from opentelemetry import trace
    except ImportError:
        return None
    if os.getenv("OTEL_SDK_DISABLED", "").strip().lower() == "true":
        return None
    if not (
        os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    ):
        # The API's tracer follows whatever provider the application sets, even
        # later, and records nothing until then.
        return trace.get_tracer("gaik", _gaik_version())
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    # Resource.create() reads OTEL_SERVICE_NAME and OTEL_RESOURCE_ATTRIBUTES, and
    # the exporter its endpoint, itself. The provider flushes on interpreter exit.
    provider = TracerProvider(resource=Resource.create({}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    _provider = provider
    return provider.get_tracer("gaik", _gaik_version())


def config_version(**fields: Any) -> str:
    """A stable id for a configuration: the same fields give the same id.

    The id is the first 16 hex characters of the SHA-256 of the fields as
    canonical JSON (sorted keys). ``None`` values are left out, so adding an
    unset option does not change the id. Values should be JSON types.
    """
    data = {k: v for k, v in fields.items() if v is not None}
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


class LLMCallSpan:
    """Handle for an open ``llm_span``; ``record`` adds the call's result."""

    def __init__(self, span: Any) -> None:
        self._span = span

    @property
    def recording(self) -> bool:
        """Whether the span is kept; skip work that only feeds the span when not."""
        try:
            return self._span is not None and self._span.is_recording()
        except Exception:
            return False

    def record(
        self,
        usage: UsageRecord | None,
        *,
        input_length: int | None = None,
        output_length: int | None = None,
        response_model: str | None = None,
    ) -> None:
        """Add tokens, estimated cost, lengths and the response's model. Never raises."""
        if not self.recording:
            return
        try:
            attributes: dict[str, Any] = {
                "gaik.input.length": input_length,
                "gaik.output.length": output_length,
                "gen_ai.response.model": response_model
                if isinstance(response_model, str)
                else None,
            }
            if usage is not None:
                attributes.update(
                    {
                        "gen_ai.usage.input_tokens": usage.input_tokens,
                        "gen_ai.usage.output_tokens": usage.output_tokens,
                        "gaik.usage.thinking_tokens": usage.thinking_tokens,
                    }
                )
                # A model missing from the price table would read as a free call.
                if lookup_price(usage.provider, usage.model) != (0.0, 0.0):
                    attributes["gaik.cost.usd"] = usage.cost_usd
                    attributes["gaik.cost.estimated"] = True
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
    prompt_version: str | None = None,
) -> Iterator[LLMCallSpan]:
    """Wrap one model call in a ``chat <model>`` span, the current span inside the block.

    ``provider`` is gaik's provider name. ``settings`` are the sampling options
    the request actually sends; only ``temperature``, ``max_tokens``, ``top_p``
    and ``reasoning_effort`` are recorded, and ``None`` values are left out.
    The call's own exception passes through unchanged; the span records only
    its type.
    """
    span = _start(component, provider, model, settings or {}, prompt_version)
    handle = LLMCallSpan(span)
    try:
        with _current(span):
            yield handle
    except BaseException as exc:
        _fail(span, exc)
        raise
    finally:
        _end(span)


def _current(span: Any) -> Any:
    """Make ``span`` the current span, so spans made during the call nest under it."""
    if span is None:
        return nullcontext()
    try:
        from opentelemetry import trace

        # Not use_span's own exception handling: it would record the message.
        return trace.use_span(
            span, end_on_exit=False, record_exception=False, set_status_on_exception=False
        )
    except Exception:
        logger.debug("gaik tracing could not make a span current", exc_info=True)
        return nullcontext()


def _start(
    component: str,
    provider: str,
    model: str,
    settings: dict[str, Any],
    prompt_version: str | None,
) -> Any:
    tracer = _get_tracer()
    if tracer is None:
        return None
    span = None
    try:
        from opentelemetry.trace import SpanKind

        span = tracer.start_span(f"chat {model}", kind=SpanKind.CLIENT)
        if not span.is_recording():
            return span
        settings = {
            k: v
            for k, v in settings.items()
            if k in _SETTINGS and isinstance(v, (bool, int, float, str))
        }
        version = _gaik_version()
        attributes: dict[str, Any] = {
            "gaik.event.class": "llm_call",
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": _GEN_AI_PROVIDER.get(provider, provider),
            "gen_ai.request.model": model,
            "gaik.provider.name": provider,
            "gaik.component.name": component,
            "gaik.component.version": version,
            "gaik.prompt.version": prompt_version,
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
            attributes[_SETTINGS[key]] = value
        span.set_attributes({k: v for k, v in attributes.items() if v is not None})
        return span
    except Exception:
        logger.debug("gaik tracing could not start a span", exc_info=True)
        _end(span)  # a span started before the fault would otherwise stay open
        return None


def _fail(span: Any, exc: BaseException) -> None:
    if span is None:
        return
    try:
        from opentelemetry.trace import Status, StatusCode

        # The type only: an exception's message may quote the prompt or document.
        kind = type(exc)
        span.set_attribute("error.type", f"{kind.__module__}.{kind.__qualname__}")
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
    global _tracer, _provider, _resolved
    with _lock:
        _tracer = None
        _provider = None
        _resolved = False
