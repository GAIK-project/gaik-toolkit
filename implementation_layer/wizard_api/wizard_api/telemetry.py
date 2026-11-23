"""OpenTelemetry spans for the WP5 AIOps stack.

The API sends its spans over OTLP/HTTP to the collector named by the standard
``OTEL_EXPORTER_OTLP_ENDPOINT`` or ``OTEL_EXPORTER_OTLP_TRACES_ENDPOINT``
(locally ``http://127.0.0.1:4318``) and nowhere else. Spans carry numbers,
statuses and the session id only: never what the user or the agent wrote, and
never who the user is (no e-mail address, no ``enduser.id``).

Without an endpoint ``setup()`` installs nothing and every span is a no-op, so
tests and deployments that have not been pointed at a collector behave as before.

The ``gaik.*`` attribute names are a draft until the WP5 event schema v1.
"""

import asyncio
import functools
import logging
import os
import re
import time
from collections.abc import AsyncIterator, Callable, Iterable
from typing import Any

from fastapi import HTTPException
from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode

SERVICE_NAME = "wizard-v2-api"

tracer = trace.get_tracer("wizard_api")
logger = logging.getLogger(__name__)

_provider: Any = None

#: Seconds an export may take, so a collector that does not answer cannot hold
#: up the API's shutdown for the exporter's default 10 s. The standard
#: ``OTEL_EXPORTER_OTLP_(TRACES_)TIMEOUT`` overrides it.
EXPORT_TIMEOUT_S = 2


def enabled() -> bool:
    """Whether an OTLP endpoint for traces is configured."""
    return bool(
        os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    )


def setup() -> None:
    """Export spans to the collector when an OTLP endpoint is set. Idempotent."""
    global _provider
    if _provider is not None or not enabled():
        return
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    # The service name picks the MLflow experiment (MLFLOW_EXPERIMENTS in gaik-aiops).
    resource = Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME") or SERVICE_NAME})
    provider = TracerProvider(resource=resource)
    timeout_set = os.getenv("OTEL_EXPORTER_OTLP_TRACES_TIMEOUT") or os.getenv(
        "OTEL_EXPORTER_OTLP_TIMEOUT"
    )
    exporter = OTLPSpanExporter() if timeout_set else OTLPSpanExporter(timeout=EXPORT_TIMEOUT_S)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _provider = provider
    # Metrics go to the same collector when its base or metrics endpoint is set
    # (a traces-only endpoint says nothing about where metrics belong).
    if os.getenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT") or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        from wizard_api import ops_metrics

        ops_metrics.setup(resource)
    if os.getenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT") or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        _setup_logs(resource)


_log_provider: Any = None


_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_ADDRESS = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")


def exportable_record(record: logging.LogRecord) -> logging.LogRecord:
    """A copy of ``record`` fit to leave the pod.

    The collector pseudonymises session ids in attributes, not inside a message,
    so ids (session, run, case: all UUIDs) and any e-mail address in the text are
    replaced. The record keeps its trace id, which leads to the pseudonymised
    session. A traceback stays in the pod's own log: it can hold paths and
    values; the exported record names only the exception type.
    """
    copy = logging.makeLogRecord(record.__dict__)
    text = _ADDRESS.sub("<address>", _UUID.sub("<id>", record.getMessage()))
    if record.exc_info and record.exc_info[0] is not None:
        text = f"{text} ({record.exc_info[0].__name__})"
    copy.msg, copy.args = text, None
    copy.exc_info = copy.exc_text = copy.stack_info = None
    return copy


#: The API's own loggers: ``wizard_api`` and everything under it.
API_LOGGER = "wizard_api"
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def log_level() -> int:
    """``WIZARD_LOG_LEVEL`` as a level (DEBUG, INFO, WARNING, ERROR); INFO unless set."""
    level = logging.getLevelName(os.getenv("WIZARD_LOG_LEVEL", "").strip().upper() or "INFO")
    return level if isinstance(level, int) else logging.INFO


def _let_through(level: int) -> None:
    """Let the API's loggers pass records at ``level`` on to their handlers."""
    tree = logging.getLogger(API_LOGGER)
    if tree.getEffectiveLevel() > level:
        tree.setLevel(level)


def configure_logging(stream: Any = None) -> None:
    """Print the API's own log lines in the pod, from ``WIZARD_LOG_LEVEL``. Idempotent.

    Uvicorn configures its own loggers only, so the API's were left at the root's
    WARNING: an INFO line, such as each tool call the agent's guard decides, was
    dropped before any handler saw it. The ``wizard_api`` loggers get their level
    here and a handler that prints to stderr (``stream`` in tests), unless one
    that writes to a stream is already on them or on the root, which would print
    each line twice.

    Records still go on to the root, where the collector's handler keeps its own
    level (``WIZARD_OTEL_LOG_LEVEL``, WARNING unless set): an INFO line reaches the
    collector only when that asks for it, and once.
    """
    level = log_level()
    tree = logging.getLogger(API_LOGGER)
    tree.setLevel(level)
    if any(
        isinstance(h, logging.StreamHandler) for h in tree.handlers + logging.getLogger().handlers
    ):
        return
    handler = logging.StreamHandler(stream)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    tree.addHandler(handler)


class _NotOwnExporter(logging.Filter):
    """Keep the exporter's own complaints out of the records it exports."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.name.startswith(("opentelemetry", "urllib3"))


def _setup_logs(resource: Any) -> None:
    """Send log records at ``WIZARD_OTEL_LOG_LEVEL`` (WARNING unless set) and above.

    The pod's own output is not collected in a shared project, so the API sends
    its records to the collector itself; the collector's privacy step runs on
    them before they are stored.
    """
    global _log_provider
    if _log_provider is not None:
        return
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

    level = getattr(logging, os.getenv("WIZARD_OTEL_LOG_LEVEL", "WARNING").upper(), logging.WARNING)
    provider = LoggerProvider(resource=resource)
    timeout_set = os.getenv("OTEL_EXPORTER_OTLP_LOGS_TIMEOUT") or os.getenv(
        "OTEL_EXPORTER_OTLP_TIMEOUT"
    )
    exporter = OTLPLogExporter() if timeout_set else OTLPLogExporter(timeout=EXPORT_TIMEOUT_S)
    provider.add_log_record_processor(BatchLogRecordProcessor(exporter))

    class _ExportHandler(LoggingHandler):
        def emit(self, record: logging.LogRecord) -> None:
            super().emit(exportable_record(record))

    handler = _ExportHandler(level=level, logger_provider=provider)
    handler.addFilter(_NotOwnExporter())
    logging.getLogger().addHandler(handler)
    # WIZARD_OTEL_LOG_LEVEL=INFO must reach the API's INFO lines even where the
    # pod prints only warnings; the pod's handler keeps WIZARD_LOG_LEVEL.
    _let_through(level)
    _log_provider = provider


def shutdown() -> None:
    """Flush the spans and metrics still queued; called when the app stops."""
    from wizard_api import ops_metrics

    ops_metrics.shutdown()
    if _log_provider is not None:
        _log_provider.shutdown()
    if _provider is not None:
        _provider.shutdown()


def refusal(exc: Any) -> str:
    """The short reason an HTTPException gives (``gate_not_ready``, ``agent_busy`` …)."""
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict) and detail.get("error"):
        return str(detail["error"])
    return str(getattr(exc, "status_code", "error"))


def record_failure(span: Span, exc: BaseException) -> None:
    """Mark ``span`` failed by an exception the API did not expect (not a refusal).

    Only the exception's type goes on the span: its message can quote data.
    """
    span.set_attribute("error.type", type(exc).__qualname__)
    span.set_status(Status(StatusCode.ERROR, type(exc).__qualname__))


def record_refusal(span: Span, attribute: str, exc: HTTPException) -> None:
    """Put the reason an HTTPException gives on ``span``.

    A 4xx is an answer (the request may not be done now), so the span keeps its
    status. A 5xx is the API failing to do it, so the span is an error too.
    """
    reason = refusal(exc)
    span.set_attribute(attribute, reason)
    if getattr(exc, "status_code", 500) >= 500:
        span.set_attribute("error.type", reason)
        span.set_status(Status(StatusCode.ERROR, reason))


def name_session(session_id: Any) -> None:
    """Put the session's id on the request's span, so the collector files the
    request under that session (MLflow groups traces by it). The id is
    pseudonymised in the collector like every ``gaik.session.id``. Without a
    recording span this does nothing."""
    trace.get_current_span().set_attribute("gaik.session.id", str(session_id))


def sandbox_start_span(kind: str):
    """Wrap a run-starting endpoint in a ``wizard.sandbox.start`` span.

    The run itself is a Job that goes on after the request returns; its
    outcome is the ``wizard.sandbox.result`` span, matched by ``run_id``.
    """

    def wrap(endpoint):
        @functools.wraps(endpoint)
        def traced(*args, **kwargs):
            # A refused start is an answer, not a failure of the API: no error status.
            with tracer.start_as_current_span(
                "wizard.sandbox.start", record_exception=False, set_status_on_exception=False
            ) as span:
                span.set_attributes(
                    {"gaik.session.id": str(kwargs.get("session_id")), "gaik.sandbox.kind": kind}
                )
                try:
                    started = endpoint(*args, **kwargs)
                except HTTPException as exc:
                    record_refusal(span, "gaik.sandbox.refused", exc)
                    raise
                except Exception as exc:
                    record_failure(span, exc)
                    raise
                if isinstance(started, dict) and started.get("run_id"):
                    span.set_attribute("gaik.sandbox.run_id", started["run_id"])
                return started

        return traced

    return wrap


def query_cost(agent: dict, result: Any) -> float | None:
    """What this one query cost, in USD.

    The SDK's ``total_cost_usd`` is a running total for the agent's client, not
    the price of the last query: each query's cost is the difference from the
    previous total, which is kept on the agent. A new client starts from zero.
    """
    total = getattr(result, "total_cost_usd", None)
    if total is None:
        return None
    before = agent.get("cost_total_usd", 0.0)
    agent["cost_total_usd"] = total
    return total - before if total >= before else total


#: What a query that ended with no result (a timeout, a crashed or killed
#: agent) is charged for the usage caps, in USD, when its agent's own budget
#: does not leave less: its real cost never arrives. About one long reply.
UNREPORTED_QUERY_COST_USD = 1.0


def unreported_query_cost(agent: dict) -> float:
    """The estimate charged for ``agent``'s query that ended with no result."""
    from wizard_api import ops_metrics

    estimate = UNREPORTED_QUERY_COST_USD
    budget = agent.get("budget_usd")
    if budget is not None:
        estimate = max(0.0, min(estimate, budget - agent.get("cost_total_usd", 0.0)))
    logger.warning("a query ended with no result; %.2f USD is counted for it", estimate)
    ops_metrics.usage_unreported.add(1)
    return estimate


def _response_model(result: Any) -> str | None:
    """The model that did most of the query's work, from the SDK's per-model usage."""
    per_model = getattr(result, "model_usage", None) or {}
    if not per_model:
        return None
    return max(per_model, key=lambda name: (per_model[name] or {}).get("outputTokens") or 0)


def record_turn_usage(
    turn: Span,
    result: Any,
    model: str,
    purpose: str = "turn",
    cost: float | None = None,
    *,
    replaced: bool = False,
) -> None:
    """Add one ``chat <model>`` span under ``turn`` from the agent SDK's ResultMessage.

    The SDK runs several model calls inside one query and reports only their
    totals, so this span stands for all of them; ``gaik.agent.num_turns`` says
    how many there were. ``model`` is the model the API asked for; the model
    that answered, from the SDK's per-model usage, is ``gen_ai.response.model``.
    ``cost`` is the query's own price in USD (see ``query_cost``). ``purpose``
    tells the user's message (``turn``) from the agent's bootstrap (``setup``)
    and a reply-language change (``language``), which cost tokens too.

    ``gen_ai.usage.input_tokens`` counts every input token, as the OTel GenAI
    convention asks: Anthropic's ``input_tokens`` leaves out the tokens read
    from or written to the prompt cache, which are added here and also kept
    on their own attributes.

    ``replaced`` marks a failed query whose message was answered by a retry on a
    new agent: it is recorded, with ``gaik.agent.replaced``, but not as an error.
    """
    end = time.time_ns()
    start = end - int((getattr(result, "duration_ms", 0) or 0) * 1_000_000)
    span = tracer.start_span(
        f"chat {model}", context=trace.set_span_in_context(turn), start_time=start
    )
    usage = getattr(result, "usage", None) or {}
    uncached = usage.get("input_tokens")
    cache_read = usage.get("cache_read_input_tokens")
    cache_creation = usage.get("cache_creation_input_tokens")
    parts = [n for n in (uncached, cache_read, cache_creation) if n is not None]
    attributes = {
        "gaik.event.class": "llm_call",
        "gen_ai.operation.name": "chat",
        "gen_ai.system": "anthropic",
        "gen_ai.request.model": model,
        "gen_ai.response.model": _response_model(result),
        "gen_ai.usage.input_tokens": sum(parts) if parts else None,
        "gen_ai.usage.output_tokens": usage.get("output_tokens"),
        "gen_ai.usage.cache_read.input_tokens": cache_read,
        "gen_ai.usage.cache_creation.input_tokens": cache_creation,
        "gaik.cost.usd": cost,
        "gaik.agent.num_turns": getattr(result, "num_turns", None),
        "gaik.agent.purpose": purpose,
    }
    span.set_attributes({k: v for k, v in attributes.items() if v is not None})
    if getattr(result, "terminal_reason", None) in ("aborted_streaming", "aborted_tools"):
        # The user stopped the reply: the query ended early, as asked.
        span.set_attribute("gaik.agent.stopped", True)
    elif getattr(result, "is_error", False):
        if replaced:
            span.set_attribute("gaik.agent.replaced", True)
        else:
            span.set_status(Status(StatusCode.ERROR, getattr(result, "subtype", None)))
    span.end(end_time=end)


async def traced_turn(
    frames: AsyncIterator[str],
    attributes: dict,
    agents: Callable[[], Iterable[tuple[dict, bool]]],
    model: str,
    is_error: Callable[[str], bool],
    is_stopped: Callable[[str], bool] | None = None,
    on_cost: Callable[[float], None] | None = None,
) -> AsyncIterator[str]:
    """Pass a chat turn's SSE ``frames`` through, inside one ``wizard.turn`` span.

    When the stream ends, each query the agents ran for it (``turn_results`` on
    the agent: the message itself, and a setup or language change before it)
    becomes a ``chat`` span under the turn. ``agents()`` gives the agents to read,
    at the end of the stream, each with whether a retry replaced it. The turn
    is an error when a frame the user saw was an error. A turn the client left
    before it ended (closed tab, dropped connection) is ``gaik.turn.aborted``;
    the query it cut short has no ``chat`` span, as its usage never arrived. A
    turn the user stopped (a frame ``is_stopped`` knows) is ``gaik.turn.stopped``
    and counted with the outcome ``stopped``, not as a failure. ``on_cost`` is
    given the turn's whole cost in USD, when the queries reported one, for the
    usage caps (services/usage_caps.py).
    """
    from wizard_api import ops_metrics

    turn = tracer.start_span("wizard.turn")
    turn.set_attributes(attributes)
    failed = False
    stopped = False
    outcome = "completed"
    started = time.monotonic()
    first = True
    try:
        async for frame in frames:
            if first:
                ops_metrics.turn_first_frame.record(time.monotonic() - started)
                first = False
            failed = failed or is_error(frame)
            stopped = stopped or (is_stopped is not None and is_stopped(frame))
            yield frame
    except (asyncio.CancelledError, GeneratorExit):
        turn.set_attribute("gaik.turn.aborted", True)
        outcome = "aborted"
        raise
    except Exception as exc:
        record_failure(turn, exc)
        outcome = "failed"
        raise
    finally:
        if outcome == "completed" and failed:
            outcome = "failed"
        elif outcome == "completed" and stopped:
            outcome = "stopped"
            turn.set_attribute("gaik.turn.stopped", True)
        ops_metrics.turns.add(1, {"outcome": outcome})
        if outcome != "aborted":
            ops_metrics.turn_duration.record(time.monotonic() - started, {"outcome": outcome})
        # Each client keeps its own running cost, so each is priced against its own.
        spent = 0.0
        for agent, replaced in agents():
            for purpose, result in agent.pop("turn_results", None) or []:
                cost = query_cost(agent, result)
                record_turn_usage(turn, result, model, purpose, cost=cost, replaced=replaced)
                spent += cost or 0.0
            if agent.pop("query_unfinished", False):
                spent += unreported_query_cost(agent)
        if on_cost is not None and spent > 0:
            on_cost(spent)
        if failed:
            turn.set_status(Status(StatusCode.ERROR))
        turn.end()
