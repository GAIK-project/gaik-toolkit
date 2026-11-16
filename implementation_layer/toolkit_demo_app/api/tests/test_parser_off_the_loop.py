"""Every branch of run_parser reads the file in a worker thread, not on the event loop."""

import asyncio
import threading
import time

import pytest
from api.routers import parser

DOCLING = "gaik.software_components.parsers.docling_api_client.DoclingApiClientParser"
PYMUPDF = "gaik.software_components.parsers.PyMuPDFParser"
DOCX = "gaik.software_components.parsers.DocxParser"


@pytest.fixture
def seen(monkeypatch):
    threads: dict[str, int] = {}
    monkeypatch.setattr(parser, "validate_vision_page_limit", lambda *a: None)
    monkeypatch.setenv("DOCLING_API_BASE", "http://docling.invalid")
    monkeypatch.setenv("DOCLING_API_PASSWORD", "placeholder")

    def local(name):
        def parse_document(self, path):
            threads[name] = threading.get_ident()
            return {"text_content": "x", "metadata": {}}

        return parse_document

    monkeypatch.setattr(f"{PYMUPDF}.parse_document", local("pymupdf"))
    monkeypatch.setattr(f"{DOCX}.parse_document", local("docx"))
    return threads


def _assert_off_the_loop(threads, *names):
    assert set(names) <= set(threads), f"not called: {set(names) - set(threads)}"
    assert all(threads[n] != threading.get_ident() for n in names)


@pytest.mark.parametrize(("parser_type", "suffix"), [("pymupdf", ".pdf"), ("docx", ".docx")])
def test_local_parsers_run_off_the_loop(seen, parser_type, suffix):
    asyncio.run(parser.run_parser("f" + suffix, suffix, parser_type))
    _assert_off_the_loop(seen, parser_type)


def test_a_slow_docling_api_parse_leaves_the_loop_free(seen, monkeypatch):
    def parse_document(self, path):
        seen["docling"] = threading.get_ident()
        time.sleep(0.5)
        return {"parsed_markdown": "x"}

    monkeypatch.setattr(f"{DOCLING}.parse_document", parse_document)

    async def main():
        ticks = 0

        async def ticker():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.02)
                ticks += 1

        task = asyncio.create_task(ticker())
        result = await parser.run_parser("f.pdf", ".pdf", "docling_api")
        task.cancel()
        return result, ticks

    result, ticks = asyncio.run(main())
    assert result["text_content"] == "x"
    _assert_off_the_loop(seen, "docling")
    assert ticks >= 5, f"the loop ticked only {ticks} times during the parse"


def test_the_pymupdf_fallback_runs_off_the_loop(seen, monkeypatch):
    def parse_document(self, path):
        seen["docling"] = threading.get_ident()
        raise RuntimeError("service down")

    monkeypatch.setattr(f"{DOCLING}.parse_document", parse_document)
    result = asyncio.run(parser.run_parser("f.pdf", ".pdf", "docling_api"))
    assert result["metadata"]["parser"] == "pymupdf"
    _assert_off_the_loop(seen, "docling", "pymupdf")


def test_the_unconfigured_fallback_runs_off_the_loop(seen, monkeypatch):
    monkeypatch.delenv("DOCLING_API_BASE")
    asyncio.run(parser.run_parser("f.pdf", ".pdf", "docling_api"))
    _assert_off_the_loop(seen, "pymupdf")
