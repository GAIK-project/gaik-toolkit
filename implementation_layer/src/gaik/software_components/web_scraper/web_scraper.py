"""WebScraper: fetch web pages, or crawl one site, into LLM-ready Markdown.

Every request passes the same checks: the URL policy (http(s), allowed domains,
public addresses only), robots.txt, a delay between requests to the same host, a
size limit and an HTML content type. Redirects are followed one hop at a time so
each hop is checked too.
"""

from __future__ import annotations

import fnmatch
import logging
import time
from collections import deque
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import PurePosixPath
from typing import Literal
from urllib.parse import urlsplit

import httpx

try:
    from protego import Protego
except ImportError as exc:  # pragma: no cover - depends on the installed extra
    raise ImportError(
        "WebScraper needs the web-scraper extra: pip install 'gaik[web-scraper]'"
    ) from exc

from gaik import __version__

from .browser import BrowserRenderer, browser_available
from .content import Extraction, decode_html, read_page
from .models import CrawlResult, PageLink, ScrapedPage, SkippedPage
from .policy import ScrapeError, UrlPolicy, host_of, normalize_url

logger = logging.getLogger(__name__)

#: The product token robots.txt rules are matched against.
ROBOTS_AGENT = "GAIKWebScraper"
DEFAULT_USER_AGENT = f"{ROBOTS_AGENT}/{__version__} (+https://github.com/GAIK-project/gaik-toolkit)"

_HTML_TYPES = ("text/html", "application/xhtml+xml")
_RETRY_STATUSES = {429, 502, 503, 504}
_MAX_RETRY_WAIT = 10.0
_MAX_URL_LENGTH = 2048
_MAX_ROBOTS_BYTES = 512_000
_UNRENDERED_WORDS = 50
# Links to files that are not HTML pages are not followed in a crawl.
_FILE_SUFFIXES = frozenset(
    ".pdf .jpg .jpeg .png .gif .svg .webp .avif .ico .bmp .tif .tiff .zip .gz .tgz .tar "
    ".rar .7z .mp3 .mp4 .m4a .m4v .wav .ogg .avi .mov .webm .mkv .doc .docx .xls .xlsx "
    ".ppt .pptx .odt .ods .csv .json .xml .rss .atom .css .js .mjs .map .woff .woff2 .ttf "
    ".otf .eot .exe .msi .dmg .apk .ics .vcf .txt .epub".split()
)

RequestCallback = Callable[[str, int, "str | None"], None]


class WebScraper:
    """Fetches pages and crawls sites into Markdown, inside a domain allowlist.

    Args:
        allowed_domains: Domains the scraper may fetch from; a domain allows its
            subdomains too. ``None`` allows every public host. Set it whenever the
            URLs come from users.
        respect_robots: Obey robots.txt (RFC 9309): disallowed pages are skipped, a
            ``Crawl-delay`` lengthens the delay, and a robots.txt that answers with a
            server error blocks the whole site.
        render_js: ``True`` renders every page in headless Chromium (needs the
            ``web-scraper-browser`` extra). ``"auto"`` renders only a page whose HTML
            holds almost no text but has scripts, when Playwright is installed.
        extraction: How strictly the main content is separated from boilerplate:
            ``"precision"`` keeps only the main text, ``"recall"`` keeps more blocks
            (useful for home pages of short cards), ``"balanced"`` sits between.
        delay_seconds: Least time between two requests to the same host.
        max_crawl_delay: The longest robots.txt ``Crawl-delay`` the scraper waits
            out; a site asking for more is skipped.
        timeout_seconds: Timeout of one request.
        max_page_bytes: Largest page, after decompression, that is read.
        max_redirects: Most redirects followed for one URL.
        user_agent: The ``User-Agent`` header. The default names the toolkit and
            links to its repository, so a site owner can see who is crawling.
        allow_private_networks: Allow hosts that resolve to private or local
            addresses. Off by default.
        transport: An httpx transport, for tests (``httpx.MockTransport``) or a proxy.

    The scraper keeps one HTTP connection pool (and with ``render_js`` one browser);
    close it with :meth:`close` or use it as a context manager. It is not
    thread-safe: use one scraper per thread.

    Example:
        >>> with WebScraper(allowed_domains=["gaik.ai"]) as scraper:
        ...     result = scraper.crawl("https://gaik.ai/", max_pages=5)
        >>> print(result.to_markdown()[:300])
    """

    def __init__(
        self,
        allowed_domains: Iterable[str] | None = None,
        *,
        respect_robots: bool = True,
        render_js: bool | Literal["auto"] = False,
        extraction: Extraction = "balanced",
        delay_seconds: float = 0.5,
        max_crawl_delay: float = 30.0,
        timeout_seconds: float = 20.0,
        max_page_bytes: int = 5_000_000,
        max_redirects: int = 5,
        user_agent: str | None = None,
        allow_private_networks: bool = False,
        transport: httpx.BaseTransport | None = None,
    ):
        if render_js not in (True, False, "auto"):
            raise ValueError("render_js must be True, False or 'auto'")
        if extraction not in ("precision", "balanced", "recall"):
            raise ValueError("extraction must be 'precision', 'balanced' or 'recall'")
        if delay_seconds < 0 or max_crawl_delay < 0 or timeout_seconds <= 0:
            raise ValueError("delays must be >= 0 and timeout_seconds > 0")
        if max_page_bytes < 1 or max_redirects < 0:
            raise ValueError("max_page_bytes must be >= 1 and max_redirects >= 0")

        self.policy = UrlPolicy(allowed_domains, allow_private_networks=allow_private_networks)
        self.respect_robots = respect_robots
        self.render_js = render_js
        self.extraction: Extraction = extraction
        self.delay_seconds = delay_seconds
        self.max_crawl_delay = max_crawl_delay
        self.timeout_seconds = timeout_seconds
        self.max_page_bytes = max_page_bytes
        self.max_redirects = max_redirects
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
            },
            transport=transport,
        )
        # origin -> parsed robots.txt; None allows everything; a str blocks the site
        self._robots: dict[str, Protego | str | None] = {}
        self._last_request: dict[str, float] = {}
        self._renderer: BrowserRenderer | None = None

    def __enter__(self) -> WebScraper:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        """Close the connection pool and the browser, if one was started."""
        self._client.close()
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None

    # ------------------------------------------------------------------ public API

    def scrape(self, url: str) -> ScrapedPage:
        """Fetch one page.

        Raises:
            ScrapeError: The page could not be fetched; ``reason`` says why (outside
                the allowed domains, robots.txt, HTTP status, not HTML, ...).
        """
        return self._scrape(_normalized(url), depth=0, parent_url=None)

    def iter_crawl(
        self,
        start_url: str,
        *,
        max_pages: int = 10,
        max_depth: int = 2,
        include_patterns: Iterable[str] | None = None,
        exclude_patterns: Iterable[str] | None = None,
        stay_on_host: bool = True,
        on_request: RequestCallback | None = None,
    ) -> Iterator[ScrapedPage | SkippedPage]:
        """Crawl breadth-first from ``start_url``, yielding each page as it is fetched.

        Args:
            start_url: The first page.
            max_pages: Stop after this many pages.
            max_depth: Follow links at most this many steps from the start page.
            include_patterns: Follow only links whose path (with its query) matches
                one of these shell patterns, e.g. ``["/fi/koulutus*"]``.
            exclude_patterns: Never follow links whose path matches one of these.
            stay_on_host: Follow links on the start page's host only. ``False``
                follows links to every allowed domain (and needs ``allowed_domains``).
            on_request: Called with ``(url, depth, parent_url)`` before each page is
                requested, e.g. to show progress.

        Yields:
            A :class:`ScrapedPage` per page, and a :class:`SkippedPage` for each URL
            that was tried but failed. Links filtered out by the scope are not
            reported. Stop iterating to stop the crawl.
        """
        if max_pages < 1 or max_depth < 0:
            raise ValueError("max_pages must be >= 1 and max_depth >= 0")
        if not stay_on_host and self.policy.allowed_domains is None:
            raise ValueError("stay_on_host=False needs allowed_domains")
        include = [p.lower() for p in include_patterns or ()]
        exclude = [p.lower() for p in exclude_patterns or ()]
        try:
            start = _normalized(start_url)
        except ScrapeError as exc:
            yield SkippedPage(url=start_url, reason=exc.reason)
            return

        start_host = host_of(start)
        queue: deque[tuple[str, int, str | None]] = deque([(start, 0, None)])
        queued = {start}
        fetched: set[str] = set()
        pages = attempts = 0
        while queue and pages < max_pages and attempts < max_pages * 3:
            url, depth, parent = queue.popleft()
            if url in fetched:
                continue
            attempts += 1
            if on_request is not None:
                on_request(url, depth, parent)
            try:
                page = self._scrape(url, depth=depth, parent_url=parent)
            except ScrapeError as exc:
                yield SkippedPage(url=url, reason=exc.reason, depth=depth, parent_url=parent)
                continue
            # Not deduplicated by rel=canonical: sites that point every page's canonical
            # at the home page would end the crawl after one page.
            if page.final_url in fetched:
                fetched.add(url)  # a redirect alias of a page already yielded
                continue
            fetched.update((url, page.final_url))
            pages += 1
            yield page
            if depth >= max_depth:
                continue
            for link in page.links:
                if link.url not in queued and self._follows(
                    link, start_host, include, exclude, stay_on_host
                ):
                    queued.add(link.url)
                    queue.append((link.url, depth + 1, page.final_url))

    def crawl(
        self,
        start_url: str,
        *,
        max_pages: int = 10,
        max_depth: int = 2,
        include_patterns: Iterable[str] | None = None,
        exclude_patterns: Iterable[str] | None = None,
        stay_on_host: bool = True,
        on_request: RequestCallback | None = None,
    ) -> CrawlResult:
        """Crawl like :meth:`iter_crawl` (same arguments) and return every page at once."""
        started = time.monotonic()
        result = CrawlResult(start_url=start_url)
        crawl = self.iter_crawl(
            start_url,
            max_pages=max_pages,
            max_depth=max_depth,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            stay_on_host=stay_on_host,
            on_request=on_request,
        )
        for item in crawl:
            if isinstance(item, ScrapedPage):
                result.pages.append(item)
            else:
                result.skipped.append(item)
        result.duration_s = round(time.monotonic() - started, 3)
        return result

    # ------------------------------------------------------------------ crawl scope

    def _follows(
        self,
        link: PageLink,
        start_host: str,
        include: list[str],
        exclude: list[str],
        stay_on_host: bool,
    ) -> bool:
        if stay_on_host:
            if host_of(link.url) != start_host:
                return False
        elif not self.policy.in_allowed_domains(link.url):
            return False
        parts = urlsplit(link.url)
        if PurePosixPath(parts.path).suffix.lower() in _FILE_SUFFIXES:
            return False
        target = (parts.path + (f"?{parts.query}" if parts.query else "")).lower()
        if include and not any(fnmatch.fnmatchcase(target, p) for p in include):
            return False
        return not any(fnmatch.fnmatchcase(target, p) for p in exclude)

    # ------------------------------------------------------------------ fetching

    def _scrape(self, url: str, *, depth: int, parent_url: str | None) -> ScrapedPage:
        started = time.monotonic()
        final_url, status, html = self._fetch(url)
        rendered = False
        if self.render_js is True:
            final_url, status, html = self._render(final_url)
            rendered = True
        content = read_page(html, final_url, self.policy, self.extraction)
        if (
            self.render_js == "auto"
            and len(content.markdown.split()) < _UNRENDERED_WORDS
            and "<script" in html.lower()
            and browser_available()
        ):
            try:
                final_url, status, html = self._render(final_url)
                content = read_page(html, final_url, self.policy, self.extraction)
                rendered = True
            except Exception as exc:  # keep the HTTP result: rendering is a bonus
                logger.info("Rendering %s failed, keeping the HTTP result: %s", final_url, exc)

        return ScrapedPage(
            url=url,
            final_url=final_url,
            status_code=status,
            title=content.title,
            description=content.description,
            language=content.language,
            published=content.published,
            canonical_url=content.canonical_url,
            markdown=content.markdown,
            links=content.links,
            structured_data=content.structured_data,
            depth=depth,
            parent_url=parent_url,
            rendered=rendered,
            fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
            elapsed_s=round(time.monotonic() - started, 3),
        )

    def _fetch(self, url: str) -> tuple[str, int, str]:
        """GET an HTML page, checking every redirect hop; return final URL, status, HTML."""
        current = url
        for _ in range(self.max_redirects + 1):
            self._check(current)
            response = self._get(current)
            try:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ScrapeError(
                            current, f"HTTP {response.status_code} without a Location"
                        )
                    current = _normalized(location, base=current)
                    continue
                if response.status_code >= 400:
                    raise ScrapeError(current, f"HTTP {response.status_code}")
                content_type = response.headers.get("content-type", "")
                media_type = content_type.split(";", 1)[0].strip().lower()
                if media_type and media_type not in _HTML_TYPES:
                    raise ScrapeError(current, f"not an HTML page ({media_type})")
                body = self._read(response, current, self.max_page_bytes)
                return current, response.status_code, decode_html(body, content_type)
            finally:
                response.close()
        raise ScrapeError(url, f"more than {self.max_redirects} redirects")

    def _render(self, url: str) -> tuple[str, int, str]:
        if self._renderer is None:
            self._renderer = BrowserRenderer(self.user_agent, self.timeout_seconds)
        self._wait_turn(url)
        final_url, status, html = self._renderer.render(url, self.policy)
        final_url = _normalized(final_url)
        if final_url != url:
            self._check(final_url)
        if status >= 400:
            raise ScrapeError(url, f"HTTP {status}")
        return final_url, status, html

    def _get(self, url: str, *, polite: bool = True) -> httpx.Response:
        """Send a streamed GET; retry once on a timeout, a lost connection or 429/5xx."""
        for attempt in (1, 2):
            if polite:
                self._wait_turn(url)
            try:
                response = self._client.send(self._client.build_request("GET", url), stream=True)
            except httpx.TimeoutException as exc:
                if attempt == 2:
                    raise ScrapeError(url, "the server did not answer in time") from exc
                continue
            except httpx.HTTPError as exc:
                if attempt == 2:
                    raise ScrapeError(url, f"could not connect ({type(exc).__name__})") from exc
                continue
            if response.status_code in _RETRY_STATUSES and attempt == 1:
                wait = _retry_after(response)
                response.close()
                if wait is None:
                    raise ScrapeError(url, f"HTTP {response.status_code}")
                time.sleep(wait)
                continue
            return response
        raise AssertionError("unreachable")  # pragma: no cover

    @staticmethod
    def _read(response: httpx.Response, url: str, limit: int) -> bytes:
        too_large = ScrapeError(url, f"the response is larger than {limit:,} bytes")
        declared = response.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            raise too_large
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > limit:
                raise too_large
            chunks.append(chunk)
        return b"".join(chunks)

    def _wait_turn(self, url: str) -> None:
        host = host_of(url)
        delay = max(self.delay_seconds, self._crawl_delay(url))
        last = self._last_request.get(host)
        if last is not None:
            wait = last + delay - time.monotonic()
            if wait > 0:
                time.sleep(wait)
        self._last_request[host] = time.monotonic()

    # ------------------------------------------------------------------ policy + robots

    def _check(self, url: str) -> None:
        if len(url) > _MAX_URL_LENGTH:
            raise ScrapeError(url[:100] + "…", "the URL is too long")
        reason = self.policy.refusal(url)
        if reason is not None:
            raise ScrapeError(url, reason)
        if not self.respect_robots:
            return
        robots = self._robots_for(url)
        if isinstance(robots, str):
            raise ScrapeError(url, robots)
        if robots is None:
            return
        if not robots.can_fetch(url, ROBOTS_AGENT):
            raise ScrapeError(url, "robots.txt disallows this page")
        delay = robots.crawl_delay(ROBOTS_AGENT)
        if delay is not None and delay > self.max_crawl_delay:
            raise ScrapeError(
                url,
                f"robots.txt asks for {delay:g} s between requests "
                f"(more than max_crawl_delay={self.max_crawl_delay:g})",
            )

    def _crawl_delay(self, url: str) -> float:
        robots = self._robots.get(_origin(url))
        if not self.respect_robots or robots is None or isinstance(robots, str):
            return 0.0
        return float(robots.crawl_delay(ROBOTS_AGENT) or 0.0)

    def _robots_for(self, url: str) -> Protego | str | None:
        origin = _origin(url)
        if origin not in self._robots:
            self._robots[origin] = self._load_robots(f"{origin}/robots.txt")
        return self._robots[origin]

    def _load_robots(self, robots_url: str) -> Protego | str | None:
        """RFC 9309: a 4xx allows everything; a 5xx or no answer blocks the site."""
        current = robots_url
        try:
            for _ in range(self.max_redirects + 1):
                if self.policy.refusal(current, check_domains=False) is not None:
                    return None  # a redirect to a refused place: no usable rules
                response = self._get(current, polite=False)
                try:
                    if response.is_redirect and response.headers.get("location"):
                        current = _normalized(response.headers["location"], base=current)
                        continue
                    if 400 <= response.status_code < 500:
                        return None
                    if response.status_code >= 500:
                        return f"robots.txt answered HTTP {response.status_code}"
                    body = self._read(response, current, _MAX_ROBOTS_BYTES)
                    return Protego.parse(body.decode("utf-8", errors="replace"))
                finally:
                    response.close()
        except ScrapeError as exc:
            if "larger than" in exc.reason:
                return None
            return f"robots.txt could not be read: {exc.reason}"
        return None


def _normalized(url: str, base: str | None = None) -> str:
    try:
        return normalize_url(url, base=base)
    except ValueError as exc:
        raise ScrapeError(url, "not a valid URL") from exc


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _retry_after(response: httpx.Response) -> float | None:
    """Seconds to wait before the retry, or None when the server asks for too long."""
    value = response.headers.get("retry-after", "").strip()
    if not value:
        return 1.0
    try:
        wait = float(value)
    except ValueError:
        try:
            wait = (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
        except (TypeError, ValueError):
            return 1.0
    wait = max(wait, 0.0)
    return wait if wait <= _MAX_RETRY_WAIT else None
