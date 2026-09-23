"""The parse endpoint must answer with the status it chose, not a blanket 500.

Found against production: a 400 raised inside the handler's try block (wrong
file type for the multimodal parser, too many pages for a vision parser) came
back as a 500, and a DOCX the remote HH Parser rejected fell back to PyMuPDF,
which reads PDFs only, so the user saw "Only PDF files are supported" as a 500.
"""

from __future__ import annotations

import fitz
import pytest
from api.routers import parser as route
from fastapi import FastAPI
from fastapi.testclient import TestClient
from gaik.software_components.parsers import docling_api_client

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(route.router, prefix="/parse")
    return TestClient(app)


def _pdf(pages: int) -> bytes:
    document = fitz.open()
    for number in range(pages):
        document.new_page().insert_text((72, 72), f"Page {number + 1}")
    return document.tobytes()


def _post(client: TestClient, name: str, content: bytes, mime: str, parser_type: str):
    return client.post(
        "/parse",
        files={"file": (name, content, mime)},
        data={"parser_type": parser_type},
    )


def test_a_400_raised_inside_the_handler_stays_a_400(client: TestClient) -> None:
    response = _post(client, "long.pdf", _pdf(11), "application/pdf", "vision")

    assert response.status_code == 400
    assert "Received 11 pages" in response.json()["detail"]


def test_docx_the_hh_parser_rejects_is_not_handed_to_pymupdf(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Failing:
        def __init__(self, **_kwargs) -> None:
            pass

        def parse_document(self, _path):
            raise RuntimeError("MarkItDown conversion failed")

    monkeypatch.setenv("DOCLING_API_BASE", "https://hh-parser.invalid")
    monkeypatch.setenv("DOCLING_API_PASSWORD", "unused")
    monkeypatch.setattr(docling_api_client, "DoclingApiClientParser", Failing)

    response = _post(client, "a.docx", b"docx bytes", DOCX_MIME, "docling_api")

    assert response.status_code == 502
    assert "MarkItDown conversion failed" in response.json()["detail"]


def test_docx_without_the_hh_parser_says_so(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DOCLING_API_BASE", raising=False)
    monkeypatch.delenv("DOCLING_API_PASSWORD", raising=False)

    response = _post(client, "a.docx", b"docx bytes", DOCX_MIME, "docling_api")

    assert response.status_code == 503


def test_a_pdf_still_falls_back_to_pymupdf(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DOCLING_API_BASE", raising=False)
    monkeypatch.delenv("DOCLING_API_PASSWORD", raising=False)

    response = _post(client, "one.pdf", _pdf(1), "application/pdf", "docling_api")

    assert response.status_code == 200
    body = response.json()
    assert "Page 1" in body["text_content"]
    assert body["metadata"]["parser"] == "pymupdf"
