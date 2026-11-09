"""OpenTelemetry spans for gaik's LLM calls (gaik.observability.tracing).

Spans are read back through an in-memory exporter. No network: the extractor
test uses a fake client that answers like the OpenAI SDK.
"""

from __future__ import annotations

import sys

import pytest
from gaik.observability import build_usage_record, config_version, llm_span, tracing
from pydantic import BaseModel

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    _EXPORTER = InMemorySpanExporter()
except ImportError:  # the extra is not installed: only the no-extra test runs
    trace = None

needs_otel = pytest.mark.skipif(trace is None, reason="needs the gaik[otel] extra")


@pytest.fixture
def spans(monkeypatch):
    """Spans recorded during the test, through an application-set provider."""
    if trace is None:
        pytest.skip("needs the gaik[otel] extra")
    # A developer's own OTEL_* settings would send gaik's spans elsewhere.
    for name in (
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_SDK_DISABLED",
    ):
        monkeypatch.delenv(name, raising=False)
    if not isinstance(trace.get_tracer_provider(), TracerProvider):
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(_EXPORTER))
        trace.set_tracer_provider(provider)
    tracing._reset_for_tests()
    _EXPORTER.clear()
    yield _EXPORTER.get_finished_spans
    _EXPORTER.clear()
    tracing._reset_for_tests()


@pytest.fixture
def off():
    """Tracing resolved again from scratch, and forgotten after the test."""
    tracing._reset_for_tests()
    yield
    tracing._reset_for_tests()


def _values(span) -> str:
    return " ".join(str(v) for v in span.attributes.values())


def test_without_the_extra_a_call_runs_as_before(monkeypatch, off):
    monkeypatch.setitem(sys.modules, "opentelemetry", None)
    with llm_span("DataExtractor", provider="openai", model="m") as call:
        call.record(None, output_length=3)
        result = "done"
    assert result == "done"
    assert tracing._get_tracer() is None


@needs_otel
def test_without_an_endpoint_gaik_follows_the_application_s_provider(monkeypatch, off):
    # The API's tracer, not a decision made once: it follows a provider the
    # application sets later, and records nothing until then.
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    sentinel = object()
    monkeypatch.setattr(trace, "get_tracer", lambda *args, **kwargs: sentinel)
    assert tracing._resolve_tracer() is sentinel


@needs_otel
def test_with_an_endpoint_gaik_exports_by_itself_and_leaves_the_global_provider_alone(
    monkeypatch, off
):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:9")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "gaik-test")
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "gaik.run.id=run-1")
    before = trace.get_tracer_provider()

    tracer = tracing._resolve_tracer()

    assert tracer is not None
    assert trace.get_tracer_provider() is before
    resource = tracing._provider.resource.attributes
    assert resource["service.name"] == "gaik-test"
    assert resource["gaik.run.id"] == "run-1"
    tracing._provider.shutdown()


@needs_otel
def test_otel_sdk_disabled_turns_gaik_s_spans_off(monkeypatch, off):
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:9")
    assert tracing._resolve_tracer() is None


@needs_otel
def test_without_a_recording_tracer_the_call_skips_the_span_s_work(monkeypatch, off):
    monkeypatch.setattr(tracing, "_get_tracer", lambda: trace.NoOpTracer())
    with llm_span("DataExtractor", provider="openai", model="m") as call:
        assert call.recording is False
        call.record(None, output_length=1)


def test_a_call_becomes_one_span_with_its_usage_and_no_text(spans):
    usage = build_usage_record(
        "openai",
        "gpt-6-luna",
        {"input_tokens": 2104, "output_tokens": 423, "thinking_tokens": 0},
        6.1,
    )
    with llm_span(
        "DataExtractor",
        provider="azure",
        model="gpt-6-luna",
        settings={"temperature": 0.0, "reasoning_effort": None},
        prompt_version="p1",
    ) as call:
        call.record(
            usage,
            input_length=len("Salainen dokumentti"),
            output_length=len('{"reporter": "Matti"}'),
            response_model="gpt-6-luna-2026-05-01",
        )

    (span,) = spans()
    assert span.name == "chat gpt-6-luna"
    assert span.kind == trace.SpanKind.CLIENT
    a = span.attributes
    assert a["gaik.event.class"] == "llm_call"
    assert a["gen_ai.operation.name"] == "chat"
    assert a["gen_ai.provider.name"] == "azure.ai.openai"
    assert a["gaik.provider.name"] == "azure"
    assert a["gen_ai.request.model"] == "gpt-6-luna"
    assert a["gen_ai.response.model"] == "gpt-6-luna-2026-05-01"
    assert a["gaik.prompt.version"] == "p1"
    assert a["gen_ai.request.temperature"] == 0.0
    assert "gaik.request.reasoning_effort" not in a
    assert a["gen_ai.usage.input_tokens"] == 2104
    assert a["gen_ai.usage.output_tokens"] == 423
    assert a["gaik.cost.usd"] == usage.cost_usd
    assert a["gaik.cost.estimated"] is True
    assert a["gaik.component.name"] == "DataExtractor"
    assert a["gaik.input.length"] == 19
    assert a["gaik.output.length"] == 21
    assert len(a["gaik.config.version"]) == 16
    assert "Salainen" not in _values(span)
    assert "Matti" not in _values(span)


def test_a_model_without_a_known_price_gets_no_cost(spans):
    usage = build_usage_record(
        "openai", "custom-model", {"input_tokens": 10, "output_tokens": 5}, 1
    )
    with llm_span("DataExtractor", provider="openai", model="custom-model") as call:
        call.record(usage)
    (span,) = spans()
    assert span.attributes["gen_ai.usage.input_tokens"] == 10
    assert "gaik.cost.usd" not in span.attributes


def test_spans_made_during_the_call_nest_under_it(spans):
    tracer = trace.get_tracer("test")
    with llm_span("DataExtractor", provider="openai", model="m"):
        with tracer.start_as_current_span("http POST"):
            pass
    by_name = {s.name: s for s in spans()}
    http, llm = by_name["http POST"], by_name["chat m"]
    assert http.parent.span_id == llm.context.span_id


def test_the_call_s_error_passes_through_and_the_span_keeps_only_its_type(spans):
    class _QuotaError(RuntimeError):
        pass

    with pytest.raises(_QuotaError, match="secret prompt text"):
        with llm_span("DataExtractor", provider="openai", model="m"):
            raise _QuotaError("secret prompt text")

    (span,) = spans()
    assert span.status.status_code == trace.StatusCode.ERROR
    assert span.status.description is None
    assert span.attributes["error.type"].endswith("_QuotaError")
    assert "secret" not in _values(span)
    assert not span.events  # no recorded exception, so no message or traceback


def test_a_fault_in_the_instrumentation_never_reaches_the_caller(spans, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("exporter down")

    monkeypatch.setattr(tracing, "config_version", broken)
    with llm_span("DataExtractor", provider="openai", model="m") as call:
        call.record(None, output_length=1)
        result = "done"
    assert result == "done"


def test_only_known_settings_are_recorded(spans):
    with llm_span(
        "DataExtractor",
        provider="openai",
        model="m",
        settings={"top_p": 1.0, "reasoning_effort": "low", "api_key": "sk-x", "stop": ["a"]},
    ):
        pass
    (span,) = spans()
    assert span.attributes["gen_ai.request.top_p"] == 1.0
    assert span.attributes["gaik.request.reasoning_effort"] == "low"
    assert not any("api_key" in k or "stop" in k for k in span.attributes)
    assert "sk-x" not in _values(span)


def test_a_span_started_before_a_fault_is_still_ended(spans, monkeypatch):
    ended = []

    class _Span:
        def is_recording(self):
            return True

        def set_attributes(self, attributes):
            raise RuntimeError("bad attribute")

        def end(self):
            ended.append(True)

    class _Tracer:
        def start_span(self, *args, **kwargs):
            return _Span()

    monkeypatch.setattr(tracing, "_get_tracer", lambda: _Tracer())
    with llm_span("DataExtractor", provider="openai", model="m") as call:
        assert call.recording is False
    assert ended == [True]


def test_the_config_version_is_stable_and_follows_the_settings():
    base = {"component": "DataExtractor", "provider": "azure", "model": "gpt-4.1"}
    first = config_version(**base, settings={"temperature": 0.0})
    assert first == config_version(**base, settings={"temperature": 0.0})
    assert first == config_version(**base, settings={"temperature": 0.0}, prompt_version=None)
    assert first != config_version(**base, settings={"temperature": 0.2})
    assert first != config_version(
        **{**base, "model": "gpt-4.1-mini"}, settings={"temperature": 0.0}
    )


class _Record(BaseModel):
    reporter: str


class _FakeClient:
    """Answers ``beta.chat.completions.parse`` like the OpenAI SDK, with usage."""

    def __init__(self, error: Exception | None = None) -> None:
        error_to_raise = error

        class _Completions:
            def parse(self, **kwargs):
                if error_to_raise is not None:
                    raise error_to_raise
                message = type("M", (), {"parsed": _Record(reporter="Matti Virtanen")})()
                choice = type("C", (), {"message": message})()
                usage = type(
                    "U", (), {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}
                )()
                return type("R", (), {"choices": [choice], "usage": usage})()

        self.beta = type(
            "Beta", (), {"chat": type("Chat", (), {"completions": _Completions()})()}
        )()


def _extractor(client):
    from gaik.software_components.extractor.extractor import DataExtractor

    extractor = DataExtractor({"use_azure": False, "api_key": "test", "model": "gpt-4.1"})
    extractor.client = client
    return extractor


def _requirements():
    from gaik.software_components.extractor.schema import ExtractionRequirements

    return ExtractionRequirements(use_case_name="ticket", fields=[])


def test_the_extractor_s_call_is_one_span_without_the_document_or_the_record(spans):
    extractor = _extractor(_FakeClient())

    record, usage = extractor._extract_one(
        "Raportoija Matti Virtanen, pumppu P17", _Record, _requirements(), "Extract the reporter"
    )

    assert record["reporter"] == "Matti Virtanen"
    (span,) = spans()
    a = span.attributes
    assert a["gaik.component.name"] == "DataExtractor"
    assert a["gen_ai.provider.name"] == "openai"
    assert a["gen_ai.request.model"] == "gpt-4.1"
    assert a["gen_ai.usage.input_tokens"] == 120 == usage.input_tokens
    assert a["gen_ai.usage.output_tokens"] == 30
    assert a["gen_ai.request.temperature"] == 0.0
    assert a["gen_ai.request.top_p"] == 1.0  # sent by _parse_with, not an argument
    assert a["gaik.input.length"] > len("Raportoija Matti Virtanen, pumppu P17")
    assert a["gaik.output.length"] == len(_Record(reporter="Matti Virtanen").model_dump_json())
    assert "Matti" not in _values(span)
    assert "P17" not in _values(span)


def test_the_extractor_records_the_settings_it_sends_not_its_arguments(spans):
    from gaik.software_components.extractor.extractor import DataExtractor

    extractor = DataExtractor(
        {"use_azure": False, "api_key": "test", "model": "gpt-6-luna", "reasoning_effort": "high"}
    )
    extractor.client = _FakeClient()

    extractor._extract_one("doc", _Record, _requirements(), "Extract")

    (span,) = spans()
    # GPT-6 with reasoning on: temperature and top_p are dropped from the request,
    # and the effort comes from the config.
    assert "gen_ai.request.temperature" not in span.attributes
    assert "gen_ai.request.top_p" not in span.attributes
    assert span.attributes["gaik.request.reasoning_effort"] == "high"


def test_the_extractor_s_error_is_unchanged_and_marks_the_span(spans):
    extractor = _extractor(_FakeClient(error=ValueError("document text in the message")))

    with pytest.raises(ValueError, match="document text in the message"):
        extractor._extract_one("doc", _Record, _requirements(), "Extract")

    (span,) = spans()
    assert span.status.status_code == trace.StatusCode.ERROR
    assert span.attributes["error.type"] == "builtins.ValueError"
    assert "document text" not in _values(span)
