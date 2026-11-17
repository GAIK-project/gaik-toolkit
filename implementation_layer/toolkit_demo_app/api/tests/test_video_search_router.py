"""Video search: the API only reads the shared index."""

from __future__ import annotations

import pytest
from api.routers import video_search
from fastapi import FastAPI
from fastapi.testclient import TestClient


class _Store:
    """Records each keyword search; the tests use no other part of the store."""

    def __init__(self) -> None:
        self.limits: list[int] = []

    def search_keyword(self, query: str, *, top_k: int, filters: dict | None):
        self.limits.append(top_k)
        return []


@pytest.fixture
def store(monkeypatch) -> _Store:
    fake = _Store()
    monkeypatch.setattr(video_search, "_get_store", lambda: fake)
    monkeypatch.setattr(video_search, "_get_embedder", lambda: None)
    return fake


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(video_search.router, prefix="/video-search")
    return TestClient(app)


def test_the_only_route_that_is_not_a_read_is_the_search() -> None:
    # Every visitor sees the same index: a route that writes or clears it would
    # be open to anyone with an account. The search is a POST for its form fields.
    not_reads = {
        (method, route.path)
        for route in video_search.router.routes
        for method in route.methods
        if method not in {"GET", "HEAD"}
    }
    assert not_reads == {("POST", "/search")}


def test_the_index_cannot_be_cleared_or_written_over_http(client, store) -> None:
    assert client.delete("/video-search/clear").status_code == 404
    response = client.post(
        "/video-search/ingest/stream",
        files={"file": ("made-up.srt", b"1\n00:00:00,000 --> 00:00:02,000\nHello\n")},
        data={"video_title": "Made up", "video_id": "an-indexed-video"},
    )
    assert response.status_code == 404
    assert store.limits == []
