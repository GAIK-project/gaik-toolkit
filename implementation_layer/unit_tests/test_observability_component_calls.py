"""Each component's direct model call, traced at its real call site.

Every case builds the component for real and swaps its SDK client (or the
HTTP call) for a fake that records the request it gets and answers like the
SDK, or raises. Each case runs four ways: with tracing on (one span per call,
named after the component, lengths and tokens only), with the call failing
(the same exception object, only its type on the span), with tracing off, and
without the ``gaik[otel]`` extra (the same request and result, no spans). The
request the component sends is pinned in every run. No network.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import ANY

import pytest
from gaik.observability import tracing
from gaik.software_components.llm.base import ChatResponse
from gaik.software_components.llm.traced_client import TracedProviderClient
from pydantic import BaseModel

from . import test_observability_llm_client as client_tests
from . import test_observability_tracing as tracing_tests

spans = tracing_tests.spans
SECRET, ANSWER, _assert_clean = client_tests.SECRET, client_tests.ANSWER, client_tests._assert_clean
MESSAGES = client_tests.MESSAGES
SRT = "1\n00:00:00,000 --> 00:00:01,000\nhei\n"
JSON_ANSWER = '{"total": "12"}'


def _ns(**kwargs):
    return SimpleNamespace(**kwargs)


class _Calls(list):
    """The requests a fake received: its keyword arguments, and ``args`` if any."""

    def record(self, *args, **kwargs):
        self.append({"args": args, **kwargs} if args else dict(kwargs))


def _answering(calls, response, error):
    """A fake SDK method: records the request, then returns ``response`` or raises ``error``."""

    def method(*args, **kwargs):
        calls.record(*args, **kwargs)
        if error is not None:
            raise error
        return response

    return method


def _completion(content=ANSWER, parsed=None):
    usage = client_tests._Usage(prompt_tokens=100, completion_tokens=20, total_tokens=120)
    message = _ns(content=content, parsed=parsed)
    return _ns(choices=[_ns(message=message)], usage=usage, model="gpt-4.1-2025-04-14")


def _raw_openai(calls, response, error):
    """An ``OpenAI`` stand-in for chat completions and structured parsing."""
    method = _answering(calls, response, error)
    return _ns(
        chat=_ns(completions=_ns(create=method)),
        beta=_ns(chat=_ns(completions=_ns(parse=method))),
    )


class _Audio:
    """An ``OpenAI`` stand-in for audio transcription."""

    def __init__(self, calls, response, error):
        self.audio = _ns(transcriptions=_ns(create=_answering(calls, response, error)))

    def close(self):
        pass


class FakeAnthropic:
    """An ``Anthropic`` stand-in: ``messages.create`` and ``messages.stream``."""

    def __init__(self, calls, message, error):
        create = _answering(calls, message, error)

        @contextmanager
        def stream(**kwargs):
            calls.record(**kwargs)
            if error is not None:
                raise error
            yield _ns(get_final_message=lambda: message)

        self.messages = _ns(create=create, stream=stream)


def _provider_client(error, result):
    """A ``ProviderClient`` as ``create_llm_client`` returns it with tracing on."""
    fake = client_tests._FakeProvider(result=result, error=error)
    return fake, TracedProviderClient(fake)


def _chat_response(text=ANSWER):
    usage = {"prompt_tokens": 10, "completion_tokens": 2}
    return ChatResponse(text=text, model="gpt-4.1", provider="openai", usage=usage)


def _file(tmp_path, name, data=b"fake"):
    path = tmp_path / name
    path.write_bytes(data)
    return path


# -- the cases ------------------------------------------------------------------
#
# Each returns (run, expected): ``run()`` makes the component's call, and
# ``expected`` says what its spans hold and which requests reach the fake
# (``calls``, compared with ``requests``).


def _transcript_enhancer(mp, tmp_path, error):
    from gaik.software_components.enhance_transcript import TranscriptEnhancer

    calls = _Calls()
    enhancer = TranscriptEnhancer(
        api_config={"provider": "openai", "api_key": "test-key", "model": "gpt-4.1"}
    )
    enhancer.client = _raw_openai(calls, _completion(), error)
    run = lambda: enhancer._chat_text(MESSAGES, fallback="fallback")  # noqa: E731
    return run, {
        "component": "TranscriptEnhancer",
        "input_tokens": 100,
        "lengths": (client_tests.INPUT_LENGTH, len(ANSWER)),
        "settings": {"gen_ai.request.temperature": 0.0},
        "calls": calls,
        "requests": [{"model": "gpt-4.1", "messages": MESSAGES, "temperature": 0.0}],
    }


def _schema_generator(mp, tmp_path, error):
    from gaik.software_components.extractor import schema
    from gaik.software_components.extractor.schema import StructureAnalysis

    calls = _Calls()
    parsed = StructureAnalysis(
        structure_type="flat",
        parent_container_name="records",
        parent_description="d",
        item_description="i",
        reasoning="r",
    )
    client = _raw_openai(calls, _completion(parsed=parsed), error)
    run = lambda: schema.detect_structure_type(SECRET, client=client, model="gpt-4.1")  # noqa: E731
    return run, {
        "component": "SchemaGenerator",
        "input_tokens": 100,
        "settings": {"gen_ai.request.temperature": 0.0, "gen_ai.request.top_p": 1.0},
        "calls": calls,
        "requests": [
            {
                "model": "gpt-4.1",
                "messages": ANY,
                "response_format": StructureAnalysis,
                "timeout": 30,
                "top_p": 1.0,
                "temperature": 0.0,
            }
        ],
    }


def _form_understander(mp, tmp_path, error):
    from gaik.software_components.form_understander import FormUnderstander, understander
    from gaik.software_components.form_understander.understander import LabelMapping

    calls = _Calls()
    mapping = LabelMapping.model_validate({"entries": [{"id": "a", "label": "Nimi"}]})
    client = _raw_openai(calls, _completion(parsed=mapping), error)
    mp.setattr(understander, "build_compat_client", lambda config: client)
    form = FormUnderstander({"use_azure": False, "model": "gpt-4.1"})
    run = lambda: form.clean_labels([{"id": "a", "raw": SECRET}])  # noqa: E731
    return run, {
        "component": "FormUnderstander",
        "input_tokens": 100,
        "calls": calls,
        "requests": [
            {
                "model": "gpt-4.1",
                "messages": ANY,
                "response_format": LabelMapping,
                "temperature": 0,
                "top_p": 1.0,
                "timeout": 30,
            }
        ],
    }


def _whisper_request(model="whisper-1"):
    return {
        "model": model,
        "file": ANY,
        "response_format": "srt",
        "language": "fi",
        "prompt": SECRET,
    }


def _parallel_transcriber_instance(mp, calls, error, **config):
    from gaik.software_components.parallel_transcriber import pipeline
    from gaik.software_components.parallel_transcriber.config import TranscriptionConfig

    settings = {
        "max_retries": 0,
        "max_429_retries": 0,
        "retry_base_delay_seconds": 0,
        "language": "fi",
        "prompt": SECRET,
        **config,
    }
    api_config = {"use_azure": False, "api_key": "test-key", "transcription_model": "whisper-1"}
    if settings.get("model") == "whisper_local":
        api_config = {"api_base": "http://whisper.test", "key": "test-key"}
    elif settings.get("model") == "gpt-4o-transcribe-diarize":
        api_config = {
            "provider": "azure",
            "use_azure": True,
            "api_key": "test-key",
            "azure_endpoint": "https://audio.test",
            "api_version": "2025-03-01-preview",
        }
    transcriber = pipeline.ParallelTranscriber(api_config, TranscriptionConfig(**settings))
    mp.setattr(transcriber, "_make_whisper_client", lambda: _Audio(calls, SRT, error))
    return transcriber


def _parallel_transcriber(mp, tmp_path, error):
    calls = _Calls()
    transcriber = _parallel_transcriber_instance(mp, calls, error)
    chunks = [str(_file(tmp_path, f"chunk_{i}.mp3")) for i in range(3)]
    run = lambda: transcriber._transcribe_chunks_whisper(chunks, None, 3, None, None)  # noqa: E731
    # One span per chunk, each opened in its worker thread.
    return run, {
        "component": "ParallelTranscriber",
        "spans": 3,
        "operation": "transcription",
        "lengths": (len(SECRET), len(SRT)),
        "calls": calls,
        "requests": [_whisper_request()] * 3,
    }


def _parallel_transcriber_single(mp, tmp_path, error):
    calls = _Calls()
    transcriber = _parallel_transcriber_instance(mp, calls, error)
    audio = _file(tmp_path, "talk.mp3")
    run = lambda: transcriber._call_whisper_single(audio)  # noqa: E731
    return run, {
        "component": "ParallelTranscriber",
        "operation": "transcription",
        "lengths": (len(SECRET), len(SRT)),
        "calls": calls,
        "requests": [_whisper_request()],
    }


def _parallel_transcriber_gpt4o(mp, tmp_path, error):
    import httpx

    calls = _Calls()
    transcriber = _parallel_transcriber_instance(
        mp, calls, error, model="gpt-4o-transcribe-diarize"
    )
    payload = {
        "text": ANSWER,
        "segments": [],
        "usage": {"type": "tokens", "input_tokens": 70, "output_tokens": 15},
    }
    response = _ns(status_code=200, json=lambda: payload, headers={}, text="")
    mp.setattr(httpx, "post", _answering(calls, response, error))
    audio = _file(tmp_path, "talk.mp3")
    run = lambda: transcriber._call_gpt4o_api(str(audio))  # noqa: E731
    url = (
        "https://audio.test/openai/deployments/gpt-4o-transcribe"
        "/audio/transcriptions?api-version=2025-03-01-preview"
    )
    return run, {
        "component": "ParallelTranscriber",
        "operation": "transcription",
        "provider": "azure.ai.openai",
        "input_tokens": 70,
        "calls": calls,
        "requests": [
            {
                "args": (url,),
                "headers": {"api-key": "test-key"},
                "files": ANY,
                "data": {
                    "model": "gpt-4o-transcribe",
                    "response_format": "diarized_json",
                    "chunking_strategy": "auto",
                    "language": "fi",
                },
                "timeout": 600.0,
            }
        ],
    }


def _parallel_transcriber_local(mp, tmp_path, error):
    import requests

    calls = _Calls()
    transcriber = _parallel_transcriber_instance(mp, calls, error, model="whisper_local")
    response = _ns(raise_for_status=lambda: None, json=lambda: {"text": ANSWER, "segments": []})
    mp.setattr(requests, "post", _answering(calls, response, error))
    audio = _file(tmp_path, "talk.mp3")
    run = lambda: transcriber._call_whisper_local_api(str(audio))  # noqa: E731
    return run, {
        "component": "ParallelTranscriber",
        "operation": "transcription",
        "provider": "whisper_local",
        "lengths": (len(SECRET), len(ANSWER)),
        "calls": calls,
        "requests": [
            {
                "args": ("http://whisper.test/transcribe",),
                "data": {
                    "language": "fi",
                    "diarization": False,
                    "include_words": True,
                    "initial_prompt": SECRET,
                },
                "files": ANY,
                "headers": {"key": "test-key"},
                "timeout": 1800,
            }
        ],
    }


def _vision_parser(mp, tmp_path, error):
    from gaik.software_components.parsers.vision import OpenAIConfig, VisionParser

    calls = _Calls()
    client = _raw_openai(calls, _completion(), error)
    mp.setattr(VisionParser, "_initialize_client", lambda self: client)
    parser = VisionParser(OpenAIConfig(model="gpt-4.1", use_azure=False, api_key="test-key"))
    run = lambda: parser._chat_content(MESSAGES)  # noqa: E731
    return run, {
        "component": "VisionParser",
        "input_tokens": 100,
        "lengths": (client_tests.INPUT_LENGTH, len(ANSWER)),
        "settings": {"gen_ai.request.max_tokens": 16_000},
        "calls": calls,
        "requests": [
            {
                "model": "gpt-4.1",
                "messages": MESSAGES,
                "max_completion_tokens": 16_000,
                "temperature": 0.0,
            }
        ],
    }


def _postgres_agent(mp, tmp_path, error, *, answer=False):
    pytest.importorskip("psycopg")
    pytest.importorskip("sqlglot")
    from gaik.software_components.postgres_agent.agent import PostgresAgent
    from gaik.software_components.postgres_agent.models import (
        GeneratedSQL,
        QueryResult,
        SchemaInfo,
        TableInfo,
    )

    calls = _Calls()
    agent = PostgresAgent("postgresql://stub:stub@localhost:1/stub", model="gpt-4.1")
    agent._schema = SchemaInfo(schema_name="public", tables=[TableInfo(name="t", columns=[])])
    parsed = GeneratedSQL(sql="SELECT 1", reasoning="stub")
    agent._llm_client = _raw_openai(calls, _completion(parsed=parsed), error)
    if answer:
        result = QueryResult(question=SECRET, sql="SELECT 1", rows=[{"n": 1}], row_count=1)
        run = lambda: agent._synthesize_answer(SECRET, result)  # noqa: E731
        request = {"model": "gpt-4.1", "messages": ANY, "temperature": 0.0}
    else:
        run = lambda: agent.generate_sql(SECRET)  # noqa: E731
        request = {
            "model": "gpt-4.1",
            "messages": ANY,
            "response_format": GeneratedSQL,
            "temperature": 0.0,
            "timeout": 30,
        }
    return run, {
        "component": "PostgresAgent",
        "input_tokens": 100,
        "calls": calls,
        "requests": [request],
    }


def _tabular_agent_answer(mp, tmp_path, error):
    pytest.importorskip("duckdb")
    from gaik.software_components.tabular_agent.agent import TabularAgent
    from gaik.software_components.tabular_agent.models import QueryResult

    calls = _Calls()
    csv = _file(tmp_path, "sales.csv", b"region,total\nnorth,1\n")
    agent = TabularAgent(csv, model="gpt-4.1")
    agent._llm_client = _raw_openai(calls, _completion(), error)
    result = QueryResult(question=SECRET, sql="SELECT 1", rows=[{"n": 1}], row_count=1)
    run = lambda: agent._synthesize_answer(SECRET, result)  # noqa: E731
    return run, {
        "component": "TabularAgent",
        "input_tokens": 100,
        "lengths": (ANY, len(ANSWER)),
        "calls": calls,
        "requests": [{"model": "gpt-4.1", "messages": ANY, "temperature": 0.0}],
    }


def _text_to_speech(mp, tmp_path, error):
    from gaik.software_components.text_to_speech import TextToSpeech

    calls = _Calls()

    @contextmanager
    def create(**kwargs):
        calls.record(**kwargs)
        if error is not None:
            raise error
        yield _ns(iter_bytes=lambda: iter([b"aud", b"io"]))

    tts = TextToSpeech(api_config={"use_azure": False, "api_key": "test-key"}, language="en")
    tts.client = _ns(audio=_ns(speech=_ns(with_streaming_response=_ns(create=create))))
    run = lambda: tts.synthesize(SECRET, voice="nova", speed=1.25).audio_bytes  # noqa: E731
    return run, {
        "component": "TextToSpeech",
        "operation": "text_to_speech",
        "lengths": (len(SECRET), None),
        "calls": calls,
        "requests": [
            {
                "model": tts.model,
                "voice": "nova",
                "input": SECRET,
                "instructions": ANY,
                "response_format": tts.response_format,
                "speed": 1.25,
            }
        ],
    }


def _transcription_response():
    usage = _ns(type="tokens", input_tokens=70, output_tokens=15, total_tokens=85)
    return _ns(text=ANSWER, usage=usage)


def _transcriber(mp, tmp_path, error):
    from gaik.software_components.transcriber import transcriber as module

    calls = _Calls()
    client = _Audio(calls, _transcription_response(), error)
    mp.setattr(module, "_create_audio_client", lambda config: client)
    instance = object.__new__(module.Transcriber)
    instance.api_config = {"provider": "openai", "api_key": "test-key"}
    audio = _file(tmp_path, "talk.mp3")
    run = lambda: instance._single_pass_transcription(audio, SECRET, "gpt-4o-transcribe")  # noqa: E731
    return run, {
        "component": "Transcriber",
        "input_tokens": 70,
        "operation": "transcription",
        "lengths": (len(SECRET), len(ANSWER)),
        "calls": calls,
        "requests": [{"model": "gpt-4o-transcribe", "file": ANY, "prompt": SECRET}],
    }


class _FakeAudio:
    """A pydub ``AudioSegment`` stand-in: 2 s long, exports any slice as bytes."""

    def __len__(self):
        return 2000

    def __getitem__(self, item):
        return _ns(export=lambda path, format: open(path, "wb").write(b"audio"))


def _transcriber_chunked(mp, tmp_path, error):
    from gaik.software_components.transcriber import transcriber as module

    calls = _Calls()
    client = _Audio(calls, _transcription_response(), error)
    mp.setattr(module, "_create_audio_client", lambda config: client)
    mp.setattr(module.time, "sleep", lambda seconds: None)
    audio = _file(tmp_path, "talk.mp3")

    def run():
        return module.split_and_transcribe_with_context(
            str(audio),
            {"provider": "openai", "api_key": "test-key"},
            max_duration_seconds=1,  # three chunks of the 2 s fake
            audio=_FakeAudio(),
            base_prompt=SECRET,
            transcription_model="gpt-4o-transcribe",
        )

    first = {"model": "gpt-4o-transcribe", "file": ANY, "prompt": SECRET}
    # Later chunks carry the end of the previous transcript as their prompt.
    later = {"model": "gpt-4o-transcribe", "file": ANY, "prompt": ANY}
    # A failed chunk is marked in the transcript, not raised.
    return run, {
        "component": "Transcriber",
        "spans": 3,
        "swallows": True,
        "operation": "transcription",
        "calls": calls,
        "requests": [first, later, later],
    }


def _whisper_local(mp, tmp_path, error):
    from gaik.software_components.transcriber import whisper_local

    calls = _Calls()
    response = _ns(raise_for_status=lambda: None, json=lambda: {"text": ANSWER, "segments": []})
    mp.setattr(whisper_local.requests, "post", _answering(calls, response, error))
    # The health check before the request is not traced.
    mp.setattr(
        whisper_local.requests,
        "get",
        lambda *a, **k: _ns(raise_for_status=lambda: None, json=lambda: {}),
    )
    audio = _file(tmp_path, "talk.mp3")

    def run():
        return whisper_local.transcribe(
            audio, api_base="http://whisper.test", key="test-key", initial_prompt=SECRET
        )

    return run, {
        "component": "Transcriber",
        "operation": "transcription",
        "provider": "whisper_local",
        "lengths": (len(SECRET), None),
        "calls": calls,
        "requests": [
            {
                "args": ("http://whisper.test/transcribe",),
                "data": {
                    "language": "auto",
                    "diarization": False,
                    "min_speakers": None,
                    "max_speakers": None,
                    "speaker_count": None,
                    "initial_prompt": SECRET,
                    "include_words": True,
                },
                "files": ANY,
                "headers": {"key": "test-key"},
                "timeout": 1800,
            }
        ],
    }


class _Invoice(BaseModel):
    total: str


def _claude_request(model, **extra):
    return {
        "model": model,
        "max_tokens": 32768,
        "system": "system",
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "low"},
        **extra,
        "messages": ANY,
    }


def _vision_extractor(provider):
    def case(mp, tmp_path, error):
        from gaik.software_components import llm as llm_package
        from gaik.software_components.vision_extractor import vision_extractor as module

        calls = _Calls()
        page = _file(tmp_path, "page.png", b"\x89PNG fake")
        extractor = object.__new__(module.VisionExtractor)
        extractor.reasoning_effort = "low"
        expected = {"component": "VisionExtractor", "calls": calls}

        if provider == "openai":
            extractor.config = {"model": "m"}
            extractor.model = "gpt-5.4"
            usage = _ns(
                input_tokens=500, output_tokens=90, output_tokens_details=_ns(reasoning_tokens=40)
            )
            response = _ns(output_text=JSON_ANSWER, usage=usage, model="gpt-5.4")
            client = _ns(responses=_ns(create=_answering(calls, response, error)))
            mp.setattr(module, "create_openai_client", lambda config: client)
            call = extractor._call_openai
            expected |= {
                "input_tokens": 500,
                "thinking_tokens": 40,
                "lengths": (len("system") + len(SECRET), len(JSON_ANSWER)),
                "settings": {
                    "gaik.request.reasoning_effort": "low",
                    "gen_ai.request.max_tokens": 32768,
                },
                "requests": [
                    {
                        "model": "gpt-5.4",
                        "instructions": "system",
                        "input": ANY,
                        "reasoning": {"effort": "low"},
                        "text": ANY,
                        "max_output_tokens": 32768,
                    }
                ],
            }
        elif provider == "claude":
            extractor.config = {"model": "m"}
            extractor.model = "claude-sonnet-4-5"
            block = _ns(type="tool_use", name="extract_data", input={"total": "12"})
            usage = _ns(input_tokens=50, output_tokens=20, cache_read_input_tokens=900)
            message = _ns(content=[block], usage=usage, model="claude-sonnet-4-5")
            mp.setattr(
                module, "create_claude_client", lambda c: FakeAnthropic(calls, message, error)
            )
            call = extractor._call_claude
            expected |= {
                "input_tokens": 950,
                "cache_read": 900,
                "provider": "anthropic",
                "lengths": (len("system") + len(SECRET), len(JSON_ANSWER)),
                "requests": [
                    _claude_request("claude-sonnet-4-5", tools=ANY, tool_choice={"type": "auto"})
                ],
            }
        elif provider == "gemini":
            extractor.config = {"vertex_ai": False, "api_key": "test-key"}
            extractor.model = "gemini-2.5-flash"
            payload = {
                "candidates": [{"content": {"parts": [{"text": JSON_ANSWER}]}}],
                "usageMetadata": {"promptTokenCount": 300, "candidatesTokenCount": 40},
            }
            response = _ns(raise_for_status=lambda: None, json=lambda: payload)
            mp.setattr(module.requests, "post", _answering(calls, response, error))
            call = extractor._call_google
            url = (
                "https://generativelanguage.googleapis.com/v1beta/"
                "models/gemini-2.5-flash:generateContent?key=test-key"
            )
            expected |= {
                "input_tokens": 300,
                "provider": "gcp.gemini",
                "settings": {
                    "gen_ai.request.temperature": 0,
                    "gen_ai.request.max_tokens": 32768,
                    "gaik.request.reasoning_effort": "low",
                },
                "requests": [
                    {
                        "args": (url,),
                        "headers": {"Content-Type": "application/json; charset=utf-8"},
                        "json": ANY,
                        "timeout": (30, 300),
                    }
                ],
            }
        else:  # a shared-config ProviderClient
            extractor.config = {"provider": "openai", "model": "gpt-4.1"}
            extractor.model = "gpt-4.1"
            extractor.model_provider = "openai"
            fake, client = _provider_client(error, _Invoice(total="12"))
            mp.setattr(llm_package, "create_llm_client", lambda config: client)
            call = extractor._call_shared
            expected |= {
                # The parsed record, measured as Pydantic's compact JSON.
                "lengths": (ANY, len(_Invoice(total="12").model_dump_json())),
                "calls": fake.calls,
                "requests": [{"response_format": _Invoice, "max_tokens": 32768}],
            }

        run = lambda: call([page], "system", SECRET, _Invoice)[0]  # noqa: E731
        return run, expected

    return case


def _multimodal_parser(provider):
    def case(mp, tmp_path, error):
        from gaik.software_components import llm as llm_package
        from gaik.software_components.parsers.multimodal_parser import multimodal_parser as module

        calls = _Calls()
        parser = object.__new__(module.MultimodalParser)
        parser.reasoning_effort = "low"
        expected = {"component": "MultimodalParser", "calls": calls}

        if provider == "openai":
            parser.config = {"model": "gpt-5.4"}
            usage = _ns(input_tokens=500, output_tokens=90)
            response = _ns(output_text=ANSWER, usage=usage, model="gpt-5.4")
            client = _ns(responses=_ns(create=_answering(calls, response, error)))
            mp.setattr(module, "create_openai_client", lambda config: client)
            call = parser._call_openai
            expected |= {
                "input_tokens": 500,
                "lengths": (len("system") + len(SECRET), len(ANSWER)),
                "requests": [
                    {
                        "model": "gpt-5.4",
                        "instructions": "system",
                        "input": ANY,
                        "reasoning": {"effort": "low"},
                        "max_output_tokens": 32768,
                    }
                ],
            }
        elif provider == "claude":
            parser.config = {"model": "claude-sonnet-4-5"}
            usage = _ns(input_tokens=50, output_tokens=20, cache_creation_input_tokens=30)
            message = _ns(content=[_ns(type="text", text=ANSWER)], usage=usage)
            mp.setattr(
                module, "create_claude_client", lambda c: FakeAnthropic(calls, message, error)
            )
            call = parser._call_claude
            expected |= {
                "input_tokens": 80,
                "provider": "anthropic",
                "lengths": (len("system") + len(SECRET), len(ANSWER)),
                "requests": [_claude_request("claude-sonnet-4-5")],
            }
        else:  # a shared-config ProviderClient
            parser.config = {"provider": "openai", "model": "gpt-4.1"}
            parser.model_provider = "openai"
            fake, client = _provider_client(error, _chat_response())
            mp.setattr(llm_package, "create_llm_client", lambda config: client)
            call = parser._call_shared
            expected |= {
                "lengths": (len("system") + len(SECRET), len(ANSWER)),
                "calls": fake.calls,
                "requests": [{"max_tokens": 32768}],
            }

        document = _file(tmp_path, "page.png", b"\x89PNG fake")
        run = lambda: call(document, "system", SECRET)[0]  # noqa: E731
        return run, expected

    return case


def _llm_judge(provider, *, images=False):
    def case(mp, tmp_path, error):
        from gaik.software_components.parsers.multimodal_parser import config as mm_config
        from gaik.software_components.validators.llm_judge import llm_judge as module

        calls = _Calls()
        expected = {"component": "LLMJudge", "calls": calls}
        if provider == "openai":
            client = _raw_openai(calls, _completion(content=JSON_ANSWER), error)
            mp.setattr(mm_config, "get_openai_config", lambda use_azure: {"model": "gpt-4.1"})
            mp.setattr(mm_config, "create_openai_client", lambda config: client)
            judge = module.LLMJudge(model_provider="openai", use_azure=False, model="gpt-4.1")
            expected |= {
                "provider": "openai",
                "input_tokens": 100,
                "settings": {"gen_ai.request.max_tokens": 4096},
                "requests": [
                    {
                        "model": "gpt-4.1",
                        "messages": ANY,
                        "max_completion_tokens": 4096,
                        "response_format": {"type": "json_object"},
                    }
                ],
            }
        elif provider == "anthropic":
            usage = _ns(input_tokens=50, output_tokens=20)
            message = _ns(content=[_ns(type="text", text=JSON_ANSWER)], usage=usage)
            mp.setattr(mm_config, "get_claude_config", lambda use_azure: {})
            mp.setattr(
                mm_config, "create_claude_client", lambda c: FakeAnthropic(calls, message, error)
            )
            judge = module.LLMJudge(model_provider="anthropic", model="claude-sonnet-4-5")
            expected |= {
                "provider": "anthropic",
                "input_tokens": 50,
                "settings": {"gen_ai.request.max_tokens": 4096},
                "requests": [
                    {
                        "model": "claude-sonnet-4-5",
                        "max_tokens": 4096,
                        "system": "system",
                        "messages": [{"role": "user", "content": SECRET}],
                    }
                ],
            }
        elif provider == "google":
            pytest.importorskip("google.genai")
            from google import genai

            meta = _ns(prompt_token_count=30, candidates_token_count=5)
            response = _ns(text=JSON_ANSWER, usage_metadata=meta)
            client = _ns(models=_ns(generate_content=_answering(calls, response, error)))
            mp.setenv("GOOGLE_GEMINI_API_KEY", "test-key")
            mp.setattr(genai, "Client", lambda **kwargs: client)
            judge = module.LLMJudge(
                model_provider="google", use_vertexai=False, model="gemini-2.5-flash"
            )
            expected |= {
                "provider": "gcp.gemini",
                "input_tokens": 30,
                "settings": {"gen_ai.request.max_tokens": 4096},
                "requests": [{"model": "gemini-2.5-flash", "contents": [SECRET], "config": ANY}],
            }
        else:  # a shared-config ProviderClient
            fake, client = _provider_client(error, _chat_response(JSON_ANSWER))
            mp.setattr(module, "create_llm_client", lambda config: client)
            judge = module.LLMJudge(
                config={"provider": "openai", "model": "gpt-4.1", "api_key": "test-key"}
            )
            expected |= {
                "provider": "openai",
                "calls": fake.calls,
                "requests": [{"model": "gpt-4.1", "max_tokens": 4096}],
            }

        expected["lengths"] = (len("system") + len(SECRET), len(JSON_ANSWER))
        if images:
            run = lambda: judge._dispatch([b"\x89PNG fake"], SECRET, "system")  # noqa: E731
        else:
            run = lambda: judge._dispatch_text(SECRET, "system")  # noqa: E731
        return run, expected

    return case


CASES = {
    "TranscriptEnhancer": _transcript_enhancer,
    "SchemaGenerator": _schema_generator,
    "FormUnderstander": _form_understander,
    "ParallelTranscriber-chunks": _parallel_transcriber,
    "ParallelTranscriber-single": _parallel_transcriber_single,
    "ParallelTranscriber-gpt4o": _parallel_transcriber_gpt4o,
    "ParallelTranscriber-local": _parallel_transcriber_local,
    "VisionParser": _vision_parser,
    "PostgresAgent-sql": _postgres_agent,
    "PostgresAgent-answer": lambda mp, tmp_path, error: _postgres_agent(
        mp, tmp_path, error, answer=True
    ),
    "TabularAgent-answer": _tabular_agent_answer,
    "TextToSpeech": _text_to_speech,
    "Transcriber": _transcriber,
    "Transcriber-chunked": _transcriber_chunked,
    "whisper_local": _whisper_local,
    "VisionExtractor-openai": _vision_extractor("openai"),
    "VisionExtractor-claude": _vision_extractor("claude"),
    "VisionExtractor-gemini": _vision_extractor("gemini"),
    "VisionExtractor-shared": _vision_extractor("shared"),
    "MultimodalParser-openai": _multimodal_parser("openai"),
    "MultimodalParser-claude": _multimodal_parser("claude"),
    "MultimodalParser-shared": _multimodal_parser("shared"),
    "LLMJudge-images": _llm_judge("openai", images=True),
    "LLMJudge-openai": _llm_judge("openai"),
    "LLMJudge-anthropic": _llm_judge("anthropic"),
    "LLMJudge-google": _llm_judge("google"),
    "LLMJudge-shared": _llm_judge("shared"),
}


def _tracing_off(monkeypatch):
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    tracing._reset_for_tests()
    tracing_tests._EXPORTER.clear()


def _without_the_extra(monkeypatch):
    """The OpenTelemetry packages cannot be imported, as without ``gaik[otel]``."""
    for name in list(sys.modules):
        if name == "opentelemetry" or name.startswith("opentelemetry."):
            monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.setitem(sys.modules, "opentelemetry", None)
    tracing._reset_for_tests()
    tracing_tests._EXPORTER.clear()


def _run_failing(case, monkeypatch, tmp_path):
    """Run ``case`` with its call failing: the result, or the exception raised."""
    error = RuntimeError(SECRET)
    run, expected = case(monkeypatch, tmp_path, error)
    if expected.get("swallows"):
        return run(), expected
    with pytest.raises(RuntimeError) as caught:
        run()
    assert caught.value is error
    return None, expected


# -- the runs ------------------------------------------------------------------------


@pytest.mark.parametrize("name", CASES)
def test_each_call_is_a_span_named_after_its_component(name, spans, monkeypatch, tmp_path):
    run, expected = CASES[name](monkeypatch, tmp_path, None)

    run()

    assert expected["calls"] == expected["requests"]
    recorded = spans()
    assert len(recorded) == expected.get("spans", 1)
    for span in recorded:
        attributes = span.attributes
        assert attributes["gaik.component.name"] == expected["component"]
        assert attributes["gen_ai.operation.name"] == expected.get("operation", "chat")
        if "provider" in expected:
            assert attributes["gen_ai.provider.name"] == expected["provider"]
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
    for attribute, value in expected.get("settings", {}).items():
        assert first[attribute] == value
    if "lengths" in expected:
        input_length, output_length = expected["lengths"]
        assert first.get("gaik.input.length") == input_length
        assert first.get("gaik.output.length") == output_length


@pytest.mark.parametrize("name", CASES)
def test_a_failed_call_records_only_the_error_s_type(name, spans, monkeypatch, tmp_path):
    result, expected = _run_failing(CASES[name], monkeypatch, tmp_path)

    if expected.get("swallows"):
        assert "[Transcription failed for segment 1]" in result
    assert expected["calls"] == expected["requests"]
    recorded = spans()
    assert len(recorded) == expected.get("spans", 1)
    for span in recorded:
        assert span.attributes["error.type"] == "builtins.RuntimeError"
        assert span.status.status_code == tracing_tests.trace.StatusCode.ERROR
        _assert_clean(span)


@pytest.mark.parametrize("off", [_tracing_off, _without_the_extra], ids=["disabled", "no-extra"])
@pytest.mark.parametrize("name", CASES)
def test_without_tracing_the_component_behaves_the_same(name, off, spans, monkeypatch, tmp_path):
    run, expected = CASES[name](monkeypatch, tmp_path, None)
    traced = run()
    traced_failure, _ = _run_failing(CASES[name], monkeypatch, tmp_path)

    off(monkeypatch)
    run, expected = CASES[name](monkeypatch, tmp_path, None)
    assert run() == traced
    assert expected["calls"] == expected["requests"]
    failure, expected = _run_failing(CASES[name], monkeypatch, tmp_path)
    assert failure == traced_failure
    assert expected["calls"] == expected["requests"]
    assert not spans()


def test_a_missing_audio_file_makes_no_span(spans, monkeypatch, tmp_path):
    from gaik.software_components.transcriber import transcriber as module

    client = _Audio(_Calls(), _transcription_response(), None)
    monkeypatch.setattr(module, "_create_audio_client", lambda config: client)
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
