"""Offline tests for WebScraper: URL policy, robots.txt, redirects, content and crawl.

Most responses come from an ``httpx.MockTransport``. Hosts are ``*.test`` names
with ``allow_private_networks=True`` (no DNS lookup); the address checks use IP
literals and a patched ``getaddrinfo``. The connection tests patch the TCP connect
or serve a page from a loopback server, so no test reaches the network.
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket

import httpx
import pytest

pytest.importorskip("trafilatura")
pytest.importorskip("protego")

from gaik.software_components.web_scraper import (  # noqa: E402
    MODEL_TEXT_NOTICE,
    CrawlResult,
    ScrapedPage,
    ScrapeError,
    SkippedPage,
    UrlPolicy,
    WebScraper,
    normalize_url,
)
from gaik.software_components.web_scraper.content import clean_markdown  # noqa: E402

ARTICLE = " ".join(["The GAIK toolkit turns documents into structured data."] * 12)


def html_page(title: str, body: str, *, head: str = "", lang: str = "en") -> str:
    return (
        f'<!doctype html><html lang="{lang}"><head><title>{title}</title>{head}</head>'
        f"<body><nav><a href='/'>Home</a></nav><main><h1>{title}</h1>"
        f"<p>{ARTICLE}</p>{body}</main><footer>Footer text</footer></body></html>"
    )


class Site:
    """A fake web server: URL -> (status, headers, body), with a request log."""

    def __init__(self, routes: dict[str, tuple[int, dict, str | bytes]]):
        self.routes = routes
        self.requests: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)
        if url in self.routes:
            status, headers, body = self.routes[url]
        elif url.endswith("/robots.txt"):
            status, headers, body = 404, {}, ""
        else:
            status, headers, body = 404, {"content-type": "text/html"}, "<html>missing</html>"
        content = body.encode("utf-8") if isinstance(body, str) else body
        return httpx.Response(status, headers=headers, content=content)

    def pages(self) -> list[str]:
        return [url for url in self.requests if not url.endswith("/robots.txt")]


HTML = {"content-type": "text/html; charset=utf-8"}


def scraper(site: Site, **kwargs) -> WebScraper:
    kwargs.setdefault("allowed_domains", ["example.test"])
    kwargs.setdefault("delay_seconds", 0)
    return WebScraper(allow_private_networks=True, transport=httpx.MockTransport(site), **kwargs)


# ---------------------------------------------------------------------- URLs


def test_normalize_url_drops_fragment_default_port_and_case():
    assert normalize_url("HTTPS://Example.TEST:443/a#top") == "https://example.test/a"
    assert normalize_url("http://example.test") == "http://example.test/"
    assert normalize_url("http://example.test:8080/x?q=1") == "http://example.test:8080/x?q=1"
    assert normalize_url("../b", base="https://example.test/a/c") == "https://example.test/b"


def test_policy_allows_subdomains_but_not_lookalikes():
    policy = UrlPolicy(["example.test"], allow_private_networks=True)
    assert policy.refusal("https://example.test/") is None
    assert policy.refusal("https://www.example.test/x") is None
    assert "outside the allowed domains" in policy.refusal("https://badexample.test/")
    assert "outside the allowed domains" in policy.refusal("https://example.test.evil.test/")


def test_policy_refuses_other_schemes_and_credentials():
    policy = UrlPolicy(allow_private_networks=True)
    assert "only http and https" in policy.refusal("file:///etc/passwd")
    assert "only http and https" in policy.refusal("ftp://example.test/")
    assert "user name or password" in policy.refusal("https://user:pw@example.test/")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://10.0.0.5/",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://100.64.0.1/",
    ],
)
def test_policy_refuses_private_addresses(url):
    assert "private or local address" in UrlPolicy().refusal(url)


def test_policy_allows_public_address_literal():
    assert UrlPolicy().refusal("https://8.8.8.8/") is None


def test_policy_refuses_a_name_that_resolves_to_a_private_address(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert "private or local address" in UrlPolicy(["internal.test"]).refusal(
        "https://internal.test/"
    )


def test_policy_keeps_the_addresses_it_checked(monkeypatch):
    calls: list[str] = []

    def fake_getaddrinfo(host, *args, **kwargs):
        calls.append(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    policy = UrlPolicy(["public.test"])
    assert policy.refusal("https://public.test/") is None
    assert policy.public_addresses("public.test") == ("8.8.8.8",)
    assert policy.public_addresses("PUBLIC.test") == ("8.8.8.8",)
    assert calls == ["public.test"]


def test_policy_gives_no_addresses_when_one_of_them_is_private(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert UrlPolicy(["mixed.test"]).public_addresses("mixed.test") == ()


def test_empty_allowlist_is_an_error():
    with pytest.raises(ValueError):
        UrlPolicy([])


def test_clean_markdown_puts_link_text_on_one_line():
    md = "[04.11.2026\n\n   Uutinen\n  Title](https://x.test/a)\n\n\n\nNext"
    assert clean_markdown(md) == "[04.11.2026 Uutinen Title](https://x.test/a)\n\nNext"


# ---------------------------------------------------------------------- scrape


def test_scrape_reads_markdown_metadata_links_and_json_ld():
    event = {"@context": "https://schema.org", "@type": "Event", "name": "GenAI Workshop"}
    head = (
        '<meta name="description" content="About the toolkit">'
        '<link rel="canonical" href="https://example.test/about">'
        f'<script type="application/ld+json">{json.dumps({"@graph": [event]})}</script>'
    )
    body = (
        '<p><a href="/docs#install">Docs</a> <a href="https://other.test/x">Other</a> '
        '<a href="mailto:a@example.test">Mail</a> <a href="#top">Top</a></p>'
    )
    site = Site({"https://example.test/about": (200, HTML, html_page("About", body, head=head))})
    with scraper(site) as s:
        page = s.scrape("https://example.test/about")

    assert page.title == "About"
    assert page.description == "About the toolkit"
    assert page.language == "en"
    assert page.canonical_url == "https://example.test/about"
    assert "structured data" in page.markdown
    assert "Footer text" not in page.markdown
    assert page.word_count > 50
    assert page.structured_data == [event]
    by_url = {link.url: link for link in page.links}
    assert set(by_url) == {
        "https://example.test/",
        "https://example.test/docs",
        "https://other.test/x",
    }
    assert by_url["https://example.test/docs"].internal is True
    assert by_url["https://other.test/x"].internal is False
    assert page.status_code == 200 and page.rendered is False


def test_redirect_inside_allowed_domains_is_followed():
    site = Site(
        {
            "https://example.test/old": (301, {"location": "/new"}, ""),
            "https://example.test/new": (200, HTML, html_page("New", "")),
        }
    )
    with scraper(site) as s:
        page = s.scrape("https://example.test/old")
    assert page.url == "https://example.test/old"
    assert page.final_url == "https://example.test/new"


def test_redirect_outside_allowed_domains_is_refused():
    site = Site({"https://example.test/go": (302, {"location": "https://evil.test/"}, "")})
    with scraper(site) as s, pytest.raises(ScrapeError, match="outside the allowed domains"):
        s.scrape("https://example.test/go")
    assert "https://evil.test/" not in site.requests


def test_redirect_loop_stops():
    site = Site({"https://example.test/a": (302, {"location": "/a"}, "")})
    with scraper(site, max_redirects=3) as s, pytest.raises(ScrapeError, match="redirects"):
        s.scrape("https://example.test/a")


@pytest.mark.parametrize(
    ("route", "match"),
    [
        ((404, HTML, "nope"), "HTTP 404"),
        ((200, {"content-type": "application/pdf"}, b"%PDF"), "not an HTML page"),
        ((200, HTML, "x" * 2000), "larger than"),
    ],
)
def test_scrape_errors_say_why(route, match):
    site = Site({"https://example.test/p": route})
    with scraper(site, max_page_bytes=1000) as s, pytest.raises(ScrapeError, match=match):
        s.scrape("https://example.test/p")


def test_retry_once_on_503():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, headers={"retry-after": "0"})
        return httpx.Response(200, headers=HTML, content=html_page("Ok", "").encode())

    s = WebScraper(
        ["example.test"],
        allow_private_networks=True,
        delay_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    assert s.scrape("https://example.test/").title == "Ok"
    assert calls["n"] == 2


def test_bad_options_are_rejected():
    with pytest.raises(ValueError, match="render_js"):
        WebScraper(["example.test"], render_js="always")
    with pytest.raises(ValueError, match="extraction"):
        WebScraper(["example.test"], extraction="everything")


def test_scraper_without_allowed_domains_needs_allow_any_domain():
    with pytest.raises(ValueError, match="allowed_domains"):
        WebScraper()
    with pytest.raises(ValueError, match="not both"):
        WebScraper(["example.test"], allow_any_domain=True)
    with WebScraper(allow_any_domain=True) as s:
        assert s.policy.allowed_domains is None


# ---------------------------------------------------------------------- robots.txt


def test_robots_disallow_with_wildcards():
    robots = "User-agent: *\nDisallow: /*/private\nDisallow: /admin/\n"
    site = Site(
        {
            "https://example.test/robots.txt": (200, {"content-type": "text/plain"}, robots),
            "https://example.test/fi/private": (200, HTML, html_page("Secret", "")),
            "https://example.test/ok": (200, HTML, html_page("Ok", "")),
        }
    )
    with scraper(site) as s:
        with pytest.raises(ScrapeError, match="robots.txt disallows"):
            s.scrape("https://example.test/fi/private")
        assert s.scrape("https://example.test/ok").title == "Ok"
    assert "https://example.test/fi/private" not in site.requests
    assert site.requests.count("https://example.test/robots.txt") == 1


def test_robots_server_error_blocks_the_site():
    site = Site({"https://example.test/robots.txt": (503, {}, "")})
    with scraper(site) as s, pytest.raises(ScrapeError, match="robots.txt answered HTTP 503"):
        s.scrape("https://example.test/")


def test_robots_ignored_when_asked():
    robots = "User-agent: *\nDisallow: /\n"
    site = Site(
        {
            "https://example.test/robots.txt": (200, {}, robots),
            "https://example.test/": (200, HTML, html_page("Home", "")),
        }
    )
    with scraper(site, respect_robots=False) as s:
        assert s.scrape("https://example.test/").title == "Home"


def test_robots_crawl_delay_longer_than_allowed_skips():
    robots = "User-agent: GAIKWebScraper\nCrawl-delay: 120\n"
    site = Site({"https://example.test/robots.txt": (200, {}, robots)})
    with (
        scraper(site, max_crawl_delay=10) as s,
        pytest.raises(ScrapeError, match="Crawl-delay|120 s"),
    ):
        s.scrape("https://example.test/")


# ---------------------------------------------------------------------- crawl


def crawl_site() -> Site:
    def links(*hrefs: str) -> str:
        return "<ul>" + "".join(f'<li><a href="{h}">{h}</a></li>' for h in hrefs) + "</ul>"

    return Site(
        {
            "https://example.test/": (
                200,
                HTML,
                html_page(
                    "Home",
                    links(
                        "/a",
                        "/b",
                        "/files/report.pdf",
                        "https://other.test/",
                        "/fi/news/1",
                        "/old",
                    ),
                ),
            ),
            "https://example.test/a": (200, HTML, html_page("A", links("/a/deep", "/"))),
            "https://example.test/b": (200, HTML, html_page("B", "")),
            "https://example.test/a/deep": (200, HTML, html_page("Deep", "")),
            "https://example.test/fi/news/1": (200, HTML, html_page("News 1", "")),
            "https://example.test/old": (301, {"location": "/a"}, ""),
        }
    )


def test_crawl_is_breadth_first_within_scope():
    site = crawl_site()
    requested: list[tuple[str, int, str | None]] = []
    with scraper(site) as s:
        result = s.crawl(
            "https://example.test/",
            max_pages=10,
            max_depth=1,
            on_request=lambda url, depth, parent: requested.append((url, depth, parent)),
        )
    titles = [page.title for page in result.pages]
    assert titles == ["Home", "A", "B", "News 1"]  # /old redirects to /a: not twice
    assert all(page.depth <= 1 for page in result.pages)
    assert result.pages[1].parent_url == "https://example.test/"
    assert "https://example.test/files/report.pdf" not in site.requests
    assert "https://other.test/" not in site.requests
    assert "https://example.test/a/deep" not in site.requests  # depth 2
    assert requested[0] == ("https://example.test/", 0, None)
    assert isinstance(result, CrawlResult) and result.skipped == []


def test_crawl_respects_max_pages_and_patterns():
    with scraper(crawl_site()) as s:
        only_two = s.crawl("https://example.test/", max_pages=2)
        news = s.crawl("https://example.test/", include_patterns=["/fi/*"])
        no_a = s.crawl("https://example.test/", exclude_patterns=["/a*", "/old"])
    assert [p.title for p in only_two.pages] == ["Home", "A"]
    assert [p.title for p in news.pages] == ["Home", "News 1"]
    assert [p.title for p in no_a.pages] == ["Home", "B", "News 1"]


def test_crawl_reports_failures_as_skipped_pages():
    site = crawl_site()
    site.routes["https://example.test/b"] = (500, HTML, "boom")
    with scraper(site) as s:
        items = list(s.iter_crawl("https://example.test/", max_depth=1))
    skipped = [item for item in items if isinstance(item, SkippedPage)]
    assert [(item.url, item.reason) for item in skipped] == [("https://example.test/b", "HTTP 500")]
    assert all(isinstance(item, ScrapedPage) for item in items if item not in skipped)


def test_crawl_of_an_invalid_start_url_yields_one_skipped_page():
    with scraper(Site({})) as s:
        result = s.crawl("https://example.test:99999/")
    assert result.pages == [] and len(result.skipped) == 1


def test_crawl_result_markdown_and_save(tmp_path):
    with scraper(crawl_site()) as s:
        result = s.crawl("https://example.test/", max_pages=2)
    markdown = result.to_markdown()
    assert "Source: https://example.test/\n" in markdown
    assert "Source: https://example.test/a\n" in markdown
    written = result.save(tmp_path)
    assert (tmp_path / "crawl.json").exists()
    assert (
        json.loads((tmp_path / "crawl.json").read_text(encoding="utf-8"))["pages"][0]["title"]
        == "Home"
    )
    assert len([p for p in written if p != "crawl.json"]) == 2
    assert all(path.read_bytes().count(b"\r\n") == 0 for path in written.values())


def test_crawl_follows_links_on_the_host_the_start_page_redirected_to():
    site = Site(
        {
            "https://example.test/": (301, {"location": "https://www.example.test/"}, ""),
            "https://www.example.test/": (
                200,
                HTML,
                html_page("Home", "<a href='/a'>A</a> <a href='https://example.test/b'>B</a>"),
            ),
            "https://www.example.test/a": (200, HTML, html_page("A", "")),
            "https://example.test/b": (200, HTML, html_page("B", "")),
        }
    )
    with scraper(site) as s:
        result = s.crawl("https://example.test/", max_pages=5)

    assert [page.title for page in result.pages] == ["Home", "A", "B"]


@pytest.mark.parametrize(
    "head",
    [
        '<link rel="canonical" href="http://[::1/">',
        '<base href="http://x:abc/">',
        '<base href="http://[bad/"><link rel="canonical" href="http://y:port/">',
    ],
)
def test_a_malformed_base_or_canonical_link_does_not_stop_the_crawl(head):
    page = f"<html><head><title>Home</title>{head}</head><body><p>{ARTICLE}</p>"
    site = Site(
        {
            "https://example.test/": (200, HTML, page + "<a href='/a'>A</a></body></html>"),
            "https://example.test/a": (200, HTML, html_page("A", "")),
        }
    )
    with scraper(site) as s:
        result = s.crawl("https://example.test/", max_pages=5)

    assert [page.title for page in result.pages] == ["Home", "A"]
    assert result.pages[0].canonical_url is None


def test_stay_on_host_false_needs_an_allowlist():
    with WebScraper(allow_any_domain=True) as s, pytest.raises(ValueError):
        list(s.iter_crawl("https://example.test/", stay_on_host=False))


# ---------------------------------------------------------------------- connections


def _resolver(answers: dict[str, list[str]], calls: list[str]):
    """A getaddrinfo that answers from ``answers``: each lookup takes the next address.

    Names are recorded in ``calls``; an IP literal (the socket connecting to an
    address it was given) is answered as itself and not recorded.
    """

    def fake_getaddrinfo(host, port=None, *args, **kwargs):
        if host in answers:
            calls.append(host)
            queue = answers[host]
            address = queue.pop(0) if len(queue) > 1 else queue[0]
        else:
            address = str(ipaddress.ip_address(host))
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port or 0))]

    return fake_getaddrinfo


def test_connection_goes_to_the_address_that_was_checked(monkeypatch):
    import httpcore

    calls: list[str] = []
    # A second lookup of the name would answer with a loopback address.
    monkeypatch.setattr(
        socket, "getaddrinfo", _resolver({"site.test": ["8.8.8.8", "127.0.0.1"]}, calls)
    )
    connected: list[tuple[str, int]] = []

    def fake_connect_tcp(self, host, port, *args, **kwargs):
        connected.append((host, port))
        raise httpcore.ConnectError("no network in tests")

    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", fake_connect_tcp)
    with WebScraper(["site.test"], respect_robots=False, delay_seconds=0) as s:
        with pytest.raises(ScrapeError, match="could not connect"):
            s.scrape("http://site.test/page")

    assert calls == ["site.test"]
    assert connected and all(target == ("8.8.8.8", 80) for target in connected)


def test_connection_to_checked_address_keeps_the_host_name(monkeypatch):
    import http.server
    import threading

    from gaik.software_components.web_scraper import policy as policy_module

    seen_hosts: list[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - the http.server hook name
            seen_hosts.append(self.headers["Host"])
            body = html_page("Local", "").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    calls: list[str] = []
    monkeypatch.setattr(socket, "getaddrinfo", _resolver({"site.test": ["127.0.0.1"]}, calls))
    # Treat the loopback server as public, so the checked-address path is the one used.
    monkeypatch.setattr(policy_module, "_is_public", lambda address: True)
    try:
        with WebScraper(["site.test"], respect_robots=False, delay_seconds=0) as s:
            page = s.scrape(f"http://site.test:{port}/")
    finally:
        server.shutdown()
        server.server_close()

    assert page.title == "Local"
    assert seen_hosts == [f"site.test:{port}"]
    assert calls == ["site.test"]


def test_proxy_from_the_environment_is_still_used(monkeypatch):
    import httpcore

    for name in ("NO_PROXY", "no_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.test:3128")
    monkeypatch.setenv("http_proxy", "http://proxy.test:3128")
    calls: list[str] = []
    monkeypatch.setattr(socket, "getaddrinfo", _resolver({"site.test": ["8.8.8.8"]}, calls))
    connected: list[tuple[str, int]] = []

    def fake_connect_tcp(self, host, port, *args, **kwargs):
        connected.append((host, port))
        raise httpcore.ConnectError("no network in tests")

    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", fake_connect_tcp)
    with WebScraper(["site.test"], respect_robots=False, delay_seconds=0) as s:
        with pytest.raises(ScrapeError, match="could not connect"):
            s.scrape("http://site.test/page")

    assert connected and all(target == ("proxy.test", 3128) for target in connected)
    assert calls == ["site.test"]  # the address check still ran before the request


def test_every_checked_address_is_tried_in_order(monkeypatch):
    import httpcore
    from gaik.software_components.web_scraper.connect import _VettedAddressBackend

    attempts: list[str] = []

    def fake_connect_tcp(self, host, port, *args, **kwargs):
        attempts.append(host)
        if host != "8.8.4.4":
            raise httpcore.ConnectError("unreachable")
        return "stream"

    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", fake_connect_tcp)
    policy = UrlPolicy(["site.test"])
    addresses = ("2001:4860::1", "2001:4860::2", "2001:4860::3", "8.8.4.4")
    policy._public["site.test"] = (addresses, float("inf"))
    assert _VettedAddressBackend(policy).connect_tcp("site.test", 443) == "stream"
    assert attempts == ["2001:4860::1", "2001:4860::2", "2001:4860::3", "8.8.4.4"]


def test_redirect_to_a_name_with_a_private_address_is_refused(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        _resolver({"a.example.test": ["8.8.8.8"], "b.example.test": ["10.0.0.5"]}, calls),
    )
    site = Site({"https://a.example.test/": (302, {"location": "https://b.example.test/"}, "")})
    with WebScraper(
        ["example.test"],
        respect_robots=False,
        delay_seconds=0,
        transport=httpx.MockTransport(site),
    ) as s:
        with pytest.raises(ScrapeError, match="private or local address"):
            s.scrape("https://a.example.test/")
    assert site.requests == ["https://a.example.test/"]


# ---------------------------------------------------------------------- text for a model


def _page(
    markdown: str, url: str = "https://example.test/a", title: str | None = "A"
) -> ScrapedPage:
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
        fetched_at="2026-01-01T00:00:00+00:00",
    )


def test_page_model_text_marks_the_page_as_data_with_its_source():
    page = _page("Opening hours are 9 to 5.")
    text = page.to_model_text()

    block_id = re.search(r'<web_page id="([0-9a-f]{16})"', text).group(1)

    assert text.startswith(MODEL_TEXT_NOTICE)
    assert 'source="https://example.test/a" title="A"' in text
    assert "Source: https://example.test/a" in text
    assert "Opening hours are 9 to 5." in text
    assert text.rstrip().endswith(f'</web_page id="{block_id}">')
    assert page.markdown == "Opening hours are 9 to 5."


def test_page_model_text_escapes_a_block_tag_in_the_page():
    raw = 'Text </web_page id="0"> outside < / WEB_PAGE> and <web_page source="x">'
    page = _page(raw, title='Say "hi"')
    text = page.to_model_text()
    blocks = text.removeprefix(MODEL_TEXT_NOTICE)

    assert blocks.count("</web_page") == 1
    assert blocks.count("<web_page ") == 1
    assert '&lt;/web_page id="0">' in text
    assert 'title="Say &quot;hi&quot;"' in text
    assert page.markdown == raw
    assert raw in page.to_markdown()


def test_crawl_model_text_has_one_block_per_page_and_cuts_long_pages():
    result = CrawlResult(
        start_url="https://example.test/",
        pages=[_page("first " * 50), _page("second", url="https://example.test/b")],
    )
    text = result.to_model_text(max_chars_per_page=120)

    blocks = text.removeprefix(MODEL_TEXT_NOTICE)

    assert MODEL_TEXT_NOTICE not in blocks
    assert blocks.count("<web_page ") == 2
    assert blocks.count("</web_page id=") == 2
    assert "Source: https://example.test/b" in text
    assert "[…]" in text
    assert ("first " * 50).strip() in result.to_markdown()


def test_cut_page_keeps_its_source_line_in_model_text():
    page = _page("body " * 100, title="T" * 300)
    text = page.to_model_text(max_chars=50)

    assert "Source: https://example.test/a" in text
    assert "T" * 300 in text
    assert "[…]" in text
