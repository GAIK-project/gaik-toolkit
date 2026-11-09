"""Model, parser and transcription calls run in a worker thread, not on the event loop.

The API is one process: a blocking call made on the event loop stalls every other
request until it returns. Each test runs a handler on an event loop in this thread and
has the fake component record the thread it was called in.
"""

from __future__ import annotations

import asyncio
import io
import threading
from types import SimpleNamespace

import pytest
from api.routers import diary, pipeline, rag, transcriber
from fastapi import UploadFile
from langchain_core.documents import Document
from pydantic import BaseModel

CONFIG = {"model": "m", "provider": "azure"}


class Schema(BaseModel):
    name: str | None = None


class Threads:
    """Records which thread each named blocking call ran in."""

    def __init__(self) -> None:
        self.seen: dict[str, int] = {}

    def mark(self, name: str) -> None:
        self.seen[name] = threading.get_ident()

    def assert_off_the_loop(self, *names: str) -> None:
        assert set(names) <= set(self.seen), f"not called: {set(names) - set(self.seen)}"
        on_loop = [n for n, thread in self.seen.items() if thread == threading.get_ident()]
        assert not on_loop, f"ran on the event loop: {on_loop}"


@pytest.fixture
def threads() -> Threads:
    return Threads()


def _upload(name: str, content: bytes) -> UploadFile:
    return UploadFile(io.BytesIO(content), filename=name)


async def _events(response) -> str:
    return "".join([chunk async for chunk in response.body_iterator])


def _fake_extraction(monkeypatch, module, threads: Threads) -> None:
    """Schema and extraction fakes shared by the pipeline and diary routes."""

    def schema(**kwargs):
        threads.mark("schema")
        return Schema, [], False

    class Extractor:
        def __init__(self, **kwargs):
            pass

        def extract(self, **kwargs):
            threads.mark("extract")
            return [{"name": "x"}]

    monkeypatch.setattr(module, "_get_or_create_schema", schema)
    monkeypatch.setattr(module, "get_api_config", lambda: CONFIG)
    monkeypatch.setattr(module, "get_model_options", lambda config: {})
    monkeypatch.setattr("gaik.software_components.extractor.DataExtractor", Extractor)
    monkeypatch.setattr("gaik.software_components.extractor.extractor.DataExtractor", Extractor)
    monkeypatch.setattr(
        "gaik.software_components.extractor.schema.print_pydantic_schema", lambda *a, **k: None
    )


def _fake_transcriber(monkeypatch, threads: Threads) -> None:
    class Transcriber:
        def __init__(self, **kwargs):
            pass

        def transcribe(self, file_path, custom_context=""):
            threads.mark("transcribe")
            return SimpleNamespace(
                raw_transcript="Hei",
                enhanced_transcript=None,
                job_id="job-1",
                segments=None,
                srt_content=None,
                vtt_content=None,
                duration_s=1.0,
                audio_duration_s=1.0,
                usage={},
            )

    monkeypatch.setattr("gaik.software_components.transcriber.Transcriber", Transcriber)


def test_transcribe(monkeypatch, threads) -> None:
    _fake_transcriber(monkeypatch, threads)
    monkeypatch.setenv("AZURE_API_KEY", "key")
    monkeypatch.setattr(
        "gaik.software_components.transcriber.get_openai_config",
        lambda use_azure=True: {"transcription_model": "cloud-model"},
    )

    response = asyncio.run(
        transcriber.transcribe_audio(
            file=_upload("a.mp3", b"ID3audio"),
            custom_context="",
            enhanced=False,
            compress_audio=True,
            language="auto",
            diarization=False,
            speaker_count=None,
            min_speakers=None,
            max_speakers=None,
            initial_prompt=None,
            prefer_local_first=False,
            fix_transcription_errors=False,
            enhanced_transcript_instructions=None,
        )
    )

    assert response.raw_transcript == "Hei"
    assert response.transcription_model == "cloud-model"
    threads.assert_off_the_loop("transcribe")


def test_pipeline_text(monkeypatch, threads) -> None:
    _fake_extraction(monkeypatch, pipeline, threads)
    monkeypatch.setattr(pipeline, "field_name_mapping", lambda model, requirements: {})

    response = asyncio.run(
        pipeline.text_pipeline(
            text="Some text",
            user_requirements="name",
            generate_pdf=False,
            pdf_title="Report",
            schema_key=None,
            regenerate_schema=False,
        )
    )

    assert response.error is None
    assert response.extracted_data == [{"name": "x"}]
    threads.assert_off_the_loop("schema", "extract")


def test_pipeline_document(monkeypatch, threads) -> None:
    _fake_extraction(monkeypatch, pipeline, threads)
    monkeypatch.setattr(pipeline, "field_name_mapping", lambda model, requirements: {})

    def parse(tmp_path, suffix, parser_type, config):
        threads.mark("parse")
        return "parsed text"

    monkeypatch.setattr(pipeline, "_parse_document_content", parse)

    response = asyncio.run(
        pipeline.document_pipeline(
            file=_upload("a.pdf", b"%PDF-1.7\n"),
            user_requirements="name",
            parser_type="pymupdf",
            generate_pdf=False,
            pdf_title="Report",
            schema_key=None,
            regenerate_schema=False,
        )
    )

    assert response.error is None
    assert response.parsed_content == "parsed text"
    threads.assert_off_the_loop("schema", "parse", "extract")


def test_pipeline_audio(monkeypatch, threads) -> None:
    class AudioToStructuredData:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            threads.mark("run")
            return SimpleNamespace(
                extracted_fields=[{"name": "x"}],
                transcription=SimpleNamespace(raw_transcript="Hei", enhanced_transcript=None),
            )

    monkeypatch.setattr(pipeline, "get_api_config", lambda: CONFIG)
    monkeypatch.setattr(
        "gaik.software_modules.audio_to_structured_data.AudioToStructuredData",
        AudioToStructuredData,
    )

    response = asyncio.run(
        pipeline.audio_pipeline(
            file=_upload("a.mp3", b"ID3audio"),
            user_requirements="name",
            generate_pdf=False,
            pdf_title="Report",
            enhanced=False,
            compress_audio=True,
            schema_key=None,
            regenerate_schema=False,
        )
    )

    assert response.error is None
    assert response.raw_transcript == "Hei"
    threads.assert_off_the_loop("run")


def test_diary_text_stream(monkeypatch, threads) -> None:
    _fake_extraction(monkeypatch, diary, threads)

    async def run() -> str:
        response = await diary.diary_text_pipeline_stream(
            text="Tänään valettiin laatta.",
            user_requirements="name",
            generate_pdf=False,
            regenerate_schema=False,
        )
        return await _events(response)

    events = asyncio.run(run())

    assert "event: result" in events
    threads.assert_off_the_loop("schema", "extract")


def test_diary_audio_stream(monkeypatch, threads) -> None:
    _fake_extraction(monkeypatch, diary, threads)
    _fake_transcriber(monkeypatch, threads)

    async def run() -> str:
        response = await diary.diary_audio_pipeline_stream(
            file=_upload("a.mp3", b"ID3audio"),
            user_requirements="name",
            generate_pdf=False,
            enhanced=False,
            compress_audio=True,
            regenerate_schema=False,
        )
        return await _events(response)

    events = asyncio.run(run())

    assert "event: result" in events
    threads.assert_off_the_loop("transcribe", "schema", "extract")


class _Workflow:
    """A RAG workflow whose every blocking part records its thread."""

    api_config = CONFIG

    def __init__(self, threads: Threads) -> None:
        document = Document(
            page_content="text", metadata={"document_name": "doc", "page_number": 1}
        )

        def index(chunks):
            threads.mark("embed")
            return len(chunks)

        def ask(question, *, top_k=None, stream=None):
            threads.mark("ask")
            return SimpleNamespace(answer="An answer", documents=[document])

        def embed_query(question):
            threads.mark("embed_query")
            return [0.0]

        def search(embedding, top_k=None, filters=None):
            threads.mark("search")
            return [(document, 0.9)]

        def generate(question, documents, stream=None):
            threads.mark("generate")
            for chunk in ("An ", "answer"):
                threads.mark(f"chunk {chunk.strip()}")
                yield chunk

        self.index_chunk_documents = index
        self.ask = ask
        self.embedder = SimpleNamespace(embed_query=embed_query)
        self.vector_store = SimpleNamespace(search=search)
        self.answer_generator = SimpleNamespace(generate=generate)


@pytest.fixture
def workflow(monkeypatch, threads) -> _Workflow:
    monkeypatch.setattr(rag, "RAG_INSTANCES", {})
    monkeypatch.setattr(rag, "_USAGE", {})
    monkeypatch.setattr(rag, "_collection_locks", {})
    return _Workflow(threads)


def test_rag_index(monkeypatch, threads, workflow) -> None:
    def parse(path, *, document_name, parser_choice, config):
        threads.mark("parse")
        return [Document(page_content="text", metadata={})] * 2, parser_choice

    monkeypatch.setattr(rag, "get_api_config", lambda: CONFIG)
    monkeypatch.setattr(rag, "_build_demo_workflow", lambda config, collection_id: workflow)
    monkeypatch.setattr(rag, "_parse_document_to_chunks", parse)
    pdf = (rag.EXAMPLE_DIR / rag.EXAMPLE_DOCUMENTS[0]["filename"]).read_bytes()

    response = asyncio.run(
        rag.index_documents(
            files=[_upload("handbook.pdf", pdf)], collection_id=None, parser_choice="pymupdf"
        )
    )

    assert response.status == "success"
    assert response.chunk_count == 2
    threads.assert_off_the_loop("parse", "embed")


def test_rag_query(threads, workflow) -> None:
    rag.RAG_INSTANCES["c1"] = workflow

    response = asyncio.run(rag.query_rag(question="What?", collection_id="c1", top_k=5))

    assert response.answer == "An answer"
    threads.assert_off_the_loop("ask")


def test_rag_query_stream(threads, workflow) -> None:
    rag.RAG_INSTANCES["c1"] = workflow

    async def run() -> str:
        response = await rag.query_rag_stream(question="What?", collection_id="c1", top_k=5)
        return await _events(response)

    events = asyncio.run(run())

    assert '"answer": "An answer"' in events
    threads.assert_off_the_loop("embed_query", "search", "generate", "chunk An", "chunk answer")
    # The stream is over: the collection is no longer marked as in use.
    assert not rag._is_busy("c1")
