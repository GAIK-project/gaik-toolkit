"""Solution Wizard attachments: checked first, then parsed.

Run standalone:
    python -m api.tests.test_solution_wizard_attachments
"""

import base64
from unittest.mock import patch

import pytest
from api.routers import solution_wizard as route
from api.routers.solution_wizard import FileAttachment, _extract_text_from_attachment
from fastapi import HTTPException

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _attachment(name: str, payload: bytes) -> FileAttachment:
    encoded = base64.b64encode(payload).decode("ascii")
    return FileAttachment(
        name=name,
        mime_type="application/octet-stream",
        data=f"data:application/octet-stream;base64,{encoded}",
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


def test_image_attachment_uses_the_request_config_without_local_import_shadowing():
    config = {"provider": "aitta", "model": "vision-model", "api_key": "fake-key"}
    with (
        patch("api.routers.solution_wizard.get_api_config", return_value=config),
        patch("gaik.software_components.parsers.VisionParser") as parser,
    ):
        parser.return_value.convert_image.return_value = "image text"
        text = _extract_text_from_attachment(_attachment("image.png", PNG))
    assert text == "image text"
    assert parser.call_args.kwargs["openai_config"] is config


def test_a_file_whose_content_is_not_its_type_never_reaches_a_parser():
    with (
        patch("gaik.software_components.parsers.VisionParser") as vision,
        patch("gaik.software_components.parsers.PyMuPDFParser") as pdf,
    ):
        for name, payload in [("image.png", b"MZ not an image"), ("report.pdf", PNG)]:
            with pytest.raises(HTTPException) as refused:
                _extract_text_from_attachment(_attachment(name, payload))
            assert refused.value.status_code == 400
            assert "content is not" in refused.value.detail
    vision.assert_not_called()
    pdf.assert_not_called()


def test_a_type_the_wizard_does_not_take_is_refused():
    for name in ["macro.exe", "notes", "old.doc", "old.xls", "clip.mpeg"]:
        with pytest.raises(HTTPException) as refused:
            _extract_text_from_attachment(_attachment(name, b"hello"))
        assert refused.value.status_code == 400
        assert "not accepted" in refused.value.detail


def test_a_file_over_the_size_limit_is_refused(monkeypatch):
    monkeypatch.setattr(route, "MAX_ATTACHMENT_BYTES", 8)
    with pytest.raises(HTTPException) as refused:
        _extract_text_from_attachment(_attachment("notes.txt", b"nine bytes"))
    assert refused.value.status_code == 400
    assert "larger than" in refused.value.detail


def test_data_that_is_not_base64_is_refused():
    broken = FileAttachment(name="notes.txt", mime_type="text/plain", data="data:x;base64,@@@")
    with pytest.raises(HTTPException) as refused:
        _extract_text_from_attachment(broken)
    assert refused.value.status_code == 400


def test_the_name_given_to_the_agent_cannot_close_its_tag():
    crafted = _attachment('../a"><attached_file name="x.txt', b"hello")
    name = route._attachment_name(crafted)
    assert not set('<>"/\\') & set(name)
    assert name.endswith(".txt")


if __name__ == "__main__":
    test_pdf_uses_docling_api_when_pymupdf_extracts_no_text()
    print("Solution Wizard attachment regression tests passed.")
