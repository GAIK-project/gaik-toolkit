"""OpenTelemetry spans for gaik's LLM calls (gaik.observability.tracing).

Spans are read back through an in-memory exporter. No network: the extractor
test uses a fake client that answers like the OpenAI SDK.
"""

from __future__ import annotations

import sys

import pytest
from gaik.observability import build_usage_record, config_version, llm_span, tracing
from pydantic import BaseModel

trace = pytest.importorskip("opentelemetry.trace")
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)

_EXPORTER = InMemorySpanExporter()


@pytest.fixture
def spans():
    """Spans recorded during the test, through an application-set provider."""
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


def test_without_an_endpoint_or_an_application_provider_nothing_is_set_up(monkeypatch, off):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.setattr(trace, "get_tracer_provider", trace.ProxyTracerProvider)
    assert tracing._resolve_tracer() is None


def test_a_call_becomes_one_span_with_its_usage_and_no_text(spans):
    usage = build_usage_record(
        "openai",
        "gpt-4.1",
        {"input_tokens": 2104, "output_tokens": 423, "thinking_tokens": 0},
        6.1,
    )
    with llm_span(
        "DataExtractor",
        provider="azure",
        model="gpt-4.1",
        settings={"temperature": 0.0, "reasoning_effort": None},
        input_length=len("Salainen dokumentti"),
    ) as call:
        call.record(usage, output_length=len('{"reporter": "Matti"}'))

    (span,) = spans()
    assert span.name == "chat gpt-4.1"
    assert span.kind == trace.SpanKind.CLIENT
    a = span.attributes
    assert a["gaik.event.class"] == "llm_call"
    assert a["gen_ai.operation.name"] == "chat"
    assert a["gen_ai.provider.name"] == "azure"
    assert a["gen_ai.request.model"] == "gpt-4.1"
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
    assert a["gaik.input.length"] > len("Raportoija Matti Virtanen, pumppu P17")
    assert a["gaik.output.length"] == len(_Record(reporter="Matti Virtanen").model_dump_json())
    assert "Matti" not in _values(span)
    assert "P17" not in _values(span)


def test_the_extractor_s_error_is_unchanged_and_marks_the_span(spans):
    extractor = _extractor(_FakeClient(error=ValueError("document text in the message")))

    with pytest.raises(ValueError, match="document text in the message"):
        extractor._extract_one("doc", _Record, _requirements(), "Extract")

    (span,) = spans()
    assert span.status.status_code == trace.StatusCode.ERROR
    assert span.attributes["error.type"] == "ValueError"
    assert "document text" not in _values(span)


class _FakeAdapter:
    """A ProviderClient (non-OpenAI path): returns the parsed model, counts usage itself."""

    provider = "anthropic_foundry"
    model = "claude-test"
    raw = None

    def __init__(self) -> None:
        from gaik.software_components.llm.base import UsageCounter

        self.usage = UsageCounter()

    def chat(self, messages, **kwargs):  # pragma: no cover - not used
        raise NotImplementedError

    def chat_parsed(self, messages, response_format, **kwargs):
        self.usage.add({"prompt_tokens": 210, "completion_tokens": 18})
        return response_format(reporter="Matti Virtanen")

    def chat_stream(self, messages, **kwargs):  # pragma: no cover - not used
        raise NotImplementedError

    def embed(self, texts, **kwargs):  # pragma: no cover - not used
        raise NotImplementedError


def test_an_adapter_call_s_tokens_reach_the_span_and_the_return_value_is_unchanged(spans):
    extractor = _extractor(_FakeAdapter())
    extractor.config = {"provider": "anthropic_foundry", "api_key": "test", "model": "claude-test"}
    extractor.model = "claude-test"

    record, usage = extractor._extract_one("doc", _Record, _requirements(), "Extract")

    assert record["reporter"] == "Matti Virtanen"
    assert usage is None  # as before: the extractor reports usage on the OpenAI path only
    (span,) = spans()
    assert span.attributes["gen_ai.provider.name"] == "anthropic_foundry"
    assert span.attributes["gen_ai.usage.input_tokens"] == 210
    assert span.attributes["gen_ai.usage.output_tokens"] == 18
