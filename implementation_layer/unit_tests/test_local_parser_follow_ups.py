"""PyMuPDF and Docling parser fixes from the parser review (#147, "Also seen").

- PyMuPDFParser closes the PDF when a page raises, so the caller can delete the file
  (on Windows an open file cannot be deleted).
- DoclingParser and VisionPlusParser accept enable_table_structure=False: Docling refuses
  table_structure_options=None.
- DoclingParser reads the .txt it advertises, and its structured text keeps tables.
"""

from __future__ import annotations

import fitz
import pytest
from gaik.software_components.parsers import pymypdf
from gaik.software_components.parsers.pymypdf import PyMuPDFParser


def _pdf(path, pages=("First page", "Second page")):
    with fitz.open() as document:
        for text in pages:
            document.new_page().insert_text((20, 20), text)
        document.save(path)
    return path


def _record_opened(monkeypatch):
    opened = []
    real_open = fitz.open

    def recording_open(*args, **kwargs):
        document = real_open(*args, **kwargs)
        opened.append(document)
        return document

    monkeypatch.setattr(pymypdf.fitz, "open", recording_open)
    return opened


@pytest.mark.parametrize("use_markdown", [True, False])
def test_pymupdf_closes_the_pdf_when_a_page_raises(monkeypatch, tmp_path, use_markdown):
    path = _pdf(tmp_path / "broken.pdf")
    opened = _record_opened(monkeypatch)

    def failing_get_text(self, *args, **kwargs):
        raise RuntimeError("page cannot be read")

    monkeypatch.setattr(fitz.Page, "get_text", failing_get_text)

    with pytest.raises(RuntimeError, match="page cannot be read"):
        PyMuPDFParser().parse_pdf(str(path), use_markdown=use_markdown)

    assert len(opened) == 1 and opened[0].is_closed
    path.unlink()  # The caller's cleanup works, on Windows too.


def test_pymupdf_closes_the_pdf_over_the_page_limit_and_after_a_read(monkeypatch, tmp_path):
    from gaik.software_components.input_limits import InputLimitError, InputLimits

    path = _pdf(tmp_path / "two.pdf")
    opened = _record_opened(monkeypatch)

    with pytest.raises(InputLimitError):
        PyMuPDFParser(limits=InputLimits(max_pages=1)).parse_pdf(str(path))
    assert "First page" in PyMuPDFParser().parse_pdf(str(path))

    assert len(opened) == 2 and all(document.is_closed for document in opened)


def _docling_parser(**options):
    pytest.importorskip("docling")
    from gaik.software_components.parsers.docling import DoclingParser

    return DoclingParser(enable_ocr=False, enable_formula_enrichment=False, **options)


def test_docling_parser_takes_table_structure_off():
    parser = _docling_parser(enable_table_structure=False)

    assert parser.pipeline_options.do_table_structure is False


def test_vision_plus_parser_takes_table_structure_off():
    pytest.importorskip("docling")
    from gaik.software_components.parsers.visionPlus import VisionPlusParser

    parser = VisionPlusParser(
        vision_config={"model": "gpt-test", "use_azure": False, "api_key": "test"},
        enable_ocr=False,
        enable_table_structure=False,
        verbose=False,
    )

    assert parser.pipeline_options.do_table_structure is False


@pytest.mark.parametrize("use_markdown", [True, False])
@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "cp1252", "utf-16"])
def test_docling_parser_reads_the_txt_it_advertises(tmp_path, use_markdown, encoding):
    parser = _docling_parser()
    path = tmp_path / "notes.txt"
    path.write_bytes("Kokous 3.5.\nPäätös: hyväksytty, 1 200 €\n".encode(encoding))

    assert parser.is_supported_file(str(path))
    result = parser.parse_document(str(path), use_markdown=use_markdown)

    assert result["text_content"] == "Kokous 3.5.\nPäätös: hyväksytty, 1 200 €\n"
    assert result["file_extension"] == ".txt"
    assert result["parsing_method"] == "docling"
    assert result["format_used"] == ("markdown" if use_markdown else "structured")


def test_docling_parser_refuses_undecodable_txt_without_naming_csv_options(tmp_path):
    parser = _docling_parser()
    path = tmp_path / "notes.txt"
    path.write_bytes(b"Notes\n\x81\x8d\n")

    with pytest.raises(ValueError, match="notes.txt: .*save it as UTF-8") as raised:
        parser.parse_document(str(path))
    assert "CSV" not in str(raised.value) and "encoding" not in str(raised.value)


def test_docling_structured_text_keeps_tables_in_reading_order():
    pytest.importorskip("docling")
    from docling_core.types.doc import (
        ContentLayer,
        DocItemLabel,
        DoclingDocument,
        TableCell,
        TableData,
    )
    from gaik.software_components.parsers.docling import DoclingParser

    document = DoclingDocument(name="report")
    document.add_text(label=DocItemLabel.TEXT, text="Before the table")
    rows = [["Item", "Qty"], ["Widget", "12"]]
    cells = [
        TableCell(
            text=text,
            start_row_offset_idx=r,
            end_row_offset_idx=r + 1,
            start_col_offset_idx=c,
            end_col_offset_idx=c + 1,
            column_header=r == 0,
        )
        for r, row in enumerate(rows)
        for c, text in enumerate(row)
    ]
    document.add_table(data=TableData(num_rows=2, num_cols=2, table_cells=cells))
    document.add_text(
        label=DocItemLabel.PAGE_FOOTER, text="Page 1", content_layer=ContentLayer.FURNITURE
    )
    document.add_text(label=DocItemLabel.TEXT, text="After the table")

    text = DoclingParser._extract_structured_text(DoclingParser.__new__(DoclingParser), document)

    before, table, footer, after = text.split("\n\n")
    assert before == "Before the table"
    assert "Widget" in table and "12" in table and table.startswith("| Item")
    # The page footer was in the structured text before, and stays.
    assert (footer, after) == ("Page 1", "After the table")


def test_docling_structured_text_gives_a_table_caption_and_footnote_once():
    pytest.importorskip("docling")
    from docling_core.types.doc import DocItemLabel, DoclingDocument, TableCell, TableData
    from gaik.software_components.parsers.docling import DoclingParser

    document = DoclingDocument(name="prices")
    cell = TableCell(
        text="A",
        start_row_offset_idx=0,
        end_row_offset_idx=1,
        start_col_offset_idx=0,
        end_col_offset_idx=1,
        column_header=True,
    )
    table = document.add_table(data=TableData(num_rows=1, num_cols=1, table_cells=[cell]))
    caption = document.add_text(label=DocItemLabel.CAPTION, text="Table 1: Prices", parent=table)
    table.captions.append(caption.get_ref())
    footnote = document.add_text(label=DocItemLabel.FOOTNOTE, text="Source: shop", parent=table)
    table.footnotes.append(footnote.get_ref())
    document.add_text(label=DocItemLabel.TEXT, text="After")

    text = DoclingParser._extract_structured_text(DoclingParser.__new__(DoclingParser), document)

    assert text.count("Table 1: Prices") == 1
    assert text.count("Source: shop") == 1
    assert text.endswith("After")


def test_docling_rag_parser_takes_table_structure_off():
    pytest.importorskip("docling")
    from gaik.software_components.RAG.rag_parser_docling.parser import DoclingRagParser

    parser = DoclingRagParser(
        enable_ocr=False,
        enable_table_structure=False,
        enable_formula_enrichment=False,
        verbose=False,
    )

    assert parser.pipeline_options.do_table_structure is False


def test_vision_rag_parser_takes_table_structure_off():
    pytest.importorskip("docling")
    from gaik.software_components.RAG.rag_parser_vision.parser import VisionRagParser

    parser = VisionRagParser(
        vision_config={"model": "gpt-test", "use_azure": False, "api_key": "test"},
        enable_ocr=False,
        enable_table_structure=False,
        enable_formula_enrichment=False,
        verbose=False,
    )

    assert parser.pipeline_options.do_table_structure is False
