"""Generated results are served only to the user whose run made them (D20)."""

from __future__ import annotations

import asyncio
import time

import pytest
from api.routers import dental_transcription, diary, luvata_order
from api.utils import result_owner
from api.utils.result_owner import forget_owner, owned_by, remember_owner, require_owner
from fastapi import HTTPException


def test_an_id_is_owned_only_by_its_user():
    remember_owner("r1", "user-a")
    try:
        assert owned_by("r1", "user-a")
        assert not owned_by("r1", "user-b")
        assert not owned_by("r1", "")
        assert not owned_by("unknown", "user-a")
        with pytest.raises(HTTPException) as refused:
            require_owner("r1", "user-b", "PDF not found")
        assert (refused.value.status_code, refused.value.detail) == (404, "PDF not found")
    finally:
        forget_owner("r1")


def test_a_run_without_a_user_is_served_only_without_one():
    remember_owner("r2", "")
    try:
        assert owned_by("r2", "")
        assert not owned_by("r2", "user-a")
    finally:
        forget_owner("r2")


def test_old_entries_are_dropped(monkeypatch):
    remember_owner("old", "user-a")
    later = time.time() + result_owner.TTL_SECONDS + 1
    monkeypatch.setattr(result_owner.time, "time", lambda: later)
    remember_owner("new", "user-a")
    try:
        assert not owned_by("old", "user-a")
        assert owned_by("new", "user-a")
    finally:
        forget_owner("new")


@pytest.mark.parametrize("kind", ["srt", "vtt"])
def test_subtitles_are_served_only_to_their_owner(kind):
    dental_transcription.SRT_STORAGE["job-s"] = ("1\n00:00 --> 00:01\nhi\n", "WEBVTT\n")
    remember_owner("job-s", "user-a")
    download = getattr(dental_transcription, f"download_{kind}")
    try:
        assert asyncio.run(download("job-s", user="user-a")).status_code == 200
        with pytest.raises(HTTPException) as refused:
            asyncio.run(download("job-s", user="user-b"))
        assert refused.value.status_code == 404
    finally:
        dental_transcription.SRT_STORAGE.pop("job-s", None)
        forget_owner("job-s")


def test_the_diary_pdf_is_served_only_to_its_owner(tmp_path):
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    diary.PDF_STORAGE["job-d"] = pdf
    remember_owner("job-d", "user-a")
    try:
        assert asyncio.run(diary.download_diary_pdf("job-d", user="user-a")).path == pdf
        with pytest.raises(HTTPException) as refused:
            asyncio.run(diary.download_diary_pdf("job-d", user="user-b"))
        assert refused.value.status_code == 404
    finally:
        diary.PDF_STORAGE.pop("job-d", None)
        forget_owner("job-d")


def test_the_order_draft_is_served_only_to_its_owner():
    luvata_order.pdf_storage["job-l"] = (b"%PDF-1.4\n", time.time())
    remember_owner("job-l", "user-a")
    try:
        ok = asyncio.run(luvata_order.download_pdf("job-l", user="user-a"))
        assert ok.body == b"%PDF-1.4\n"
        with pytest.raises(HTTPException) as refused:
            asyncio.run(luvata_order.download_pdf("job-l", user="user-b"))
        assert refused.value.status_code == 404
    finally:
        luvata_order.pdf_storage.pop("job-l", None)
        forget_owner("job-l")


def _routes_that_make_results():
    from api.routers import pipeline, tabular_agent

    return [
        *(
            getattr(pipeline, n)
            for n in (
                "audio_pipeline",
                "document_pipeline",
                "text_pipeline",
                "audio_pipeline_stream",
                "text_pipeline_stream",
                "document_pipeline_stream",
            )
        ),
        diary.diary_audio_pipeline_stream,
        diary.diary_text_pipeline_stream,
        luvata_order.process_order,
        tabular_agent.upload_file,
    ] + [
        r.endpoint
        for r in dental_transcription.router.routes
        if getattr(r, "path", "").endswith("/stream")
    ]


@pytest.mark.parametrize("route", _routes_that_make_results(), ids=lambda r: r.__name__)
def test_every_route_that_makes_a_result_records_its_user(route):
    import inspect

    from fastapi.params import Depends

    user = inspect.signature(route).parameters["user"].default
    assert isinstance(user, Depends) and user.dependency is result_owner.current_user
    assert "remember_owner(" in inspect.getsource(route)
