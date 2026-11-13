"""OpenTelemetry spans for clients from ``create_llm_client()`` (llm.traced_client).

Every adapter the factory returns is built for real, with its SDK client
swapped for a fake that answers like the SDK. No network. Spans are read back
through the in-memory exporter of ``test_observability_tracing``.
"""

from __future__ import annotations

import contextvars
import copy
import sys
import types
import weakref
from types import SimpleNamespace

import pytest
from gaik.observability import llm_span, tracing
from gaik.software_components.llm import ProviderClient, create_llm_client
from gaik.software_components.llm import traced_client as traced
from gaik.software_components.llm.base import ChatResponse
from gaik.software_components.llm.traced_client import TracedProviderClient
from pydantic import BaseModel

from . import test_observability_tracing as tracing_tests

# The in-memory exporter and its fixtures are shared with the tracing tests.
spans, off = tracing_tests.spans, tracing_tests.off
trace, needs_otel, _values = tracing_tests.trace, tracing_tests.needs_otel, tracing_tests._values

SECRET = "Matti Virtanen, henkilötunnus 010101-123X"
ANSWER = "Asiakas Matti Virtanen valittaa laskusta"
MESSAGES = [
    {"role": "system", "content": "You are a helpdesk."},
    {"role": "user", "content": [{"type": "text", "text": SECRET}]},
]
INPUT_LENGTH = len("You are a helpdesk.") + len(SECRET)

#: Every attribute an llm_call span may carry; anything else is a leak to look at.
ALLOWED = {
    "gaik.event.class",
    "gen_ai.operation.name",
    "gen_ai.provider.name",
    "gen_ai.request.model",
    "gen_ai.response.model",
    "gen_ai.request.temperature",
    "gen_ai.request.top_p",
    "gen_ai.request.top_k",
    "gen_ai.request.max_tokens",
    "gaik.request.reasoning_effort",
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "gaik.usage.thinking_tokens",
    "gaik.cost.usd",
    "gaik.cost.estimated",
    "gaik.provider.name",
    "gaik.component.name",
    "gaik.component.version",
    "gaik.prompt.version",
    "gaik.config.version",
    "gaik.input.length",
    "gaik.output.length",
    "error.type",
}


class Ticket(BaseModel):
    reporter: str


def _assert_clean(span) -> None:
    """No text, secret or endpoint in the span; only the attributes listed above."""
    assert set(span.attributes) <= ALLOWED, set(span.attributes) - ALLOWED
    values = _values(span)
    for text in (SECRET, ANSWER, "Matti", "test-key", "example", "http"):
        assert text not in values


# -- fake SDK clients, one per adapter --------------------------------------


class _Usage(SimpleNamespace):
    def model_dump(self):
        return dict(vars(self))


def _openai_raw(stream_finished: list | None = None):
    def completion(content):
        message = SimpleNamespace(content=content, parsed=Ticket(reporter=ANSWER))
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)],
            model="gpt-4.1-2025-04-14",
            usage=_Usage(prompt_tokens=120, completion_tokens=30, total_tokens=150),
        )

    def create(**kwargs):
        if kwargs.get("stream"):
            return _openai_chunks(stream_finished)
        return completion(ANSWER)

    def embeddings(**kwargs):
        data = [SimpleNamespace(index=i, embedding=[0.1, 0.2]) for i in range(len(kwargs["input"]))]
        return SimpleNamespace(data=data, usage=_Usage(prompt_tokens=9, total_tokens=9))

    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
        beta=SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(parse=lambda **kw: completion(None)))
        ),
        embeddings=SimpleNamespace(create=embeddings),
    )


def _openai_chunks(finished):
    try:
        for word in ANSWER.split(" "):
            delta = SimpleNamespace(content=word + " ")
            yield SimpleNamespace(choices=[SimpleNamespace(delta=delta)])
    finally:
        if finished is not None:
            finished.append(True)


def _azure_client():
    client = create_llm_client(
        {
            "provider": "azure",
            "api_key": "test-key",
            "api_version": "2025-03-01-preview",
            "azure_endpoint": "https://example.openai.azure.com/",
            "model": "gpt-4.1",
        }
    )
    client.raw = _openai_raw()
    return client


def _anthropic_client():
    pytest.importorskip("anthropic")
    client = create_llm_client(
        {"provider": "anthropic", "api_key": "test-key", "model": "claude-haiku-4-5"}
    )
    usage = SimpleNamespace(input_tokens=120, output_tokens=30)

    def create(**kwargs):
        if kwargs.get("tools"):
            block = SimpleNamespace(type="tool_use", name="Ticket", input={"reporter": ANSWER})
        else:
            block = SimpleNamespace(type="text", text=ANSWER)
        return SimpleNamespace(
            content=[block], model="claude-haiku-4-5-20251001", usage=usage, stop_reason="end"
        )

    class _Stream:
        text_stream = iter(ANSWER.split(" "))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    client.raw = SimpleNamespace(
        messages=SimpleNamespace(create=create, stream=lambda **kwargs: _Stream())
    )
    return client


def _google_client():
    pytest.importorskip("google.genai")
    client = create_llm_client(
        {"provider": "google", "api_key": "test-key", "model": "gemini-2.5-flash"}
    )
    usage = SimpleNamespace(prompt_token_count=120, candidates_token_count=30)

    def generate(**kwargs):
        parsed = {"reporter": ANSWER} if kwargs["config"].response_mime_type else None
        return SimpleNamespace(text=ANSWER, parsed=parsed, usage_metadata=usage)

    def stream(**kwargs):
        return iter(SimpleNamespace(text=w) for w in ANSWER.split(" "))

    def embed(**kwargs):
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=[0.1]) for _ in kwargs["contents"]]
        )

    client.raw = SimpleNamespace(
        models=SimpleNamespace(
            generate_content=generate, generate_content_stream=stream, embed_content=embed
        )
    )
    return client


def _litellm_client(monkeypatch):
    pytest.importorskip("litellm")
    from gaik.software_components.llm import litellm_provider

    def completion(**kwargs):
        if kwargs.get("stream"):
            delta = [SimpleNamespace(content=w) for w in ANSWER.split(" ")]
            return iter(SimpleNamespace(choices=[SimpleNamespace(delta=d)]) for d in delta)
        content = (
            Ticket(reporter=ANSWER).model_dump_json() if "response_format" in kwargs else ANSWER
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            model="gpt-4.1",
            usage=_Usage(prompt_tokens=120, completion_tokens=30, total_tokens=150),
        )

    def embedding(**kwargs):
        usage = _Usage(prompt_tokens=9, total_tokens=9)
        return SimpleNamespace(data=[{"index": 0, "embedding": [0.1]}], usage=usage)

    monkeypatch.setattr(litellm_provider.litellm, "completion", completion)
    monkeypatch.setattr(litellm_provider.litellm, "embedding", embedding)
    return create_llm_client(
        {"provider": "litellm", "model": "azure/gpt-4.1", "embedding_model": "azure/emb"}
    )


#: provider -> (builder, gen_ai.provider.name, request model, priced)
ADAPTERS = {
    "azure": (lambda mp: _azure_client(), "azure.ai.openai", "gpt-4.1", True),
    "anthropic": (lambda mp: _anthropic_client(), "anthropic", "claude-haiku-4-5", True),
    "google": (lambda mp: _google_client(), "gcp.gemini", "gemini-2.5-flash", True),
    "litellm": (_litellm_client, "litellm", "azure/gpt-4.1", False),
}


@pytest.fixture(params=sorted(ADAPTERS))
def adapter(request, spans, monkeypatch):
    build, gen_ai_provider, model, priced = ADAPTERS[request.param]
    return SimpleNamespace(
        client=build(monkeypatch),
        name=request.param,
        gen_ai_provider=gen_ai_provider,
        model=model,
        priced=priced,
        spans=spans,
    )


# -- one span per call, on every adapter ------------------------------------


def test_the_factory_s_client_is_wrapped_and_still_the_adapter(adapter):
    client = adapter.client
    inner = client.__wrapped__
    assert type(client) is TracedProviderClient
    assert isinstance(client, ProviderClient)
    assert isinstance(client, type(inner))
    assert client.provider == inner.provider
    assert client.usage is inner.usage
    assert repr(client) == repr(inner)


def test_chat_is_one_span_with_tokens_lengths_and_no_text(adapter):
    response = adapter.client.chat(MESSAGES, temperature=0.2)

    assert isinstance(response, ChatResponse)
    assert response.text == ANSWER
    (span,) = adapter.spans()
    a = span.attributes
    assert span.name == f"chat {adapter.model}"
    assert span.kind == trace.SpanKind.CLIENT
    assert a["gaik.event.class"] == "llm_call"
    assert a["gen_ai.operation.name"] == "chat"
    assert a["gen_ai.provider.name"] == adapter.gen_ai_provider
    assert a["gaik.provider.name"] == adapter.name
    assert a["gen_ai.request.model"] == adapter.model
    assert a["gen_ai.request.temperature"] == 0.2
    assert a["gen_ai.usage.input_tokens"] == 120
    assert a["gen_ai.usage.output_tokens"] == 30
    assert a["gaik.input.length"] == INPUT_LENGTH
    assert a["gaik.output.length"] == len(ANSWER)
    assert "gaik.component.name" not in a
    assert ("gaik.cost.usd" in a) is adapter.priced
    if adapter.priced:
        assert a["gaik.cost.estimated"] is True
    _assert_clean(span)


def test_chat_parsed_is_one_span_with_tokens_and_the_record_s_length(adapter):
    parsed = adapter.client.chat_parsed(MESSAGES, Ticket)

    assert parsed == Ticket(reporter=ANSWER)
    (span,) = adapter.spans()
    a = span.attributes
    assert span.name == f"chat {adapter.model}"
    assert a["gen_ai.usage.input_tokens"] == 120
    assert a["gaik.output.length"] == len(parsed.model_dump_json())
    _assert_clean(span)


def test_chat_stream_is_one_span_that_ends_when_the_stream_is_read(adapter):
    stream = adapter.client.chat_stream(MESSAGES)

    assert isinstance(stream, types.GeneratorType)
    assert adapter.spans() == ()  # nothing is sent before the first read
    chunks = list(stream)

    assert "".join(chunks).replace(" ", "") == ANSWER.replace(" ", "")
    (span,) = adapter.spans()
    assert span.name == f"chat {adapter.model}"
    assert span.attributes["gaik.output.length"] == len("".join(chunks))
    assert span.attributes["gaik.input.length"] == INPUT_LENGTH
    _assert_clean(span)


def test_embed_is_one_embeddings_span(adapter):
    if adapter.name == "anthropic":
        with pytest.raises(NotImplementedError):
            adapter.client.embed([SECRET])
        (span,) = adapter.spans()
        assert span.attributes["error.type"] == "builtins.NotImplementedError"
        _assert_clean(span)
        return

    vectors = adapter.client.embed([SECRET])

    assert len(vectors) == 1
    (span,) = adapter.spans()
    assert span.name.startswith("embeddings ")
    assert span.attributes["gen_ai.operation.name"] == "embeddings"
    assert span.attributes["gaik.input.length"] == len(SECRET)
    # OpenAI and LiteLLM report the embedding's tokens; Gemini's API does not.
    if adapter.name in ("azure", "litellm"):
        assert span.attributes["gen_ai.usage.input_tokens"] == 9
    _assert_clean(span)


# -- the caller sees the client's own result and exceptions -----------------


class _FakeProvider:
    """A ProviderClient whose calls do what a test tells them."""

    provider = "openai"
    model = "gpt-4.1"
    embedding_model = "text-embedding-3-small"

    def __init__(self, result=None, error=None, chunks=(), fail_after=None):
        self.result, self.error = result, error
        self.chunks, self.fail_after = list(chunks), fail_after
        self.raw = object()
        self.closed = False
        self.calls = []

    def chat(self, messages, *args, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result

    chat_parsed = embed = chat

    def chat_stream(self, messages, **kwargs):
        try:
            for i, chunk in enumerate(self.chunks):
                if self.fail_after is not None and i == self.fail_after:
                    raise self.error
                yield chunk
        finally:
            self.closed = True


def test_the_result_is_the_client_s_own_object_and_arguments_pass_unchanged(spans):
    sentinel = object()
    fake = _FakeProvider(result=sentinel)
    client = TracedProviderClient(fake)

    assert client.chat(MESSAGES, temperature=0.1, model="other") is sentinel
    assert client.chat_parsed(MESSAGES, Ticket) is sentinel
    assert client.embed(["x"]) is sentinel
    assert fake.calls == [{"temperature": 0.1, "model": "other"}, {}, {}]
    names = [s.name for s in spans()]
    assert names == ["chat other", "chat gpt-4.1", "embeddings text-embedding-3-small"]


def test_the_client_s_exception_passes_through_unchanged_with_only_its_type(spans):
    error = ValueError(f"provider said: {SECRET}")
    client = TracedProviderClient(_FakeProvider(error=error))

    with pytest.raises(ValueError) as caught:
        client.chat(MESSAGES)

    assert caught.value is error
    # The traceback still reaches the frame that raised it.
    tb = caught.value.__traceback__
    while tb.tb_next is not None:
        tb = tb.tb_next
    assert tb.tb_frame.f_code.co_name == "chat"
    assert tb.tb_frame.f_locals["self"].__class__ is _FakeProvider
    (span,) = spans()
    assert span.status.status_code == trace.StatusCode.ERROR
    assert span.attributes["error.type"] == "builtins.ValueError"
    assert not span.events  # no recorded exception, so no message
    _assert_clean(span)


def test_an_adapter_s_sdk_error_passes_through_unchanged(spans):
    client = _azure_client()
    error = RuntimeError(SECRET)

    def boom(**kwargs):
        raise error

    client.raw.chat.completions.create = boom
    with pytest.raises(RuntimeError) as caught:
        client.chat(MESSAGES)
    assert caught.value is error
    (span,) = spans()
    assert span.attributes["error.type"] == "builtins.RuntimeError"
    _assert_clean(span)


# -- streams -----------------------------------------------------------------


def test_a_stream_closed_early_ends_its_span_and_closes_the_client_s_stream(spans):
    fake = _FakeProvider(chunks=["a", "b", "c"])
    stream = TracedProviderClient(fake).chat_stream(MESSAGES)

    assert next(stream) == "a"
    assert spans() == ()
    stream.close()

    assert fake.closed
    (span,) = spans()
    assert span.attributes["gaik.output.length"] == 1
    assert span.status.status_code == trace.StatusCode.UNSET


def test_a_stream_dropped_unread_ends_its_span(spans):
    fake = _FakeProvider(chunks=["a", "b"])
    stream = TracedProviderClient(fake).chat_stream(MESSAGES)
    next(stream)
    del stream  # CPython finalizes the generator here

    assert fake.closed
    assert len(spans()) == 1


def test_a_stream_that_fails_ends_its_span_and_raises_the_same_error(spans):
    error = ConnectionError(SECRET)
    fake = _FakeProvider(chunks=["a", "b"], fail_after=1, error=error)
    stream = TracedProviderClient(fake).chat_stream(MESSAGES)

    assert next(stream) == "a"
    with pytest.raises(ConnectionError) as caught:
        next(stream)

    assert caught.value is error
    (span,) = spans()
    assert span.attributes["error.type"] == "builtins.ConnectionError"
    assert span.status.status_code == trace.StatusCode.ERROR
    _assert_clean(span)


def test_a_stream_is_current_only_while_the_client_makes_a_chunk(spans):
    tracer = trace.get_tracer("test")
    seen = []

    class _Client(_FakeProvider):
        def chat_stream(self, messages, **kwargs):
            for chunk in ("a", "b"):
                with tracer.start_as_current_span("http"):
                    seen.append(tracing.in_llm_span())
                yield chunk

    stream = TracedProviderClient(_Client()).chat_stream(MESSAGES)
    for _ in stream:
        # The caller's own work between chunks is outside the stream's span.
        assert not tracing.in_llm_span()
        with tracer.start_as_current_span("caller"):
            pass

    assert seen == [True, True]
    by_name = {}
    for span in spans():
        by_name.setdefault(span.name, []).append(span)
    (llm,) = by_name["chat gpt-4.1"]
    assert all(s.parent.span_id == llm.context.span_id for s in by_name["http"])
    assert all(s.parent is None for s in by_name["caller"])


def test_two_streams_read_in_turn_keep_their_own_spans(spans):
    first = TracedProviderClient(_FakeProvider(chunks=["a", "b"])).chat_stream(MESSAGES)
    second = TracedProviderClient(_FakeProvider(chunks=["c", "d"])).chat_stream(MESSAGES)

    assert [next(first), next(second), next(first), next(second)] == ["a", "c", "b", "d"]
    assert list(first) == list(second) == []

    one, two = spans()
    assert one.parent is None and two.parent is None
    assert one.context.span_id != two.context.span_id


# -- nesting -----------------------------------------------------------------


def test_a_call_nests_under_the_application_s_span(spans):
    tracer = trace.get_tracer("app")
    client = TracedProviderClient(_FakeProvider(result="ok"))

    with tracer.start_as_current_span("request") as parent:
        client.chat(MESSAGES)
        list(TracedProviderClient(_FakeProvider(chunks=["x"])).chat_stream(MESSAGES))

    calls = [s for s in spans() if s.name.startswith("chat")]
    assert len(calls) == 2
    assert all(s.parent.span_id == parent.get_span_context().span_id for s in calls)


def test_a_call_inside_a_component_s_own_span_makes_no_second_span(spans):
    client = TracedProviderClient(_FakeProvider(result="ok", chunks=["x"]))

    with llm_span("DataExtractor", provider="openai", model="gpt-4.1"):
        client.chat(MESSAGES)
        list(client.chat_stream(MESSAGES))

    (span,) = spans()
    assert span.attributes["gaik.component.name"] == "DataExtractor"


def test_the_extractor_on_a_factory_client_is_one_span_with_the_adapter_s_tokens(spans):
    pytest.importorskip("anthropic")
    from gaik.software_components.extractor.extractor import DataExtractor
    from gaik.software_components.extractor.schema import ExtractionRequirements

    client = _anthropic_client()
    config = {"provider": "anthropic", "model": "claude-haiku-4-5"}
    extractor = DataExtractor.__new__(DataExtractor)
    extractor.config, extractor.model, extractor.client = config, config["model"], client
    extractor.temperature, extractor.reasoning_effort = 0.0, None
    requirements = ExtractionRequirements(use_case_name="ticket", fields=[])

    extractor._extract_one(SECRET, Ticket, requirements, "Extract")

    (span,) = spans()
    a = span.attributes
    assert a["gaik.component.name"] == "DataExtractor"
    assert a["gen_ai.usage.input_tokens"] == 120
    assert a["gen_ai.response.model"] == "claude-haiku-4-5-20251001"
    _assert_clean(span)


# -- off, and faults ---------------------------------------------------------


def test_without_the_extra_the_factory_returns_the_adapter_itself(monkeypatch, off):
    monkeypatch.setitem(sys.modules, "opentelemetry", None)
    client = create_llm_client({"provider": "openai", "api_key": "test-key", "model": "gpt-4.1"})
    assert type(client).__name__ == "OpenAIProvider"
    client.raw = _openai_raw()
    assert client.chat(MESSAGES).text == ANSWER


@needs_otel
def test_otel_sdk_disabled_returns_the_adapter_itself(monkeypatch, off):
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    client = create_llm_client({"provider": "openai", "api_key": "test-key", "model": "gpt-4.1"})
    assert type(client).__name__ == "OpenAIProvider"


@needs_otel
def test_without_a_recording_tracer_calls_and_streams_pass_through(monkeypatch, spans):
    monkeypatch.setattr(tracing, "_tracer", trace.NoOpTracer())
    monkeypatch.setattr(tracing, "_resolved", True)
    fake = _FakeProvider(result="ok", chunks=["a", "b"])
    client = TracedProviderClient(fake)

    assert client.chat(MESSAGES) == "ok"
    stream = client.chat_stream(MESSAGES)
    assert next(stream) == "a"
    stream.close()
    assert fake.closed
    assert spans() == ()


def test_a_fault_in_the_tracer_never_reaches_the_caller(spans, monkeypatch):
    class _Broken:
        def start_span(self, *args, **kwargs):
            raise RuntimeError("tracer down")

    monkeypatch.setattr(tracing, "_tracer", _Broken())
    monkeypatch.setattr(tracing, "_resolved", True)
    client = TracedProviderClient(_FakeProvider(result="ok", chunks=["a"]))

    assert client.chat(MESSAGES) == "ok"
    assert list(client.chat_stream(MESSAGES)) == ["a"]


def test_a_fault_in_a_recording_span_never_reaches_the_caller(spans, monkeypatch):
    from opentelemetry.sdk.trace import Span

    def broken(self, *args, **kwargs):
        raise RuntimeError("exporter down")

    monkeypatch.setattr(Span, "set_attributes", broken)
    monkeypatch.setattr(Span, "set_attribute", broken)
    monkeypatch.setattr(Span, "set_status", broken)
    client = TracedProviderClient(_FakeProvider(result="ok", chunks=["a"]))

    assert client.chat(MESSAGES) == "ok"
    assert list(client.chat_stream(MESSAGES)) == ["a"]
    error = ValueError("x")
    with pytest.raises(ValueError) as caught:
        TracedProviderClient(_FakeProvider(error=error)).chat(MESSAGES)
    assert caught.value is error


def test_a_fault_in_the_wrapper_s_own_steps_never_reaches_the_caller(spans, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("bug")

    monkeypatch.setattr(traced, "llm_span", broken)
    monkeypatch.setattr(traced, "start_llm_span", broken)
    client = TracedProviderClient(_FakeProvider(result="ok", chunks=["a"]))
    assert client.chat(MESSAGES) == "ok"
    assert list(client.chat_stream(MESSAGES)) == ["a"]
    # Messages the wrapper cannot measure are still the client's business.
    monkeypatch.undo()
    assert client.chat([object()]) == "ok"
    assert "gaik.input.length" not in spans()[-1].attributes

    monkeypatch.setattr(traced, "in_llm_span", broken)
    assert client.chat(MESSAGES) == "ok"
    assert list(client.chat_stream(MESSAGES)) == ["a"]


# -- transparency ------------------------------------------------------------


def test_attributes_are_the_client_s_to_read_and_set(spans):
    fake = _FakeProvider(result="ok")
    client = TracedProviderClient(fake)

    client.model = "gpt-4.1-mini"
    client.raw = "new raw"
    client.extra = 1
    assert (fake.model, fake.raw, fake.extra) == ("gpt-4.1-mini", "new raw", 1)
    assert client.extra == 1
    del client.extra
    assert not hasattr(fake, "extra")
    with pytest.raises(AttributeError):
        _ = client.missing
    assert "chat_stream" in dir(client)
    assert client.__wrapped__ is fake
    assert isinstance(client, _FakeProvider)
    assert traced.traced_client(client) is client  # never wrapped twice
    duplicate = copy.copy(client)
    assert type(duplicate) is TracedProviderClient
    assert duplicate.__wrapped__ is not fake


def test_putting_a_method_back_gives_the_client_its_own(spans, monkeypatch):
    fake = _FakeProvider(result="ok")
    client = TracedProviderClient(fake)

    monkeypatch.setattr(client, "chat", lambda *args, **kwargs: "patched")
    assert client.chat(MESSAGES) == "patched"
    monkeypatch.undo()  # sets client.chat back to the wrapper's own method

    assert "chat" not in vars(fake)
    assert client.chat(MESSAGES) == "ok"


def test_with_only_the_opentelemetry_api_the_factory_returns_the_adapter_itself(monkeypatch, off):
    # chromadb and others bring the API (and SDK) but not the extra's exporter.
    monkeypatch.setitem(sys.modules, "opentelemetry.exporter.otlp.proto.http", None)
    client = create_llm_client({"provider": "openai", "api_key": "test-key", "model": "gpt-4.1"})
    assert type(client).__name__ == "OpenAIProvider"


def test_a_method_stored_under_another_name_is_stored(spans):
    fake = _FakeProvider(result="ok")
    fake.on_done = "old"
    client = TracedProviderClient(fake)

    client.on_done = client.chat

    assert fake.on_done == client.chat
    assert client.on_done(MESSAGES) == "ok"
    assert weakref.ref(client)() is client


def test_a_stream_made_outside_a_component_s_span_and_read_inside_it_is_one_span(spans):
    stream = TracedProviderClient(_FakeProvider(chunks=["a"])).chat_stream(MESSAGES)
    with llm_span("DataExtractor", provider="openai", model="gpt-4.1"):
        assert list(stream) == ["a"]

    (span,) = spans()
    assert span.attributes["gaik.component.name"] == "DataExtractor"


def test_a_context_copied_inside_an_ended_span_still_traces_its_calls(spans):
    client = TracedProviderClient(_FakeProvider(result="ok"))
    with llm_span("DataExtractor", provider="openai", model="gpt-4.1"):
        copied = contextvars.copy_context()  # as an asyncio task made here would hold

    assert copied.run(client.chat, MESSAGES) == "ok"
    assert [s.name for s in spans()] == ["chat gpt-4.1", "chat gpt-4.1"]
    assert "gaik.component.name" not in spans()[1].attributes


def test_a_stream_that_is_not_iterable_still_ends_its_span(spans):
    class _Client(_FakeProvider):
        def chat_stream(self, messages, **kwargs):
            return 42

    stream = TracedProviderClient(_Client()).chat_stream(MESSAGES)
    with pytest.raises(TypeError):
        next(stream)

    (span,) = spans()
    assert span.attributes["error.type"] == "builtins.TypeError"


def test_a_stream_dropped_before_its_first_read_makes_no_span(spans):
    fake = _FakeProvider(chunks=["a"])
    stream = TracedProviderClient(fake).chat_stream(MESSAGES)
    del stream
    assert spans() == ()


def test_a_fault_making_the_span_current_never_reaches_the_caller(spans, monkeypatch):
    class _Broken:
        def __enter__(self):
            raise RuntimeError("context runtime down")

        def __exit__(self, *exc):
            raise RuntimeError("context runtime down")

    monkeypatch.setattr(tracing, "_current", lambda span: _Broken())
    error = ValueError("x")
    client = TracedProviderClient(_FakeProvider(result="ok", chunks=["a", "b"]))

    assert client.chat(MESSAGES) == "ok"
    assert list(client.chat_stream(MESSAGES)) == ["a", "b"]
    with pytest.raises(ValueError) as caught:
        TracedProviderClient(_FakeProvider(error=error)).chat(MESSAGES)
    assert caught.value is error
    assert len(spans()) == 3


def test_an_exception_thrown_into_a_stream_reaches_the_client_s_stream(spans):
    class _Client(_FakeProvider):
        def chat_stream(self, messages, **kwargs):
            try:
                yield "a"
            except TimeoutError:
                yield "recovered"

    stream = TracedProviderClient(_Client()).chat_stream(MESSAGES)
    assert next(stream) == "a"
    assert stream.throw(TimeoutError()) == "recovered"
    assert list(stream) == []

    (span,) = spans()
    assert span.status.status_code == trace.StatusCode.UNSET
    assert span.attributes["gaik.output.length"] == len("a") + len("recovered")


def test_responses_within_one_span_add_up(spans):
    from gaik.observability.tracing import record_response

    with llm_span("DataExtractor", provider="openai", model="gpt-4.1"):
        record_response({"prompt_tokens": 100, "completion_tokens": 10})
        record_response({"prompt_tokens": 100, "completion_tokens": 20})

    (span,) = spans()
    assert span.attributes["gen_ai.usage.input_tokens"] == 200
    assert span.attributes["gen_ai.usage.output_tokens"] == 30
    assert span.attributes["gaik.cost.usd"] == pytest.approx((200 * 2.00 + 30 * 8.00) / 1e6)
    # The response did not say how many tokens went to thinking: left out, not 0.
    assert "gaik.usage.thinking_tokens" not in span.attributes


def test_gemini_s_thinking_tokens_count_as_output(spans):
    pytest.importorskip("google.genai")
    client = _google_client()
    usage = SimpleNamespace(
        prompt_token_count=120, candidates_token_count=30, thoughts_token_count=50
    )
    client.raw.models.generate_content = lambda **kwargs: SimpleNamespace(
        text=ANSWER, parsed=None, usage_metadata=usage
    )

    response = client.chat(MESSAGES)

    assert response.usage == {"prompt_tokens": 120, "completion_tokens": 30}  # unchanged
    (span,) = spans()
    assert span.attributes["gen_ai.usage.output_tokens"] == 80
    assert span.attributes["gaik.usage.thinking_tokens"] == 50


@needs_otel
def test_the_extra_is_looked_up_once_not_on_every_call(monkeypatch, spans):
    import importlib.util

    calls = []
    real = importlib.util.find_spec

    def counting(name, *args, **kwargs):
        calls.append(name)
        return real(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", counting)
    client = TracedProviderClient(_FakeProvider(result="ok", chunks=["a"]))
    for _ in range(3):
        client.chat(MESSAGES)
        list(client.chat_stream(MESSAGES))

    assert calls.count("opentelemetry.exporter.otlp.proto.http") == 1
    assert len(spans()) == 6
