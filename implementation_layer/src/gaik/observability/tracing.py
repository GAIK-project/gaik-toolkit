"""OpenTelemetry spans for gaik's LLM calls (optional ``gaik[otel]`` extra).

Each instrumented model call becomes one ``chat <model>`` span (``embeddings
<model>`` for an embedding call) with the OpenTelemetry GenAI names
(``gen_ai.*``) and gaik's own (``gaik.*``): which component made the call, the
provider, model and settings, tokens, an estimated cost and a configuration
version. The settings are the ones the request carries: the code that sends it
reports them with ``record_request``, after the provider's own adjustments (a
temperature a reasoning model drops is left out), and the tokens the response
reports with ``record_response``. Only lengths of the input and output are
recorded, never their text, and an error is recorded by its type, never its
message.

Clients from ``create_llm_client()`` make these spans for every call (see
``gaik.software_components.llm.traced_client``); a component that opens its own
``llm_span`` around a call gets that span alone.

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
import importlib.util
import json
import logging
import os
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from typing import Any

from .pricing import lookup_price
from .usage import UsageRecord, build_usage_record

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_tracer: Any = None
_provider: Any = None  # gaik's own provider, when it exports by itself
_resolved = False
_extra: bool | None = None  # whether the gaik[otel] extra is installed, once known

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


def tracing_enabled() -> bool:
    """Whether the ``gaik[otel]`` extra is installed and gaik's tracing is not off.

    The OpenTelemetry API alone, which other packages bring, is not enough.
    True also when the spans are dropped because nothing collects them (no
    endpoint and no application provider); ``LLMCallSpan.recording`` tells.
    Never raises.
    """
    return _get_tracer() is not None and _extra_installed()


def _extra_installed() -> bool:
    """Whether the OTLP exporter, which only the ``gaik[otel]`` extra brings, is present.

    Looked up once per process: packages do not come and go while it runs, and
    the lookup searches the installed packages, which costs on every model call.
    """
    global _extra
    if _extra is None:
        try:
            spec = importlib.util.find_spec("opentelemetry.exporter.otlp.proto.http")
            _extra = spec is not None
        except (ImportError, ValueError):
            _extra = False
    return _extra


def in_llm_span() -> bool:
    """Whether an ``llm_span`` is open, and not yet ended, in this thread or task."""
    call = _current_call.get()
    return call is not None and not call.ended


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
        self._ended = False
        self._usage: UsageRecord | None = None

    @property
    def ended(self) -> bool:
        """Whether ``end`` has been called."""
        return self._ended

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
        thinking_reported: bool = True,
    ) -> None:
        """Add tokens, estimated cost, lengths and the response's model. Never raises.

        ``thinking_reported=False`` leaves the thinking tokens out rather than
        recording an unknown count as 0.
        """
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
                        "gaik.usage.thinking_tokens": usage.thinking_tokens
                        if thinking_reported
                        else None,
                    }
                )
                # A model missing from the price table would read as a free call.
                if lookup_price(usage.provider, usage.model) != (0.0, 0.0):
                    attributes["gaik.cost.usd"] = usage.cost_usd
                    attributes["gaik.cost.estimated"] = True
            self._span.set_attributes({k: v for k, v in attributes.items() if v is not None})
        except Exception:
            logger.debug("gaik tracing could not record a result", exc_info=True)

    def record_usage(
        self, usage: Mapping[str, Any] | None, *, response_model: str | None = None
    ) -> None:
        """Add the tokens a response reports, in an adapter's usage dict, and its model.

        Takes either key style (``input_tokens``/``output_tokens`` or
        ``prompt_tokens``/``completion_tokens``); the cost is estimated for the
        span's provider and model. Responses within one span add up: a
        component that retries inside its span is billed for every attempt.
        Never raises.
        """
        if not self.recording:
            return
        try:
            counts = _token_counts(usage)
            if counts:
                record = build_usage_record(
                    self._identity.get("provider", ""), self._identity.get("model", ""), counts, 0.0
                )
                self._usage = record if self._usage is None else self._usage + record
            self.record(
                self._usage,
                response_model=response_model,
                thinking_reported=bool(usage) and _reports_thinking(usage),
            )
        except Exception:
            logger.debug("gaik tracing could not record the usage", exc_info=True)

    @contextmanager
    def active(self) -> Iterator[LLMCallSpan]:
        """Make this the current span and call inside the block.

        For a call that runs in pieces, such as a stream read chunk by chunk:
        spans made and settings recorded in the block land here. The block's
        exception passes through unchanged and unrecorded; ``fail`` records it.
        """
        token = _current_call.set(self)
        scope = _current(self._span)
        try:
            scope.__enter__()
        except Exception:
            logger.debug("gaik tracing could not make a span current", exc_info=True)
            scope = None
        try:
            yield self
        except BaseException as exc:
            _leave(scope, exc)
            raise
        else:
            _leave(scope, None)
        finally:
            _current_call.reset(token)

    def fail(self, exc: BaseException) -> None:
        """Mark the span failed with the exception's type, never its message. Never raises."""
        _fail(self._span, exc)

    def end(self) -> None:
        """End the span; a second call does nothing. Never raises."""
        if not self._ended:
            self._ended = True
            _end(self._span)


@contextmanager
def llm_span(
    component: str | None,
    *,
    provider: str,
    model: str,
    prompt_version: str | None = None,
    operation: str = "chat",
) -> Iterator[LLMCallSpan]:
    """Wrap one model call in a ``<operation> <model>`` span, the current span inside the block.

    ``provider`` is gaik's provider name and ``operation`` the GenAI operation,
    ``chat`` or ``embeddings``. The request's settings are added by
    ``record_request``, called where the request is sent. The call's own
    exception passes through unchanged; the span records only its type.
    """
    call = start_llm_span(
        component,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        operation=operation,
    )
    try:
        with call.active():
            yield call
    except BaseException as exc:
        call.fail(exc)
        raise
    finally:
        call.end()


def start_llm_span(
    component: str | None,
    *,
    provider: str,
    model: str,
    prompt_version: str | None = None,
    operation: str = "chat",
) -> LLMCallSpan:
    """Start a span like ``llm_span`` does, for a call that outlives one block.

    The span is not made current: wrap each piece of the call in
    ``LLMCallSpan.active()``, then call ``fail`` on an error and always ``end``.
    ``component`` may be ``None`` when the caller does not know it; the
    attribute is then left out.
    """
    identity = {
        "component": component,
        "version": _gaik_version(),
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
    }
    return LLMCallSpan(_start(identity, operation), identity)


def record_response(usage: Mapping[str, Any] | None, *, response_model: str | None = None) -> None:
    """Record the tokens a model response reports on the open ``llm_span``, if any.

    Call it where the response arrives, with the adapter's usage dict. Outside
    an ``llm_span`` it does nothing, like ``record_request``.
    """
    call = _current_call.get()
    if call is not None:
        call.record_usage(usage, response_model=response_model)


def record_request(settings: Mapping[str, Any]) -> None:
    """Record the settings a model request carries on the open ``llm_span``, if any.

    Call it where the request is sent, with the options as sent, so the span
    shows what the provider received. Outside an ``llm_span`` it does nothing;
    so it does in a thread started inside one, or in a generator consumed after
    the span has closed. The adapters' streaming calls do not record: a stream
    read inside some other call's span would put its settings there.
    """
    call = _current_call.get()
    if call is not None:
        call.record_request(settings)


def _leave(scope: Any, exc: BaseException | None) -> None:
    """Leave a context entered by ``LLMCallSpan.active``; a fault here is only logged."""
    if scope is None:
        return
    try:
        if exc is None:
            scope.__exit__(None, None, None)
        else:
            scope.__exit__(type(exc), exc, exc.__traceback__)
    except BaseException as fault:
        if fault is not exc:
            logger.debug("gaik tracing could not leave a span's context", exc_info=True)


def _reports_thinking(usage: Mapping[str, Any]) -> bool:
    return any(isinstance(usage.get(k), int) for k in ("thinking_tokens", "reasoning_tokens"))


def _token_counts(usage: Mapping[str, Any] | None) -> dict[str, int] | None:
    """The counts ``build_usage_record`` takes, or ``None`` when the response has none."""
    if not usage:
        return None

    def count(*keys: str) -> int:
        for key in keys:
            value = usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
        return 0

    counts = {
        "input_tokens": count("input_tokens", "prompt_tokens"),
        "output_tokens": count("output_tokens", "completion_tokens"),
        "thinking_tokens": count("thinking_tokens", "reasoning_tokens"),
        "total_tokens": count("total_tokens"),
    }
    return counts if counts["input_tokens"] or counts["output_tokens"] else None


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


def _start(identity: dict[str, Any], operation: str = "chat") -> Any:
    tracer = _get_tracer()
    if tracer is None:
        return None
    span = None
    try:
        from opentelemetry.trace import SpanKind

        span = tracer.start_span(f"{operation} {identity['model']}", kind=SpanKind.CLIENT)
        if not span.is_recording():
            return span
        provider = identity["provider"]
        attributes: dict[str, Any] = {
            "gaik.event.class": "llm_call",
            "gen_ai.operation.name": operation,
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
    """Forget the resolved tracer and extra so the next call resolves them again."""
    global _tracer, _provider, _resolved, _extra
    with _lock:
        _tracer = None
        _provider = None
        _resolved = False
        _extra = None
