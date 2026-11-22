"""Video search rejects a top_k outside 1..100 before it reaches the store."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from api.routers import video_search
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch) -> tuple[TestClient, list[int]]:
    seen: list[int] = []

    def search_keyword(query, *, top_k, filters=None):
        seen.append(top_k)
        return []

    store = SimpleNamespace(search_keyword=search_keyword)
    monkeypatch.setattr(video_search, "_get_store", lambda: store)
    monkeypatch.setattr(video_search, "_get_embedder", lambda: None)
    app = FastAPI()
    app.include_router(video_search.router, prefix="/video")
    return TestClient(app), seen


@pytest.mark.parametrize("top_k", ["0", "-1", "101"])
def test_a_top_k_out_of_range_is_rejected(client, top_k):
    http, seen = client
    response = http.post(
        "/video/search", data={"query": "kissa", "top_k": top_k, "search_type": "keyword"}
    )

    assert response.status_code == 422
    assert seen == []


def test_a_top_k_in_range_reaches_the_store(client):
    http, seen = client
    response = http.post(
        "/video/search", data={"query": "kissa", "top_k": "5", "search_type": "keyword"}
    )

    assert response.status_code == 200
    assert seen == [5]
