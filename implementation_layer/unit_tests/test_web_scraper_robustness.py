"""Offline regression tests for WebScraper page reading and crawling (issue #147).

Responses come from ``httpx.MockTransport`` with ``*.test`` hosts and
``allow_private_networks=True``, so no test reaches the network.
"""

from __future__ import annotations

import httpx
import pytest

pytest.importorskip("trafilatura")
pytest.importorskip("protego")

from gaik.software_components.web_scraper import (  # noqa: E402
    ScrapeError,
    SkippedPage,
    WebScraper,
)
from gaik.software_components.web_scraper.content import decode_html  # noqa: E402

ARTICLE = " ".join(["The GAIK toolkit turns documents into structured data."] * 12)
HTML = {"content-type": "text/html; charset=utf-8"}


def page_body(title: str, body: str = "") -> str:
    return (
        f"<head><title>{title}</title></head><body><main><h1>{title}</h1>"
        f"<p>{ARTICLE}</p>{body}</main></body></html>"
    )


def page(title: str, body: str = "") -> str:
    return "<html>" + page_body(title, body)


def routes_transport(routes: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url in routes:
            route = routes[url]
            if callable(route):
                return route()
            return httpx.Response(200, headers=HTML, content=route.encode("utf-8"))
        if url.endswith("/robots.txt"):
            return httpx.Response(404)
        return httpx.Response(404, headers=HTML, content=b"<html>missing</html>")

    return httpx.MockTransport(handler)


def make_scraper(routes: dict, **kwargs) -> WebScraper:
    return WebScraper(
        allowed_domains=["example.test"],
        allow_private_networks=True,
        delay_seconds=0,
        transport=routes_transport(routes),
        **kwargs,
    )


class FailingStream(httpx.SyncByteStream):
    """A body that sends one chunk and then fails like a dropped connection."""

    def __init__(self, error: Exception):
        self.error = error

    def __iter__(self):
        yield b"<html><head><title>Cut"
        raise self.error


def failing(error: Exception, content_type: str = "text/html"):
    return lambda: httpx.Response(
        200, headers={"content-type": content_type}, stream=FailingStream(error)
    )


# ------------------------------------------------- #147 item 6: XHTML pages


def test_xhtml_page_with_an_xml_declaration_is_read():
    xhtml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" '
        '"http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">\n'
        '<html xmlns="http://www.w3.org/1999/xhtml">'
        + page_body("XHTML page", '<a href="/next">Next</a>')
    )
    with make_scraper({"https://example.test/": xhtml}) as scraper:
        result = scraper.scrape("https://example.test/")
    assert result.title == "XHTML page"
    assert [link.url for link in result.links] == ["https://example.test/next"]
    assert "structured data" in result.markdown


# ------------------------------------------- #147 item 7: body read errors


@pytest.mark.parametrize(
    "error",
    [httpx.ReadTimeout("slow"), httpx.RemoteProtocolError("peer closed")],
    ids=["timeout", "protocol"],
)
def test_an_error_while_the_body_is_read_is_a_scrape_error(error):
    with make_scraper({"https://example.test/": failing(error)}) as scraper:
        with pytest.raises(ScrapeError) as info:
            scraper.scrape("https://example.test/")
    assert info.value.url == "https://example.test/"


def test_one_page_that_fails_mid_body_does_not_end_the_crawl():
    routes = {
        "https://example.test/": page("Home", '<a href="/a">A</a> <a href="/b">B</a>'),
        "https://example.test/a": failing(httpx.ReadTimeout("slow")),
        "https://example.test/b": page("B"),
    }
    with make_scraper(routes) as scraper:
        items = list(scraper.iter_crawl("https://example.test/", max_pages=5))
    skipped = [item.url for item in items if isinstance(item, SkippedPage)]
    fetched = [item.final_url for item in items if not isinstance(item, SkippedPage)]
    assert fetched == ["https://example.test/", "https://example.test/b"]
    assert skipped == ["https://example.test/a"]


def test_a_robots_txt_that_fails_mid_body_is_reported_not_raised():
    routes = {
        "https://example.test/robots.txt": failing(httpx.ReadTimeout("slow"), "text/plain"),
        "https://example.test/": page("Home"),
    }
    with make_scraper(routes) as scraper:
        with pytest.raises(ScrapeError, match="robots.txt could not be read"):
            scraper.scrape("https://example.test/")


# ------------------------------------------------------------ #147 extras


def test_iso_8859_1_is_decoded_as_windows_1252():
    text = "<p>€ 5 “quoted”</p>"
    body = text.encode("cp1252")
    assert decode_html(body, "text/html; charset=ISO-8859-1") == text
    assert decode_html(b'<meta charset="latin1">' + body, "text/html").endswith(text)


@pytest.mark.parametrize(
    "option", [{"exclude_patterns": "/en/*"}, {"include_patterns": "/fi/*"}], ids=str
)
def test_a_pattern_given_as_a_string_is_one_pattern(option):
    routes = {
        "https://example.test/": page("Home", '<a href="/fi/a">FI</a> <a href="/en/b">EN</a>'),
        "https://example.test/fi/a": page("FI"),
        "https://example.test/en/b": page("EN"),
    }
    with make_scraper(routes) as scraper:
        result = scraper.crawl("https://example.test/", max_pages=5, **option)
    assert [p.final_url for p in result.pages] == [
        "https://example.test/",
        "https://example.test/fi/a",
    ]
