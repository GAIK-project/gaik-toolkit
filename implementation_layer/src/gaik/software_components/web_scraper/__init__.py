"""Web Scraper

Fetches web pages, or crawls one site breadth-first, and returns each page as clean
Markdown with its title, description, language, date, links and JSON-LD. Every
request stays inside a domain allowlist and public addresses, obeys robots.txt and
waits between requests to the same host. Optional headless Chromium rendering covers
sites that build their content with JavaScript.

Hand ``CrawlResult.to_model_text()`` to the extractor, a prompt or a RAG index:
each page sits in a ``<web_page source="...">`` block marked as data, not
instructions, headed by the URL it came from. ``to_markdown()`` gives the same
pages without the marking.

Main Classes:
    - WebScraper: Fetch pages and crawl sites
    - ScrapedPage: One page as Markdown with its metadata and links
    - CrawlResult: The pages of a crawl, as one Markdown document or saved files
    - SkippedPage: A URL that was tried but not scraped, with the reason
    - UrlPolicy: The allowlist and private-address checks
    - VettedAddressTransport: The HTTP transport that connects only to checked addresses
    - ScrapeError: Raised by ``WebScraper.scrape`` with the reason

Example:
    >>> from gaik.software_components.web_scraper import WebScraper
    >>> with WebScraper(allowed_domains=["gaik.ai"]) as scraper:
    ...     result = scraper.crawl("https://gaik.ai/", max_pages=5)
    >>> result.save("output/gaik-site")
"""

from .browser import browser_available
from .connect import VettedAddressTransport
from .models import MODEL_TEXT_NOTICE, CrawlResult, PageLink, ScrapedPage, SkippedPage
from .policy import ScrapeError, UrlPolicy, normalize_url
from .web_scraper import DEFAULT_USER_AGENT, ROBOTS_AGENT, WebScraper

__all__ = [
    "WebScraper",
    "ScrapedPage",
    "PageLink",
    "SkippedPage",
    "CrawlResult",
    "UrlPolicy",
    "VettedAddressTransport",
    "MODEL_TEXT_NOTICE",
    "ScrapeError",
    "normalize_url",
    "browser_available",
    "DEFAULT_USER_AGENT",
    "ROBOTS_AGENT",
]

__version__ = "0.1.0"
