"""Offline tests for RAGWorkflow(parser="text") and its TextRagParser.

Documents are built in ``tmp_path``; embeddings are fake, so no test calls an API and
none needs Docling or a vision model.
"""

from __future__ import annotations

import pymupdf
import pytest
from docx import Document as DocxDocument
from gaik.software_modules.RAG_workflow import RAGWorkflow
from gaik.software_modules.RAG_workflow.text_parser import TextRagParser

CONFIG = {"use_azure": False, "api_key": "test", "model": "gpt-test"}
PARAGRAPH = "The GAIK toolkit indexes documents for question answering. " * 4


def _pdf(path, pages: list[str]):
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_textbox(pymupdf.Rect(40, 40, 560, 800), text, fontsize=9)
    doc.save(path)
    doc.close()
    return path


def test_pdf_chunks_keep_page_numbers_and_metadata(tmp_path):
    pdf = _pdf(
        tmp_path / "report.pdf", ["Budget for 2026 is 120 000 euros.", "Owner: Haaga-Helia."]
    )
    chunks = TextRagParser().convert_doc_to_chunks(pdf, document_name="Annual report")

    assert [c.metadata["page_number"] for c in chunks] == [1, 2]
    assert {c.metadata["document_name"] for c in chunks} == {"Annual report"}
    assert [c.metadata["chunk_id"] for c in chunks] == [0, 1]
    assert "120 000 euros" in chunks[0].page_content
    assert chunks[0].metadata["source"].endswith("report.pdf")
    assert chunks[0].metadata["heading"] is None


def test_long_text_is_split_with_overlap_and_nothing_lost(tmp_path):
    words = [f"word{i}." for i in range(900)]
    text = "\n\n".join(" ".join(words[i : i + 30]) for i in range(0, 900, 30))
    source = tmp_path / "notes.md"
    source.write_text(text, encoding="utf-8")

    parser = TextRagParser(chunk_chars=400, overlap_chars=60)
    chunks = parser.convert_doc_to_chunks(source)

    assert len(chunks) > 5
    assert all(len(c.page_content) <= 400 for c in chunks)
    found = " ".join(c.page_content for c in chunks)
    assert all(word in found for word in words)
    # Consecutive chunks share their boundary text.
    first_tail = chunks[0].page_content.split()[-1]
    assert first_tail in chunks[1].page_content
    assert chunks[0].metadata["page_number"] == "Unknown"
    assert chunks[0].metadata["document_name"] == "notes"


def test_one_paragraph_longer_than_a_chunk_is_cut_at_sentences(tmp_path):
    source = tmp_path / "long.txt"
    source.write_text(PARAGRAPH * 10, encoding="utf-8")
    chunks = TextRagParser(chunk_chars=300, overlap_chars=0).convert_doc_to_chunks(source)
    assert all(len(c.page_content) <= 300 for c in chunks)
    assert all(c.page_content.endswith(".") for c in chunks)


def test_docx_paragraphs_and_tables_are_read(tmp_path):
    doc = DocxDocument()
    doc.add_paragraph("Opening hours are from 8 to 16.")
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Campus"
    table.rows[0].cells[1].text = "Pasila"
    path = tmp_path / "guide.docx"
    doc.save(path)

    text = " ".join(c.page_content for c in TextRagParser().convert_doc_to_chunks(path))
    assert "Opening hours" in text and "Campus | Pasila" in text


def test_a_pdf_without_text_points_to_the_vision_parser(tmp_path):
    scan = _pdf(tmp_path / "scan.pdf", ["", ""])
    with pytest.raises(ValueError, match="parser='vision'"):
        TextRagParser().convert_doc_to_chunks(scan)


def test_an_unsupported_file_type_is_an_error(tmp_path):
    slides = tmp_path / "deck.pptx"
    slides.write_bytes(b"x")
    with pytest.raises(ValueError, match="unsupported file type .pptx"):
        TextRagParser().convert_doc_to_chunks(slides)


def test_workflow_indexes_with_the_text_parser_without_a_parser_config(tmp_path, monkeypatch):
    # No parser_config and no api_config: the text parser needs neither, so the
    # workflow must not fall back to the default Azure config.
    def no_default_config(**kwargs):
        raise AssertionError("the text parser must not load a default config")

    monkeypatch.setattr(
        "gaik.software_modules.RAG_workflow.pipeline.get_openai_config", no_default_config
    )
    workflow = RAGWorkflow(
        parser="text",
        embedding_config=CONFIG,
        answer_config=CONFIG,
        persist=False,
        stream=False,
    )
    assert isinstance(workflow.parser, TextRagParser)

    def fake_embed(documents, **kwargs):
        return [[float(i), 1.0] for i in range(len(documents))], list(documents)

    monkeypatch.setattr(workflow.embedder, "embed", fake_embed)
    pdf = _pdf(tmp_path / "a.pdf", ["First page text.", "Second page text."])
    notes = tmp_path / "b.md"
    notes.write_text("Notes about the project.", encoding="utf-8")

    result = workflow.index_documents([pdf, notes], filenames=["Report A", "Notes B"])

    assert result.num_documents == 2 and result.num_chunks == 3
    assert result.vector_store_path is None


def test_an_unknown_parser_is_rejected():
    with pytest.raises(ValueError, match="parser must be 'vision' or 'text'"):
        RAGWorkflow(parser="ocr", embedding_config=CONFIG, answer_config=CONFIG)
