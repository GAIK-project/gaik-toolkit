"""OpenTelemetry spans for gaik's LLM calls (optional ``gaik[otel]`` extra).

Each instrumented model call becomes one ``chat <model>`` span with the
OpenTelemetry GenAI names (``gen_ai.*``) and gaik's own (``gaik.*``): which
component made the call, the provider, model and settings, tokens, an estimated
cost and a configuration version. The settings are the ones the request carries:
the code that sends it reports them with ``record_request``, after the
provider's own adjustments (a temperature a reasoning model drops is left out).
Only lengths of the input and output are recorded, never their text, and an
error is recorded by its type, never its message.

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
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from typing import Any

from .pricing import lookup_price
from .usage import UsageRecord

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_tracer: Any = None
_provider: Any = None  # gaik's own provider, when it exports by itself
_resolved = False

#: The request settings a span records, by attribute name; any other key is left out.
#: Providers name the token limit differently; all three are the same setting.
_SETTINGS = {
    "temperature": "gen_ai.request.temperature",
    "top_p": "gen_ai.request.top_p",
    "top_k": "gen_ai.request.top_k",
    "max_tokens": "gen_ai.request.max_tokens",
    "max_completion_tokens": "gen_ai.request.max_tokens",
    "max_output_tokens": "gen_ai.request.max_tokens",
    "reasoning_effort": "gaik.request.reasoning_effort",
}

#: The open ``llm_span`` of this thread or task, for ``record_request``.
_current_call: ContextVar[LLMCallSpan | None] = ContextVar("gaik_llm_call", default=None)

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
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        # The API alone comes with other packages (chromadb, for one); the
        # exporter only with the extra. Say why no spans arrive.
        logger.warning(
            "An OTLP endpoint is set but the OTLP exporter is not installed, so gaik "
            "sends no spans. Install gaik[otel]."
        )
        return None

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

    def __init__(self, span: Any, identity: dict[str, Any] | None = None) -> None:
        self._span = span
        self._identity = identity or {}

    @property
    def recording(self) -> bool:
        """Whether the span is kept; skip work that only feeds the span when not."""
        try:
            return self._span is not None and self._span.is_recording()
        except Exception:
            return False

    def record_request(self, settings: Mapping[str, Any]) -> None:
        """Add the settings the request carries, and the config version they give.

        Only the known sampling options are kept (see ``_SETTINGS``); ``None``
        values are left out. Never raises.
        """
        if not self.recording:
            return
        try:
            kept = _known_settings(settings)
            attributes: dict[str, Any] = {_SETTINGS[k]: v for k, v in kept.items()}
            attributes["gaik.config.version"] = config_version(**self._identity, settings=kept)
            self._span.set_attributes(attributes)
        except Exception:
            logger.debug("gaik tracing could not record the request", exc_info=True)

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
    prompt_version: str | None = None,
) -> Iterator[LLMCallSpan]:
    """Wrap one model call in a ``chat <model>`` span, the current span inside the block.

    ``provider`` is gaik's provider name. The request's settings are added by
    ``record_request``, called where the request is sent. The call's own
    exception passes through unchanged; the span records only its type.
    """
    identity = {
        "component": component,
        "version": _gaik_version(),
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
    }
    span = _start(identity)
    handle = LLMCallSpan(span, identity)
    token = _current_call.set(handle)
    try:
        with _current(span):
            yield handle
    except BaseException as exc:
        _fail(span, exc)
        raise
    finally:
        _current_call.reset(token)
        _end(span)


def record_request(settings: Mapping[str, Any]) -> None:
    """Record the settings a model request carries on the open ``llm_span``, if any.

    Call it where the request is sent, with the options as sent, so the span
    shows what the provider received. Outside an ``llm_span`` it does nothing;
    so it does in a thread started inside one, or in a generator consumed after
    the span has closed, which is why the adapters' streaming calls do not
    record (no component streams inside a span).
    """
    call = _current_call.get()
    if call is not None:
        call.record_request(settings)


def _known_settings(settings: Mapping[str, Any]) -> dict[str, Any]:
    return {
        k: v
        for k, v in settings.items()
        if k in _SETTINGS and isinstance(v, (bool, int, float, str))
    }


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


def _start(identity: dict[str, Any]) -> Any:
    tracer = _get_tracer()
    if tracer is None:
        return None
    span = None
    try:
        from opentelemetry.trace import SpanKind

        span = tracer.start_span(f"chat {identity['model']}", kind=SpanKind.CLIENT)
        if not span.is_recording():
            return span
        provider = identity["provider"]
        attributes: dict[str, Any] = {
            "gaik.event.class": "llm_call",
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": _GEN_AI_PROVIDER.get(provider, provider),
            "gen_ai.request.model": identity["model"],
            "gaik.provider.name": provider,
            "gaik.component.name": identity["component"],
            "gaik.component.version": identity["version"],
            "gaik.prompt.version": identity["prompt_version"],
            # Replaced by record_request with the request's settings included.
            "gaik.config.version": config_version(**identity),
        }
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
