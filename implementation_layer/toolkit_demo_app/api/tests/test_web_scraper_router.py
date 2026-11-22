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


def _page(url: str, title: str, markdown: str):
    from gaik.software_components.web_scraper import ScrapedPage

    return ScrapedPage(
        url=url,
        final_url=url,
        status_code=200,
        title=title,
        description=None,
        language="en",
        published=None,
        canonical_url=None,
        markdown=markdown,
    )


PAGES = [
    ("https://gaik.ai/", "GAIK project", "Text of the start page."),
    ("https://gaik.ai/b", "News", "Text of page b."),
]


def test_page_of_finds_the_page_block_of_a_position():
    """The extractor reads ``to_model_text``: a quote is in the block of its own page."""
    from gaik.software_components.web_scraper import CrawlResult

    pages = [_page(*page) for page in PAGES]
    document = CrawlResult(start_url=PAGES[0][0], pages=pages).to_model_text()

    def page_of(text: str) -> str | None:
        return route._page_of(document, pages, document.index(text))

    assert page_of("Text of the start page") == "https://gaik.ai/"
    assert page_of("Text of page b") == "https://gaik.ai/b"
    # A quote of a title belongs to its own page, not to the page before it.
    assert page_of("# News") == "https://gaik.ai/b"
    assert page_of("# GAIK project") == "https://gaik.ai/"
    assert route._page_of(document, pages, 0) is None  # the notice before the blocks


def test_page_of_reads_a_document_without_blocks_by_its_source_lines():
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


def test_the_extractor_reads_the_pages_as_marked_data_and_each_quote_names_its_page(
    client, monkeypatch
):
    pages = [_page(*page) for page in PAGES]

    class FakeScraper:
        def __init__(self, allowed_domains, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

        def iter_crawl(self, start_url, *, on_request, **kwargs):
            yield from pages

    class Item(BaseModel):
        title: str

    read: list[str] = []

    class FakeExtractor:
        def __init__(self, config, **kwargs):
            pass

        def extract(self, *, documents, **kwargs):
            read.extend(documents)
            quote = {"field": "title", "document": 1, "page": 1, "quote": "Text of page b."}
            return [{"title": "Text of page b.", "field_sources": {"items": [quote]}}]

    monkeypatch.setattr("gaik.software_components.web_scraper.WebScraper", FakeScraper)
    monkeypatch.setattr("gaik.software_components.extractor.DataExtractor", FakeExtractor)
    monkeypatch.setattr(route, "get_api_config", lambda: {"provider": "azure", "model": "m"})
    monkeypatch.setattr(route, "get_model_options", lambda config: {})
    monkeypatch.setattr(route, "_schema_for", lambda config, requirements: (Item, None))
    body = {"url": "https://gaik.ai/", "requirements": "The title of each page"}
    with client.stream("POST", "/web-scraper/run", json=body) as response:
        found = events(response)

    (document,) = read
    assert document.startswith("The <web_page> blocks below hold web pages")
    assert document.count('<web_page id="') == 2
    result = next(data for kind, data in found if kind == "result")
    (source,) = result["sources"]
    assert source["verdict"] == "verified"
    assert source["page_url"] == "https://gaik.ai/b"
