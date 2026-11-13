"""OpenTelemetry spans for components that call a model SDK directly.

Components build their own OpenAI, Azure, Anthropic or Google request; each
such call gets one ``llm_call`` span named after the component, with the
tokens the SDK response reports (``sdk_usage``) and lengths, never text.
The SDK clients are fakes that answer like the SDK. No network.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from gaik.observability import sdk_usage, text_length, tracing
from gaik.observability.tracing import llm_span, provider_of, record_response

from . import test_observability_llm_client as client_tests
from . import test_observability_tracing as tracing_tests

spans, off = tracing_tests.spans, tracing_tests.off
SECRET, ANSWER, _assert_clean = client_tests.SECRET, client_tests.ANSWER, client_tests._assert_clean
OPENAI = {"provider": "openai", "api_key": "test-key", "model": "gpt-4.1"}


# -- sdk_usage ----------------------------------------------------------------


def _ns(**kwargs):
    return SimpleNamespace(**kwargs)


def test_chat_completions_usage_reads_reasoning_and_cached_tokens():
    usage = _ns(
        prompt_tokens=1000,
        completion_tokens=300,
        prompt_tokens_details=_ns(cached_tokens=800),
        completion_tokens_details=_ns(reasoning_tokens=200),
    )
    assert sdk_usage(_ns(usage=usage)) == {
        "input_tokens": 1000,  # cached input is part of prompt_tokens
        "output_tokens": 300,
        "thinking_tokens": 200,
        "cache_read_input_tokens": 800,
    }


def test_responses_api_usage_reads_reasoning_and_cached_tokens():
    usage = _ns(
        input_tokens=500,
        output_tokens=90,
        input_tokens_details=_ns(cached_tokens=100),
        output_tokens_details=_ns(reasoning_tokens=40),
    )
    assert sdk_usage(_ns(usage=usage)) == {
        "input_tokens": 500,
        "output_tokens": 90,
        "thinking_tokens": 40,
        "cache_read_input_tokens": 100,
    }


def test_anthropic_usage_counts_cache_reads_and_writes_as_input():
    usage = _ns(
        input_tokens=50,
        output_tokens=20,
        cache_read_input_tokens=900,
        cache_creation_input_tokens=30,
    )
    assert sdk_usage(_ns(usage=usage)) == {
        "input_tokens": 980,
        "output_tokens": 20,
        "cache_read_input_tokens": 900,
        "cache_creation_input_tokens": 30,
    }


def test_litellm_usage_with_anthropic_cache_fields():
    usage = _ns(prompt_tokens=400, completion_tokens=10, cache_read_input_tokens=300)
    assert sdk_usage(_ns(usage=usage))["cache_read_input_tokens"] == 300


def test_gemini_usage_from_the_sdk_and_from_rest():
    meta = _ns(
        prompt_token_count=120,
        candidates_token_count=30,
        thoughts_token_count=50,
        cached_content_token_count=60,
    )
    expected = {
        "input_tokens": 120,
        "output_tokens": 80,  # thinking is billed as output
        "thinking_tokens": 50,
        "cache_read_input_tokens": 60,
    }
    assert sdk_usage(_ns(usage_metadata=meta)) == expected
    rest = {
        "usageMetadata": {
            "promptTokenCount": 120,
            "candidatesTokenCount": 30,
            "thoughtsTokenCount": 50,
            "cachedContentTokenCount": 60,
        }
    }
    assert sdk_usage(rest) == expected


def test_embedding_and_transcription_usage():
    assert sdk_usage(_ns(usage=_ns(prompt_tokens=12, total_tokens=12))) == {
        "input_tokens": 12,
        "output_tokens": 0,
    }
    transcription = _ns(usage=_ns(type="tokens", input_tokens=70, output_tokens=15))
    assert sdk_usage(transcription) == {"input_tokens": 70, "output_tokens": 15}


@pytest.mark.parametrize(
    "response",
    [None, "text", {}, _ns(usage=None), _ns(usage=_ns(type="duration", seconds=3.0)), MagicMock()],
)
def test_responses_without_token_counts_give_nothing(response):
    assert sdk_usage(response) == {}


def test_text_length_counts_text_parts_only():
    messages = [
        {"role": "system", "content": "abc"},
        {"role": "user", "content": [{"type": "text", "text": "de"}, {"type": "image_url"}]},
    ]
    assert text_length(messages) == 5
    assert text_length(["abc", [{"type": "input_text", "text": "de"}]]) == 5
    assert text_length(None) is None
    assert text_length([object()]) is None


def test_provider_of_names_sdk_clients():
    class AzureOpenAI: ...

    class AnthropicFoundry: ...

    class OpenAI: ...

    assert provider_of(AzureOpenAI()) == "azure"
    assert provider_of(AnthropicFoundry()) == "anthropic"
    assert provider_of(OpenAI()) == "openai"
    assert provider_of(SimpleNamespace(provider="google")) == "google"


# -- the span's tokens (issue #122) -------------------------------------------


def test_reasoning_and_cached_tokens_reach_the_span(spans):
    usage = _ns(
        prompt_tokens=1000,
        completion_tokens=300,
        prompt_tokens_details=_ns(cached_tokens=800),
        completion_tokens_details=_ns(reasoning_tokens=200),
    )
    with llm_span("DocumentClassifier", provider="openai", model="gpt-4.1"):
        record_response(_ns(usage=usage, model="gpt-4.1-2025-04-14"))

    (span,) = spans()
    assert span.attributes["gaik.usage.thinking_tokens"] == 200
    assert span.attributes["gen_ai.usage.cache_read.input_tokens"] == 800
    assert span.attributes["gen_ai.response.model"] == "gpt-4.1-2025-04-14"


def test_claude_cached_input_counts_in_input_and_cost(spans):
    usage = _ns(input_tokens=50, output_tokens=20, cache_read_input_tokens=900)
    with llm_span("VisionExtractor", provider="anthropic", model="claude-sonnet-4-5"):
        record_response(_ns(usage=usage))
        record_response(_ns(usage=usage))  # a retry inside the span adds up

    (span,) = spans()
    assert span.attributes["gen_ai.usage.input_tokens"] == 1900
    assert span.attributes["gen_ai.usage.cache_read.input_tokens"] == 1800
    assert span.attributes["gaik.cost.usd"] > 0


# -- components -----------------------------------------------------------------


def _completion(content=ANSWER, parsed=None):
    message = SimpleNamespace(content=content, parsed=parsed)
    usage = _ns(prompt_tokens=100, completion_tokens=20, completion_tokens_details=None)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)], usage=usage, model="gpt-4.1-2025-04-14"
    )


class _RawOpenAI:
    """Stands in for ``OpenAI``: chat completions, parse and embeddings."""

    def __init__(self, response=None, error=None, stream=None):
        self.calls: list[dict] = []

        def create(**kwargs):
            self.calls.append(kwargs)
            if error is not None:
                raise error
            if kwargs.get("stream"):
                return iter(stream or [])
            return response

        def embed(**kwargs):
            self.calls.append(kwargs)
            data = [
                SimpleNamespace(index=i, embedding=[0.1]) for i, _ in enumerate(kwargs["input"])
            ]
            return SimpleNamespace(data=data, usage=_ns(prompt_tokens=7, total_tokens=7))

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))
        self.beta = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=create)))
        self.embeddings = SimpleNamespace(create=embed)


def _answer_generator(client, **kwargs):
    from gaik.software_components.RAG.answer_generator import AnswerGenerator

    generator = AnswerGenerator(config=OPENAI, **kwargs)
    generator.client = client
    return generator


def _doc(text):
    from langchain_core.documents import Document

    return Document(page_content=text, metadata={"source": "a.pdf"})


def test_a_direct_call_is_one_span_named_after_its_component(spans):
    pytest.importorskip("langchain_core")
    generator = _answer_generator(_RawOpenAI(_completion()), stream=False)

    assert generator.generate("Mikä on laskun summa?", [_doc(SECRET)]) == ANSWER

    (span,) = spans()
    assert span.name == "chat gpt-4.1"
    assert span.attributes["gaik.component.name"] == "AnswerGenerator"
    assert span.attributes["gen_ai.provider.name"] == "openai"
    assert span.attributes["gen_ai.usage.input_tokens"] == 100
    assert span.attributes["gen_ai.usage.output_tokens"] == 20
    assert span.attributes["gen_ai.request.temperature"] == 0.0
    assert span.attributes["gaik.output.length"] == len(ANSWER)
    assert span.attributes["gaik.input.length"] > len(SECRET)
    _assert_clean(span)


def test_a_component_s_error_passes_through_unchanged(spans):
    pytest.importorskip("langchain_core")
    error = ValueError(SECRET)
    generator = _answer_generator(_RawOpenAI(error=error), stream=False)

    with pytest.raises(ValueError) as caught:
        generator.generate("q", [_doc("x")])
    assert caught.value is error

    (span,) = spans()
    assert span.attributes["error.type"] == "builtins.ValueError"
    _assert_clean(span)


def test_a_streamed_answer_is_one_span_that_ends_with_the_stream(spans):
    pytest.importorskip("langchain_core")
    chunks = [
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=part))])
        for part in ("Asiakas ", "valittaa")
    ]
    generator = _answer_generator(_RawOpenAI(stream=chunks), stream=True)

    stream = generator.generate("q", [_doc(SECRET)])
    assert not spans()  # nothing is sent before the first read
    assert "".join(stream) == "Asiakas valittaa"

    (span,) = spans()
    assert span.attributes["gaik.component.name"] == "AnswerGenerator"
    assert span.attributes["gen_ai.request.temperature"] == 0.0
    assert span.attributes["gaik.output.length"] == len("Asiakas valittaa")
    _assert_clean(span)


def test_a_call_through_a_provider_client_gets_no_second_span(spans):
    pytest.importorskip("langchain_core")
    from gaik.software_components.llm.base import ChatResponse
    from gaik.software_components.llm.traced_client import TracedProviderClient

    inner = client_tests._FakeProvider(
        result=ChatResponse(text=ANSWER, model="gpt-4.1", provider="openai", usage={}, raw=None)
    )
    generator = _answer_generator(TracedProviderClient(inner), stream=False)

    assert generator.generate("q", [_doc("x")]) == ANSWER
    (span,) = spans()
    assert span.attributes["gaik.component.name"] == "AnswerGenerator"


def test_embedder_batches_are_embedding_spans_with_tokens(spans):
    from gaik.software_components.RAG.embedder import Embedder

    embedder = Embedder({**OPENAI, "embedding_model": "text-embedding-3-small"})
    embedder.client = _RawOpenAI()

    vectors, _ = embedder.embed([SECRET, "toinen"], batch_size=1)

    assert len(vectors) == 2
    first, second = spans()
    assert first.name == "embeddings text-embedding-3-small"
    assert first.attributes["gaik.component.name"] == "Embedder"
    assert first.attributes["gen_ai.usage.input_tokens"] == 7
    assert first.attributes["gaik.input.length"] == len(SECRET)
    assert second.attributes["gaik.input.length"] == len("toinen")
    _assert_clean(first)


def test_document_classifier_records_settings_tokens_and_lengths(spans):
    from gaik.software_components.doc_classifier.classifier import DocumentClassifier

    classifier = DocumentClassifier(OPENAI)
    model = None

    def parse(**kwargs):
        nonlocal model
        model = kwargs["response_format"]
        return _completion(
            parsed=model(document_class="invoice", confidence=0.9, reasoning="totals")
        )

    classifier.client = SimpleNamespace(
        beta=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)))
    )

    result = classifier._classify_with_llm(SECRET, ["invoice", "contract"])

    assert result["class"] == "invoice"
    (span,) = spans()
    assert span.attributes["gaik.component.name"] == "DocumentClassifier"
    assert span.attributes["gen_ai.usage.input_tokens"] == 100
    assert span.attributes["gaik.output.length"] > 0
    _assert_clean(span)


def test_tabular_agent_retries_are_counted_in_one_span(spans, tmp_path, monkeypatch):
    pytest.importorskip("duckdb")
    from gaik.software_components.tabular_agent.agent import TabularAgent
    from gaik.software_components.tabular_agent.models import GeneratedSQL
    from openai import APITimeoutError

    csv = tmp_path / "sales.csv"
    csv.write_text("region,total\nnorth,1\n", encoding="utf-8")
    agent = TabularAgent(csv, model="gpt-4.1")
    attempts = []

    def parse(**kwargs):
        attempts.append(kwargs)
        if len(attempts) == 1:
            raise APITimeoutError(request=MagicMock())
        return _completion(parsed=GeneratedSQL(sql="SELECT 1", reasoning="stub"))

    agent._llm_client = SimpleNamespace(
        beta=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)))
    )
    import gaik.software_components.tabular_agent.agent as module

    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    agent._parse_structured([{"role": "user", "content": SECRET}], GeneratedSQL)

    assert len(attempts) == 2
    (span,) = spans()
    assert span.attributes["gaik.component.name"] == "TabularAgent"
    assert span.attributes["gen_ai.usage.input_tokens"] == 100  # the failed try had none
    assert "error.type" not in span.attributes


def test_gemini_rest_call_in_the_multimodal_parser(spans, monkeypatch, tmp_path):
    from gaik.software_components.parsers.multimodal_parser import multimodal_parser as module

    payload = {
        "candidates": [{"content": {"parts": [{"text": ANSWER}]}}],
        "usageMetadata": {"promptTokenCount": 300, "candidatesTokenCount": 40},
    }
    response = MagicMock()
    response.json.return_value = payload
    monkeypatch.setattr(module.requests, "post", lambda *a, **k: response)
    monkeypatch.setattr(module, "_build_google_body", lambda *a: {})
    parser = object.__new__(module.MultimodalParser)
    parser.config = {"vertex_ai": False, "api_key": "test-key", "model": "gemini-2.5-flash"}
    parser.reasoning_effort = "low"

    text, _ = parser._call_google(tmp_path / "a.pdf", "system", SECRET)

    assert text == ANSWER + "\n"
    (span,) = spans()
    assert span.attributes["gaik.component.name"] == "MultimodalParser"
    assert span.attributes["gen_ai.provider.name"] == "gcp.gemini"
    assert span.attributes["gen_ai.usage.input_tokens"] == 300
    _assert_clean(span)


def test_components_work_the_same_with_tracing_off(off, monkeypatch):
    pytest.importorskip("langchain_core")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    tracing._reset_for_tests()
    generator = _answer_generator(_RawOpenAI(_completion()), stream=False)

    assert generator.generate("q", [_doc("x")]) == ANSWER
    assert not tracing.tracing_enabled()


def test_a_transcription_span_has_tokens_but_no_cost(spans):
    usage = _ns(type="tokens", input_tokens=1000, output_tokens=200)
    with llm_span(
        "Transcriber", provider="azure", model="gpt-4o-mini-transcribe", operation="transcription"
    ):
        record_response(_ns(usage=usage))

    (span,) = spans()
    assert span.name == "transcription gpt-4o-mini-transcribe"
    assert span.attributes["gen_ai.usage.input_tokens"] == 1000
    # The chat rate of gpt-4o-mini would match by prefix; audio is billed otherwise.
    assert "gaik.cost.usd" not in span.attributes


def test_no_component_span_without_the_extra(spans, monkeypatch):
    pytest.importorskip("langchain_core")
    monkeypatch.setattr(tracing, "_extra", False)
    generator = _answer_generator(_RawOpenAI(_completion()), stream=False)

    assert generator.generate("q", [_doc("x")]) == ANSWER
    assert not spans()


def test_llm_judge_text_call_is_one_span(spans, monkeypatch):
    from gaik.software_components.parsers.multimodal_parser import config as mm_config
    from gaik.software_components.validators.llm_judge.llm_judge import LLMJudge

    raw = _RawOpenAI(_completion(content='{"equivalent": true}'))
    monkeypatch.setattr(mm_config, "get_openai_config", lambda use_azure: {"model": "gpt-4.1"})
    monkeypatch.setattr(mm_config, "create_openai_client", lambda config: raw)
    judge = LLMJudge(model_provider="openai", use_azure=False, model="gpt-4.1")

    text, input_tokens, output_tokens = judge._dispatch_text(SECRET, "system")

    assert (text, input_tokens, output_tokens) == ('{"equivalent": true}', 100, 20)
    (span,) = spans()
    assert span.attributes["gaik.component.name"] == "LLMJudge"
    assert span.attributes["gen_ai.provider.name"] == "openai"
    assert span.attributes["gen_ai.usage.input_tokens"] == 100
    assert span.attributes["gaik.output.length"] == len(text)
    _assert_clean(span)


def test_a_streamed_answer_closed_early_ends_its_span(spans):
    pytest.importorskip("langchain_core")
    chunks = [
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=part))])
        for part in ("Asiakas ", "valittaa")
    ]
    generator = _answer_generator(_RawOpenAI(stream=chunks), stream=True)

    stream = generator.generate("q", [_doc(SECRET)])
    assert next(stream) == "Asiakas "
    stream.close()

    (span,) = spans()
    assert span.attributes["gaik.output.length"] == len("Asiakas ")
    assert "error.type" not in span.attributes
