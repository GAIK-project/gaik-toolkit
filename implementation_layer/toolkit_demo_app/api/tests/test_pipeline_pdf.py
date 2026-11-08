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


def test_expired_pdfs_are_removed_and_fresh_ones_kept(tmp_path, monkeypatch):
    from datetime import datetime, timedelta

    monkeypatch.setattr(pipeline, "PDF_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "PDF_STORAGE", {})
    monkeypatch.setattr(pipeline, "PDF_TIMESTAMPS", {})
    now = datetime.now()
    old, fresh = pipeline._pdf_path("old-job"), pipeline._pdf_path("fresh-job")
    old.write_bytes(b"%PDF-1.4\n")
    fresh.write_bytes(b"%PDF-1.4\n")
    pipeline.PDF_STORAGE.update({"old-job": old, "fresh-job": fresh})
    pipeline.PDF_TIMESTAMPS.update({"old-job": now - timedelta(hours=2), "fresh-job": now})

    pipeline.remove_expired_pdfs(now)

    assert not old.exists() and "old-job" not in pipeline.PDF_STORAGE
    assert fresh.exists() and "fresh-job" in pipeline.PDF_STORAGE


def test_a_pdf_left_by_an_earlier_process_is_removed(tmp_path, monkeypatch):
    import os
    from datetime import datetime, timedelta

    monkeypatch.setattr(pipeline, "PDF_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "PDF_STORAGE", {})
    monkeypatch.setattr(pipeline, "PDF_TIMESTAMPS", {})
    leftover = tmp_path / "before-restart.pdf"
    leftover.write_bytes(b"%PDF-1.4\n")
    two_hours_ago = (datetime.now() - timedelta(hours=2)).timestamp()
    os.utime(leftover, (two_hours_ago, two_hours_ago))
    recent = tmp_path / "recent.pdf"
    recent.write_bytes(b"%PDF-1.4\n")

    assert pipeline.remove_expired_pdfs() == 1
    assert not leftover.exists() and recent.exists()


def test_the_api_starts_the_pdf_cleanup(monkeypatch):
    from api import main
    from fastapi.testclient import TestClient

    started = []

    async def fake_cleanup():
        started.append(True)

    monkeypatch.setattr(main.pipeline, "cleanup_old_pdfs", fake_cleanup)
    with TestClient(main.app):
        pass
    assert started == [True]
