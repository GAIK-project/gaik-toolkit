"""The web scraper route keeps to its allowlist and streams a fake crawl as events."""

from __future__ import annotations

import json

import pytest
from api.routers import web_scraper as route
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, create_model


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(route.router, prefix="/web-scraper")
    return TestClient(app)


def events(response) -> list[tuple[str, dict]]:
    found, kind = [], None
    for line in response.iter_lines():
        if line.startswith("event: "):
            kind = line[7:]
        elif line.startswith("data: "):
            found.append((kind, json.loads(line[6:])))
    return found


def test_sites_lists_only_allowed_domains(client):
    data = client.get("/web-scraper/sites").json()
    assert data["allowed_domains"] == list(route.ALLOWED_DOMAINS)
    assert {site["domain"] for site in data["sites"]} <= set(route.ALLOWED_DOMAINS)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/",
        "https://gaik.ai.example.com/",
        "https://evilgaik.ai/",
        "ftp://gaik.ai/",
        "http://127.0.0.1:8000/",
    ],
)
def test_run_refuses_urls_outside_the_allowlist(client, url):
    response = client.post("/web-scraper/run", json={"url": url})
    assert response.status_code == 400


def test_run_bounds_the_crawl(client):
    response = client.post("/web-scraper/run", json={"url": "https://gaik.ai/", "max_pages": 99})
    assert response.status_code == 422


def test_run_streams_pages_from_the_scraper(client, monkeypatch):
    from gaik.software_components.web_scraper import ScrapedPage, SkippedPage

    page = ScrapedPage(
        url="https://gaik.ai/",
        final_url="https://gaik.ai/",
        status_code=200,
        title="GAIK",
        description=None,
        language="en",
        published=None,
        canonical_url=None,
        markdown="Hello " * 10,
    )

    class FakeScraper:
        def __init__(self, allowed_domains, **kwargs):
            assert tuple(allowed_domains) == route.ALLOWED_DOMAINS

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

        def iter_crawl(self, start_url, *, on_request, **kwargs):
            on_request(start_url, 0, None)
            yield page
            yield SkippedPage(url="https://gaik.ai/x", reason="HTTP 404", depth=1)

    monkeypatch.setattr("gaik.software_components.web_scraper.WebScraper", FakeScraper)
    with client.stream("POST", "/web-scraper/run", json={"url": "https://gaik.ai/"}) as response:
        found = events(response)
    kinds = [kind for kind, _ in found]
    assert kinds == ["request", "page", "skipped", "crawl_done", "done"]
    assert found[1][1]["title"] == "GAIK" and found[1][1]["word_count"] == 10
    assert found[3][1]["pages"] == 1 and found[3][1]["skipped"] == 1


def test_named_fields_fixes_an_empty_container_name():
    class Item(BaseModel):
        title: str

    unnamed = create_model("X_Collection", **{"": (list[Item], ...)})
    named = route._named_fields(unnamed)
    assert list(named.model_fields) == ["records"]
    assert route._named_fields(named) is named


def test_page_of_finds_the_section_of_a_position():
    class Page:
        def __init__(self, url):
            self.final_url = url

    pages = [Page("https://gaik.ai/"), Page("https://gaik.ai/b")]
    document = (
        "# A\n\nSource: https://gaik.ai/\n\ntext a\n---\n\n"
        "# B\n\nSource: https://gaik.ai/b\n\ntext b"
    )
    assert route._page_of(document, pages, document.index("text a")) == "https://gaik.ai/"
    assert route._page_of(document, pages, document.index("text b")) == "https://gaik.ai/b"
    assert route._page_of(document, pages, 0) is None
