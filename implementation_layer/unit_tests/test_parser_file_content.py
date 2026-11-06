"""The PDF and DOCX parsers check a file's content, not only its name."""

from __future__ import annotations

import pytest

pytest.importorskip("fitz")
pytest.importorskip("docx")

import fitz  # noqa: E402
from docx import Document  # noqa: E402
from gaik.software_components.parsers.docx_parser import DocxParser  # noqa: E402
from gaik.software_components.parsers.pymypdf import PyMuPDFParser  # noqa: E402


def _pdf(path, text="Invoice 42"):
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), text)
    doc.save(path)
    doc.close()
    return path


def _docx(path, text="Meeting notes"):
    doc = Document()
    doc.add_paragraph(text)
    doc.save(path)
    return path


def test_pdf_with_pdf_content_is_parsed(tmp_path):
    path = _pdf(tmp_path / "invoice.pdf")
    assert "Invoice 42" in PyMuPDFParser().parse_pdf(str(path))


def test_pdf_marker_may_follow_a_few_leading_bytes(tmp_path):
    source = _pdf(tmp_path / "source.pdf")
    path = tmp_path / "padded.pdf"
    path.write_bytes(b"\n\n" + source.read_bytes())
    assert "Invoice 42" in PyMuPDFParser().parse_pdf(str(path))


def test_other_content_named_pdf_is_rejected(tmp_path):
    path = _docx(tmp_path / "notes.pdf")
    with pytest.raises(ValueError, match="not a PDF document"):
        PyMuPDFParser().parse_pdf(str(path))
    with pytest.raises(ValueError, match="not a PDF document"):
        PyMuPDFParser().parse_document(str(path))


def test_docx_with_docx_content_is_parsed(tmp_path):
    path = _docx(tmp_path / "notes.docx")
    assert "Meeting notes" in DocxParser().parse_docx(str(path))


def test_other_content_named_docx_is_rejected(tmp_path):
    path = _pdf(tmp_path / "invoice.docx")
    with pytest.raises(ValueError, match="not a DOCX document"):
        DocxParser().parse_docx(str(path))
    with pytest.raises(ValueError, match="not a DOCX document"):
        DocxParser().parse_document(str(path))


def test_empty_file_is_rejected(tmp_path):
    pdf = tmp_path / "empty.pdf"
    pdf.write_bytes(b"")
    docx = tmp_path / "empty.docx"
    docx.write_bytes(b"")
    with pytest.raises(ValueError):
        PyMuPDFParser().parse_pdf(str(pdf))
    with pytest.raises(ValueError):
        DocxParser().parse_docx(str(docx))
