"""Regression tests for Solution Wizard file attachment parsing.

Run standalone:
    python -m api.tests.test_solution_wizard_attachments
"""

import base64
from unittest.mock import patch

from api.routers.solution_wizard import FileAttachment, _extract_text_from_attachment


def _attachment(name: str, payload: bytes) -> FileAttachment:
    encoded = base64.b64encode(payload).decode("ascii")
    return FileAttachment(
        name=name,
        mime_type="application/pdf",
        data=f"data:application/pdf;base64,{encoded}",
    )


def test_pdf_uses_docling_api_when_pymupdf_extracts_no_text():
    """Scanned/image PDFs should not reach the agent as empty attachments."""
    with (
        patch.dict(
            "os.environ",
            {"DOCLING_API_BASE": "https://parser.example", "DOCLING_API_PASSWORD": "secret"},
        ),
        patch("gaik.software_components.parsers.PyMuPDFParser") as pymupdf_parser,
        patch(
            "gaik.software_components.parsers.docling_api_client.DoclingApiClientParser"
        ) as docling_parser,
    ):
        pymupdf_parser.return_value.parse_document.return_value = {"text_content": ""}
        docling_parser.return_value.parse_document.return_value = {
            "parsed_markdown": "| Metric | 2022 |\n| --- | --- |\n| Degrees | 1,698 |",
        }

        text = _extract_text_from_attachment(_attachment("hh-report-page-5.pdf", b"%PDF-1.7"))

    assert "Degrees" in text
    assert "1,698" in text


if __name__ == "__main__":
    test_pdf_uses_docling_api_when_pymupdf_extracts_no_text()
    print("Solution Wizard attachment regression tests passed.")
