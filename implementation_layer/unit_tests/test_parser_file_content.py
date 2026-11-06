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


@pytest.mark.parametrize("padding", [2, 3000])
def test_pdf_with_bytes_before_its_header_is_parsed(tmp_path, padding):
    source = _pdf(tmp_path / "source.pdf")
    path = tmp_path / "padded.pdf"
    path.write_bytes(b"\n" * padding + source.read_bytes())
    assert "Invoice 42" in PyMuPDFParser().parse_pdf(str(path))


def test_pdf_without_its_header_line_is_parsed(tmp_path):
    # PyMuPDF repairs such a file, so the parser keeps accepting it.
    data = _pdf(tmp_path / "source.pdf").read_bytes()
    path = tmp_path / "headerless.pdf"
    path.write_bytes(data[data.index(b"\n") + 1 :])
    assert "Invoice 42" in PyMuPDFParser().parse_pdf(str(path))


def test_docx_with_bytes_before_the_container_is_parsed(tmp_path):
    source = _docx(tmp_path / "source.docx")
    path = tmp_path / "padded.docx"
    path.write_bytes(b"junk" * 10 + source.read_bytes())
    assert "Meeting notes" in DocxParser().parse_docx(str(path))


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


def test_unreadable_pdf_keeps_the_library_error(tmp_path):
    # Files PyMuPDF cannot open at all fail as they did before the content check.
    for name, data in [("empty.pdf", b""), ("text.pdf", b"hello world")]:
        path = tmp_path / name
        path.write_bytes(data)
        with pytest.raises(fitz.FileDataError):
            PyMuPDFParser().parse_pdf(str(path))


def test_empty_docx_is_rejected(tmp_path):
    path = tmp_path / "empty.docx"
    path.write_bytes(b"")
    with pytest.raises(ValueError, match="not a DOCX document"):
        DocxParser().parse_docx(str(path))
