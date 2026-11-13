"""Each component's direct model call, traced at its real call site.

Every case builds the component for real and swaps its SDK client (or the
HTTP call) for a fake that answers like the SDK, or raises. Each case runs
three ways: with tracing on (one span per call, named after the component,
lengths and tokens only), with the call failing (the same exception object,
only its type on the span), and with tracing off (the same result, no spans).
No network.
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from gaik.observability import tracing
from pydantic import BaseModel

from . import test_observability_llm_client as client_tests
from . import test_observability_tracing as tracing_tests

spans = tracing_tests.spans
SECRET, ANSWER, _assert_clean = client_tests.SECRET, client_tests.ANSWER, client_tests._assert_clean
MESSAGES = client_tests.MESSAGES
SRT = "1\n00:00:00,000 --> 00:00:01,000\nhei\n"


def _ns(**kwargs):
    return SimpleNamespace(**kwargs)


def _completion(content=ANSWER, parsed=None):
    usage = client_tests._Usage(prompt_tokens=100, completion_tokens=20, total_tokens=120)
    message = _ns(content=content, parsed=parsed)
    return _ns(choices=[_ns(message=message)], usage=usage, model="gpt-4.1-2025-04-14")


def _raw_openai(response, error):
    """An ``OpenAI`` stand-in whose chat calls return ``response`` or raise ``error``."""

    def create(**kwargs):
        if error is not None:
            raise error
        return response

    return _ns(
        chat=_ns(completions=_ns(create=create)),
        beta=_ns(chat=_ns(completions=_ns(parse=create))),
    )


class _Audio:
    """An ``OpenAI`` stand-in for audio transcription."""

    def __init__(self, response, error):
        def create(**kwargs):
            if error is not None:
                raise error
            return response

        self.audio = _ns(transcriptions=_ns(create=create))

    def close(self):
        pass


# -- the cases ------------------------------------------------------------------
#
# Each returns (run, expected): ``run()`` makes the component's call, and
# ``expected`` says what its spans hold.


def _transcript_enhancer(mp, tmp_path, error):
    from gaik.software_components.enhance_transcript import TranscriptEnhancer

    enhancer = TranscriptEnhancer(
        api_config={"provider": "openai", "api_key": "test-key", "model": "gpt-4.1"}
    )
    enhancer.client = _raw_openai(_completion(), error)
    run = lambda: enhancer._chat_text(MESSAGES, fallback="fallback")  # noqa: E731
    return run, {"component": "TranscriptEnhancer", "input_tokens": 100}


def _schema_generator(mp, tmp_path, error):
    from gaik.software_components.extractor import schema
    from gaik.software_components.extractor.schema import StructureAnalysis

    parsed = StructureAnalysis(
        structure_type="flat",
        parent_container_name="records",
        parent_description="d",
        item_description="i",
        reasoning="r",
    )
    client = _raw_openai(_completion(parsed=parsed), error)
    run = lambda: schema.detect_structure_type(SECRET, client=client, model="gpt-4.1")  # noqa: E731
    return run, {"component": "SchemaGenerator", "input_tokens": 100}


def _form_understander(mp, tmp_path, error):
    from gaik.software_components.form_understander import FormUnderstander, understander
    from gaik.software_components.form_understander.understander import LabelMapping

    mapping = LabelMapping.model_validate({"entries": [{"id": "a", "label": "Nimi"}]})
    mp.setattr(
        understander,
        "build_compat_client",
        lambda config: _raw_openai(_completion(parsed=mapping), error),
    )
    form = FormUnderstander({"use_azure": False, "model": "gpt-4.1"})
    run = lambda: form.clean_labels([{"id": "a", "raw": SECRET}])  # noqa: E731
    return run, {"component": "FormUnderstander", "input_tokens": 100}


def _parallel_transcriber(mp, tmp_path, error):
    from gaik.software_components.parallel_transcriber import pipeline
    from gaik.software_components.parallel_transcriber.config import TranscriptionConfig

    config = TranscriptionConfig(max_retries=0, max_429_retries=0, retry_base_delay_seconds=0)
    transcriber = pipeline.ParallelTranscriber(
        {"use_azure": False, "api_key": "test-key", "transcription_model": "whisper-1"}, config
    )
    mp.setattr(transcriber, "_make_whisper_client", lambda: _Audio(SRT, error))
    chunks = []
    for i in range(3):
        chunk = tmp_path / f"chunk_{i}.mp3"
        chunk.write_bytes(b"audio")
        chunks.append(str(chunk))
    run = lambda: transcriber._transcribe_chunks_whisper(chunks, None, 3, None, None)  # noqa: E731
    # One span per chunk, each opened in its worker thread.
    return run, {"component": "ParallelTranscriber", "spans": 3, "operation": "transcription"}


def _vision_parser(mp, tmp_path, error):
    from gaik.software_components.parsers.vision import OpenAIConfig, VisionParser

    mp.setattr(VisionParser, "_initialize_client", lambda self: _raw_openai(_completion(), error))
    parser = VisionParser(OpenAIConfig(model="gpt-4.1", use_azure=False, api_key="test-key"))
    run = lambda: parser._chat_content(MESSAGES)  # noqa: E731
    return run, {"component": "VisionParser", "input_tokens": 100}


def _postgres_agent(mp, tmp_path, error):
    pytest.importorskip("psycopg")
    pytest.importorskip("sqlglot")
    from gaik.software_components.postgres_agent.agent import PostgresAgent
    from gaik.software_components.postgres_agent.models import (
        GeneratedSQL,
        SchemaInfo,
        TableInfo,
    )

    agent = PostgresAgent("postgresql://stub:stub@localhost:1/stub", model="gpt-4.1")
    agent._schema = SchemaInfo(schema_name="public", tables=[TableInfo(name="t", columns=[])])
    parsed = GeneratedSQL(sql="SELECT 1", reasoning="stub")
    agent._llm_client = _raw_openai(_completion(parsed=parsed), error)
    run = lambda: agent.generate_sql(SECRET)  # noqa: E731
    return run, {"component": "PostgresAgent", "input_tokens": 100}


def _text_to_speech(mp, tmp_path, error):
    from gaik.software_components.text_to_speech import TextToSpeech

    @contextmanager
    def create(**kwargs):
        if error is not None:
            raise error
        yield _ns(iter_bytes=lambda: iter([b"aud", b"io"]))

    tts = TextToSpeech(api_config={"use_azure": False, "api_key": "test-key"}, language="en")
    tts.client = _ns(audio=_ns(speech=_ns(with_streaming_response=_ns(create=create))))
    run = lambda: tts.synthesize(SECRET).audio_bytes  # noqa: E731
    return run, {"component": "TextToSpeech", "operation": "text_to_speech"}


def _transcription_response():
    usage = _ns(type="tokens", input_tokens=70, output_tokens=15, total_tokens=85)
    return _ns(text=ANSWER, usage=usage)


def _transcriber(mp, tmp_path, error):
    from gaik.software_components.transcriber import transcriber as module

    mp.setattr(
        module, "_create_audio_client", lambda config: _Audio(_transcription_response(), error)
    )
    instance = object.__new__(module.Transcriber)
    instance.api_config = {"provider": "openai", "api_key": "test-key"}
    audio = tmp_path / "talk.mp3"
    audio.write_bytes(b"audio")
    run = lambda: instance._single_pass_transcription(audio, SECRET, "gpt-4o-transcribe")  # noqa: E731
    return run, {"component": "Transcriber", "input_tokens": 70, "operation": "transcription"}


class _FakeAudio:
    """A pydub ``AudioSegment`` stand-in: 2 s long, exports any slice as bytes."""

    def __len__(self):
        return 2000

    def __getitem__(self, item):
        return _ns(export=lambda path, format: open(path, "wb").write(b"audio"))


def _transcriber_chunked(mp, tmp_path, error):
    from gaik.software_components.transcriber import transcriber as module

    mp.setattr(
        module, "_create_audio_client", lambda config: _Audio(_transcription_response(), error)
    )
    mp.setattr(module.time, "sleep", lambda seconds: None)
    audio = tmp_path / "talk.mp3"
    audio.write_bytes(b"audio")

    def run():
        return module.split_and_transcribe_with_context(
            str(audio),
            {"provider": "openai", "api_key": "test-key"},
            max_duration_seconds=1,  # three chunks of the 2 s fake
            audio=_FakeAudio(),
            base_prompt=SECRET,
            transcription_model="gpt-4o-transcribe",
        )

    # A failed chunk is marked in the transcript, not raised.
    return run, {
        "component": "Transcriber",
        "spans": 3,
        "swallows": True,
        "operation": "transcription",
    }


def _whisper_local(mp, tmp_path, error):
    from gaik.software_components.transcriber import whisper_local

    def post(*args, **kwargs):
        if error is not None:
            raise error
        return _ns(raise_for_status=lambda: None, json=lambda: {"text": ANSWER, "segments": []})

    mp.setattr(whisper_local.requests, "post", post)
    # The health check before the request is not traced.
    mp.setattr(
        whisper_local.requests,
        "get",
        lambda *a, **k: _ns(raise_for_status=lambda: None, json=lambda: {}),
    )
    audio = tmp_path / "talk.mp3"
    audio.write_bytes(b"audio")

    def run():
        return whisper_local.transcribe(
            audio, api_base="http://whisper.test", key="test-key", initial_prompt=SECRET
        )

    return run, {"component": "Transcriber", "operation": "transcription"}


class _Invoice(BaseModel):
    total: str


def _vision_extractor(provider):
    def case(mp, tmp_path, error):
        from gaik.software_components.vision_extractor import vision_extractor as module

        page = tmp_path / "page.png"
        page.write_bytes(b"\x89PNG fake")
        extractor = object.__new__(module.VisionExtractor)
        extractor.config = {"model": "m"}
        extractor.reasoning_effort = "low"

        if provider == "openai":
            extractor.model = "gpt-5.4"
            usage = _ns(
                input_tokens=500, output_tokens=90, output_tokens_details=_ns(reasoning_tokens=40)
            )
            response = _ns(output_text='{"total": "12"}', usage=usage, model="gpt-5.4")

            def create(**kwargs):
                if error is not None:
                    raise error
                return response

            mp.setattr(
                module, "create_openai_client", lambda config: _ns(responses=_ns(create=create))
            )
            call = extractor._call_openai
            expected = {"input_tokens": 500, "thinking_tokens": 40}
        else:
            extractor.model = "claude-sonnet-4-5"
            block = _ns(type="tool_use", name="extract_data", input={"total": "12"})
            usage = _ns(input_tokens=50, output_tokens=20, cache_read_input_tokens=900)
            message = _ns(content=[block], usage=usage, model="claude-sonnet-4-5")

            class FakeAnthropic:
                @contextmanager
                def _stream(self, **kwargs):
                    if error is not None:
                        raise error
                    yield _ns(get_final_message=lambda: message)

                @property
                def messages(self):
                    return _ns(stream=self._stream)

            mp.setattr(module, "create_claude_client", lambda config: FakeAnthropic())
            call = extractor._call_claude
            expected = {"input_tokens": 950, "cache_read": 900}

        run = lambda: call([page], "system", SECRET, _Invoice)[0]  # noqa: E731
        return run, {"component": "VisionExtractor", "output": True, **expected}

    return case


CASES = {
    "TranscriptEnhancer": _transcript_enhancer,
    "SchemaGenerator": _schema_generator,
    "FormUnderstander": _form_understander,
    "ParallelTranscriber": _parallel_transcriber,
    "VisionParser": _vision_parser,
    "PostgresAgent": _postgres_agent,
    "TextToSpeech": _text_to_speech,
    "Transcriber": _transcriber,
    "Transcriber-chunked": _transcriber_chunked,
    "whisper_local": _whisper_local,
    "VisionExtractor-openai": _vision_extractor("openai"),
    "VisionExtractor-claude": _vision_extractor("claude"),
}


def _tracing_off(monkeypatch):
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    tracing._reset_for_tests()
    tracing_tests._EXPORTER.clear()


# -- the three runs ----------------------------------------------------------------


@pytest.mark.parametrize("name", CASES)
def test_each_call_is_a_span_named_after_its_component(name, spans, monkeypatch, tmp_path):
    run, expected = CASES[name](monkeypatch, tmp_path, None)

    run()

    recorded = spans()
    assert len(recorded) == expected.get("spans", 1)
    for span in recorded:
        attributes = span.attributes
        assert attributes["gaik.component.name"] == expected["component"]
        assert attributes["gen_ai.operation.name"] == expected.get("operation", "chat")
        assert "error.type" not in attributes
        assert attributes["gaik.event.class"] == "llm_call"
        _assert_clean(span)
    first = recorded[0].attributes
    if "input_tokens" in expected:
        assert first["gen_ai.usage.input_tokens"] == expected["input_tokens"]
    if expected.get("operation") in ("transcription", "text_to_speech"):
        assert "gaik.cost.usd" not in first
    if "thinking_tokens" in expected:
        assert first["gaik.usage.thinking_tokens"] == expected["thinking_tokens"]
    if "cache_read" in expected:
        assert first["gen_ai.usage.cache_read.input_tokens"] == expected["cache_read"]
    if expected.get("output"):
        assert first["gaik.output.length"] == len('{"total": "12"}')


@pytest.mark.parametrize("name", CASES)
def test_a_failed_call_records_only_the_error_s_type(name, spans, monkeypatch, tmp_path):
    error = RuntimeError(SECRET)
    run, expected = CASES[name](monkeypatch, tmp_path, error)

    if expected.get("swallows"):
        assert "[Transcription failed for segment 1]" in run()
    else:
        with pytest.raises(RuntimeError) as caught:
            run()
        assert caught.value is error

    recorded = spans()
    assert len(recorded) == expected.get("spans", 1)
    for span in recorded:
        assert span.attributes["error.type"] == "builtins.RuntimeError"
        assert span.status.status_code == tracing_tests.trace.StatusCode.ERROR
        _assert_clean(span)


@pytest.mark.parametrize("name", CASES)
def test_with_tracing_off_the_component_behaves_the_same(name, spans, monkeypatch, tmp_path):
    run, _ = CASES[name](monkeypatch, tmp_path, None)
    traced = run()

    _tracing_off(monkeypatch)
    assert run() == traced
    assert not spans()

    error = RuntimeError(SECRET)
    failing, expected = CASES[name](monkeypatch, tmp_path, error)
    if not expected.get("swallows"):
        with pytest.raises(RuntimeError) as caught:
            failing()
        assert caught.value is error
    assert not spans()


def test_a_missing_audio_file_makes_no_span(spans, monkeypatch, tmp_path):
    from gaik.software_components.transcriber import transcriber as module

    mp_client = _Audio(_transcription_response(), None)
    monkeypatch.setattr(module, "_create_audio_client", lambda config: mp_client)
    instance = object.__new__(module.Transcriber)
    instance.api_config = {"provider": "openai", "api_key": "test-key"}

    with pytest.raises(FileNotFoundError):
        instance._single_pass_transcription(tmp_path / "missing.mp3", "", "whisper-1")
    assert not spans()


def test_a_chunk_s_span_excludes_the_pause_after_it(spans, monkeypatch, tmp_path):
    from gaik.software_components.transcriber import transcriber as module

    run, _ = _transcriber_chunked(monkeypatch, tmp_path, None)
    pauses = []

    def sleep(seconds):
        # The pause comes after the chunk's span has ended.
        pauses.append(len(spans()))

    monkeypatch.setattr(module.time, "sleep", sleep)
    run()

    assert pauses == [1, 2, 3]
