"""The pipeline's PDF download can also be shown inside a page (the incident preview)."""

import asyncio

from api.routers import pipeline


def _download(tmp_path, **kwargs):
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    pipeline.PDF_STORAGE["job-1234"] = pdf
    try:
        return asyncio.run(pipeline.download_pdf("job-1234", **kwargs))
    finally:
        pipeline.PDF_STORAGE.pop("job-1234", None)


def test_the_pdf_downloads_as_an_attachment_by_default(tmp_path):
    response = _download(tmp_path)

    assert response.headers["content-disposition"].startswith("attachment")


def test_the_pdf_can_be_shown_inline(tmp_path):
    response = _download(tmp_path, inline=True)

    assert response.headers["content-disposition"].startswith("inline")
