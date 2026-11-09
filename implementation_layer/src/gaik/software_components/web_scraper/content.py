"""Turn a fetched HTML page into Markdown, metadata, links and JSON-LD.

trafilatura finds the main content and writes it as Markdown, so navigation, cookie
banners and footers stay out of the text an LLM reads. Links and JSON-LD are read
from the whole page with lxml: the links drive a crawl, and JSON-LD is the
structured data (events, courses, organisations) a site publishes for search
engines.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal

try:
    import lxml.html
    import trafilatura
    from lxml import etree
    from trafilatura import extract_metadata
except ImportError as exc:  # pragma: no cover - depends on the installed extra
    raise ImportError(
        "WebScraper needs the web-scraper extra: pip install 'gaik[web-scraper]'"
    ) from exc

from .models import PageLink
from .policy import UrlPolicy, host_of, normalize_url

Extraction = Literal["precision", "balanced", "recall"]

_LINK_TEXT = re.compile(r"\[([^\]]*)\]\(")
_BLANK_LINES = re.compile(r"\n{3,}")
_SPACES = re.compile(r"\s+")
_META_CHARSET = re.compile(rb"""<meta[^>]+charset=["']?([A-Za-z0-9._-]+)""", re.IGNORECASE)
_SKIPPED_SCHEMES = ("mailto:", "tel:", "javascript:", "data:", "sms:", "ftp:")
_MAX_LINKS = 500
_MAX_JSON_LD = 20


@dataclass
class PageContent:
    """What one HTML page holds, before it becomes a ScrapedPage."""

    title: str | None
    description: str | None
    language: str | None
    published: str | None
    canonical_url: str | None
    markdown: str
    links: list[PageLink] = field(default_factory=list)
    structured_data: list[dict] = field(default_factory=list)


def decode_html(body: bytes, content_type: str) -> str:
    """The page as text: the charset of the Content-Type header, else of a <meta>
    tag, else UTF-8 with undecodable bytes replaced."""
    charset = None
    match = re.search(r"charset=([^\s;]+)", content_type, re.IGNORECASE)
    if match:
        charset = match.group(1).strip("\"'")
    else:
        meta = _META_CHARSET.search(body[:4096])
        if meta:
            charset = meta.group(1).decode("ascii", "replace")
    try:
        return body.decode(charset or "utf-8", errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _collapse(text: str | None) -> str:
    return _SPACES.sub(" ", text or "").strip()


def clean_markdown(markdown: str) -> str:
    """Markdown with link texts on one line and at most one blank line in a row."""

    def one_line(match: re.Match) -> str:
        return f"[{_collapse(match.group(1))}]("

    markdown = _LINK_TEXT.sub(one_line, markdown)
    markdown = "\n".join(line.rstrip() for line in markdown.splitlines())
    return _BLANK_LINES.sub("\n\n", markdown).strip()


def _markdown(html: str, url: str, extraction: Extraction) -> str:
    def run(precision: bool, recall: bool) -> str:
        return (
            trafilatura.extract(
                html,
                url=url,
                output_format="markdown",
                include_links=True,
                include_tables=True,
                include_formatting=True,
                include_images=False,
                include_comments=False,
                favor_precision=precision,
                favor_recall=recall,
                deduplicate=False,
            )
            or ""
        )

    markdown = run(extraction == "precision", extraction == "recall")
    if not markdown.strip() and extraction != "recall":
        # A page of short blocks (a home page of link cards) can fall below the
        # precision thresholds; recall keeps them rather than return nothing.
        markdown = run(False, True)
    return clean_markdown(markdown)


def _links(tree, page_url: str, policy: UrlPolicy) -> list[PageLink]:
    page_host = host_of(page_url)
    links: dict[str, PageLink] = {}
    for anchor in tree.iter("a"):
        href = (anchor.get("href") or "").strip()
        if not href or href.startswith("#") or href.lower().startswith(_SKIPPED_SCHEMES):
            continue
        try:
            url = normalize_url(href, base=page_url)
        except ValueError:
            continue
        if not url.startswith(("http://", "https://")) or url in links:
            continue
        host = host_of(url)
        internal = host == page_host or (
            policy.allowed_domains is not None and policy.in_allowed_domains(url)
        )
        links[url] = PageLink(
            url=url, text=_collapse(anchor.text_content())[:200], internal=internal
        )
        if len(links) >= _MAX_LINKS:
            break
    return list(links.values())


def _json_ld(tree) -> list[dict]:
    items: list[dict] = []
    for script in tree.xpath('//script[@type="application/ld+json"]'):
        try:
            data = json.loads(script.text_content() or "")
        except (json.JSONDecodeError, ValueError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if isinstance(item, dict) and isinstance(item.get("@graph"), list):
                items.extend(node for node in item["@graph"] if isinstance(node, dict))
            elif isinstance(item, dict):
                items.append(item)
        if len(items) >= _MAX_JSON_LD:
            break
    return items[:_MAX_JSON_LD]


def _meta(tree, *names: str) -> str | None:
    for name in names:
        for attr in ("name", "property"):
            values = tree.xpath(f'//meta[@{attr}="{name}"]/@content')
            if values and _collapse(values[0]):
                return _collapse(values[0])
    return None


def _page_url(url: str, page_url: str) -> str | None:
    """A URL the page states about itself (its base or canonical); None when malformed.

    A page is still read when its ``<base>`` or canonical link is not a URL.
    """
    try:
        return normalize_url(url, base=page_url)
    except ValueError:
        return None


def read_page(
    html: str, page_url: str, policy: UrlPolicy, extraction: Extraction = "balanced"
) -> PageContent:
    """Read an HTML page fetched from ``page_url`` (the URL after redirects)."""
    try:
        tree = lxml.html.fromstring(html)
    except (etree.ParserError, ValueError):
        return PageContent(None, None, None, None, None, "")

    # Read the links and JSON-LD first: trafilatura prunes the tree it is given, so
    # it gets the HTML text and parses its own copy.
    base = tree.xpath("//base/@href")
    links = _links(tree, (_page_url(base[0], page_url) if base else None) or page_url, policy)
    structured_data = _json_ld(tree)
    canonical = tree.xpath('//link[@rel="canonical"]/@href')
    language = _collapse(tree.get("lang")) or _meta(tree, "og:locale") or None
    title = _collapse(tree.findtext(".//title")) or None
    description = _meta(tree, "description", "og:description")

    metadata = extract_metadata(html, default_url=page_url, extensive=False)
    return PageContent(
        title=(metadata.title if metadata else None) or title,
        description=(metadata.description if metadata else None) or description,
        language=language,
        published=metadata.date if metadata else None,
        canonical_url=_page_url(canonical[0], page_url) if canonical else None,
        markdown=_markdown(html, page_url, extraction),
        links=links,
        structured_data=structured_data,
    )
