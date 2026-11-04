"""Result types of the web scraper."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

_MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_SLUG = re.compile(r"[^a-z0-9]+")


@dataclass
class PageLink:
    """A link found on a page.

    ``internal`` is true for a link to the page's own host or to another allowed
    domain: the links a crawl may follow.
    """

    url: str
    text: str
    internal: bool


@dataclass
class ScrapedPage:
    """One fetched page as Markdown, with what the page says about itself.

    Attributes:
        url: The URL that was requested.
        final_url: The URL after redirects; cite this one.
        status_code: HTTP status of the final response.
        title: The page title.
        description: The meta or Open Graph description.
        language: The ``lang`` of the ``<html>`` element.
        published: The publication or update date the page states, ``YYYY-MM-DD``.
        canonical_url: The page's ``rel=canonical`` URL, when it names one.
        markdown: The main content as Markdown, without navigation and footers.
        links: Every distinct http(s) link on the page, in page order.
        structured_data: JSON-LD objects the page publishes (schema.org).
        depth: Link steps from the crawl's start page; 0 for the start page.
        parent_url: The page whose link led here; ``None`` for the start page.
        rendered: Whether the page was rendered in a browser (JavaScript run).
        fetched_at: When the page was fetched, ISO 8601 in UTC.
        elapsed_s: Seconds spent fetching and reading the page.
    """

    url: str
    final_url: str
    status_code: int
    title: str | None
    description: str | None
    language: str | None
    published: str | None
    canonical_url: str | None
    markdown: str
    links: list[PageLink] = field(default_factory=list)
    structured_data: list[dict] = field(default_factory=list)
    depth: int = 0
    parent_url: str | None = None
    rendered: bool = False
    fetched_at: str = ""
    elapsed_s: float = 0.0

    @property
    def word_count(self) -> int:
        """Words in the Markdown, counting each link by its text."""
        return len(_MARKDOWN_LINK.sub(r"\1", self.markdown).split())

    @property
    def internal_links(self) -> list[PageLink]:
        return [link for link in self.links if link.internal]

    def to_markdown(self) -> str:
        """The page as a Markdown document headed by its title and source URL."""
        heading = self.title or self.final_url
        return f"# {heading}\n\nSource: {self.final_url}\n\n{self.markdown}".rstrip() + "\n"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["word_count"] = self.word_count
        return data


@dataclass
class SkippedPage:
    """A URL the scraper tried but did not turn into a page, and why."""

    url: str
    reason: str
    depth: int = 0
    parent_url: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CrawlResult:
    """The pages of one crawl, in the order they were fetched."""

    start_url: str
    pages: list[ScrapedPage] = field(default_factory=list)
    skipped: list[SkippedPage] = field(default_factory=list)
    duration_s: float = 0.0

    @property
    def word_count(self) -> int:
        return sum(page.word_count for page in self.pages)

    def to_markdown(self, max_chars_per_page: int | None = None) -> str:
        """Every page as one Markdown document, each headed by its source URL.

        This is the text to hand an extractor or a RAG index: the ``Source:`` line of
        each section lets an answer cite the page it came from.
        """
        sections = []
        for page in self.pages:
            text = page.to_markdown()
            if max_chars_per_page is not None and len(text) > max_chars_per_page:
                text = text[:max_chars_per_page].rstrip() + "\n\n[…]\n"
            sections.append(text)
        return "\n---\n\n".join(sections)

    def to_dict(self) -> dict:
        return {
            "start_url": self.start_url,
            "duration_s": self.duration_s,
            "pages": [page.to_dict() for page in self.pages],
            "skipped": [page.to_dict() for page in self.skipped],
        }

    def save(self, directory: str | Path) -> dict[str, Path]:
        """Write ``pages/NN-<slug>.md`` for each page and ``crawl.json`` for all.

        Returns a mapping of logical name to written path.
        """
        directory = Path(directory)
        pages_dir = directory / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        written: dict[str, Path] = {}
        for number, page in enumerate(self.pages, start=1):
            path = pages_dir / f"{number:02d}-{_slug(page.final_url)}.md"
            path.write_text(page.to_markdown(), encoding="utf-8", newline="\n")
            written[page.final_url] = path
        crawl_json = directory / "crawl.json"
        crawl_json.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        written["crawl.json"] = crawl_json
        return written


def _slug(url: str) -> str:
    parts = urlsplit(url)
    slug = _SLUG.sub("-", f"{parts.hostname or ''}{parts.path}".lower()).strip("-")
    return slug[:80] or "page"
