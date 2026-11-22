"""PyMuPDF and Docling parser fixes from the parser review (#147, "Also seen").

- PyMuPDFParser closes the PDF when a page raises, so the caller can delete the file
  (on Windows an open file cannot be deleted).
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
