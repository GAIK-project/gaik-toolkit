# Web Scraper

Fetches web pages, or crawls one site breadth-first, and returns each page as clean
Markdown with its title, description, language, date, links and JSON-LD. The
Markdown is ready for an LLM: hand `to_model_text()` to the extractor, a RAG index or
a report writer, each page in a block headed by the URL it came from and marked as
data, not instructions.

- **Main content only.** [trafilatura](https://github.com/adbar/trafilatura) separates
  the article from navigation, cookie banners and footers.
- **Safe by default.** `allowed_domains` is required (or an explicit
  `allow_any_domain=True`). Every request, redirect hop included, stays inside those
  domains and never reaches a private, loopback or link-local address (cloud metadata
  endpoints, services inside your cluster): the host is resolved once, every address
  it resolves to is checked, and the connection goes to a checked address.
- **Polite.** robots.txt is obeyed (wildcards and `Crawl-delay` via
  [protego](https://github.com/scrapy/protego)), requests to one host are spaced by
  `delay_seconds`, and the `User-Agent` names the toolkit.
- **JavaScript when needed.** `render_js=True` renders pages in headless Chromium;
  `render_js="auto"` does so only for pages whose HTML holds almost no text.

## Installation

```bash
pip install "gaik[web-scraper]"

# Optional: JavaScript rendering
pip install "gaik[web-scraper-browser]"
playwright install chromium
```

The component makes no LLM calls itself. Extraction from the scraped Markdown uses
the extractor, which works with any provider from `get_llm_config()`.

---

## Quick Start

```python
from gaik.software_components.web_scraper import WebScraper

with WebScraper(allowed_domains=["gaik.ai"]) as scraper:
    page = scraper.scrape("https://gaik.ai/news-events/")
    print(page.title, page.language, page.word_count)
    print(page.markdown[:500])

    result = scraper.crawl("https://gaik.ai/", max_pages=10, max_depth=2)

result.save("output/gaik-site")        # pages/NN-<slug>.md + crawl.json
document = result.to_markdown()        # one document, a "Source: <url>" per page
for_model = result.to_model_text()     # the same pages, each in a <web_page> block
```

### Stream a crawl

`iter_crawl` yields each page as soon as it is fetched, and a `SkippedPage` (with a
reason) for each URL that failed. Stop iterating to stop the crawl.

```python
from gaik.software_components.web_scraper import ScrapedPage, WebScraper

with WebScraper(allowed_domains=["haaga-helia.fi"]) as scraper:
    for item in scraper.iter_crawl(
        "https://www.haaga-helia.fi/fi/koulutus",
        max_pages=20,
        include_patterns=["/fi/koulutus*"],
    ):
        if isinstance(item, ScrapedPage):
            print("page", item.final_url, item.title)
        else:
            print("skip", item.url, item.reason)
```

### Extract structured data from a site

```python
from gaik.software_components.extractor import DataExtractor, SchemaGenerator
from gaik.software_components.llm import get_llm_config

requirements = "List every event: title, date (YYYY-MM-DD), and the source page URL."
config = get_llm_config()
generator = SchemaGenerator(config=config)
schema = generator.generate_schema(user_requirements=requirements)
records = DataExtractor(config=config).extract(
    extraction_model=schema,
    requirements=generator.item_requirements,
    user_requirements=requirements,
    documents=[result.to_model_text(max_chars_per_page=6000)],
)
```

`to_model_text()` puts each page in a `<web_page id="..." source="..." title="...">`
block that ends at `</web_page id="...">`, after one line telling the model that the
blocks hold fetched data, not instructions. The `id` is derived from the page text,
so a page cannot write its own block's closing tag, and a `<web_page` or `</web_page`
tag in its text is escaped. `max_chars_per_page` cuts the page body, never the
heading or `Source:` line. `markdown` and `to_markdown()` are left as fetched.

---

## API

### WebScraper

| Argument | Default | Meaning |
|----------|---------|---------|
| `allowed_domains` | required | Domains that may be fetched; a domain allows its subdomains. Leaving it out raises `ValueError` unless `allow_any_domain=True`. |
| `respect_robots` | `True` | Obey robots.txt (RFC 9309). A robots.txt that answers 5xx blocks the site. |
| `render_js` | `False` | `True`, `False` or `"auto"`. Needs the `web-scraper-browser` extra. |
| `extraction` | `"balanced"` | `"precision"`, `"balanced"` or `"recall"`: how strictly boilerplate is dropped. |
| `delay_seconds` | `0.5` | Least time between requests to one host. |
| `max_crawl_delay` | `30.0` | A site whose robots.txt asks for a longer `Crawl-delay` is skipped. |
| `timeout_seconds` | `20.0` | Timeout of one request. |
| `max_page_bytes` | `5_000_000` | Largest page read, after decompression. |
| `max_redirects` | `5` | Most redirects followed per URL; each hop is checked. |
| `user_agent` | toolkit name | The `User-Agent` header. robots.txt rules match the token `GAIKWebScraper`. |
| `allow_private_networks` | `False` | Allow hosts that resolve to private or local addresses (an intranet). |
| `allow_any_domain` | `False` | Fetch from every public host without a domain list. For scripts whose URLs you choose yourself, never for URLs from users. Cannot be combined with `allowed_domains`. |
| `transport` | `None` | An `httpx` transport, for tests or a proxy. The default, `VettedAddressTransport`, connects only to the addresses the policy checked; `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` and `NO_PROXY` are honoured as httpx would. Your own transport does its own name lookup (the address check still runs before each request). |

Methods:

- `scrape(url) -> ScrapedPage` raises `ScrapeError` (with `.reason`) when the page
  cannot be fetched.
- `iter_crawl(start_url, *, max_pages=10, max_depth=2, include_patterns=None,
  exclude_patterns=None, stay_on_host=True, on_request=None)` yields `ScrapedPage`
  and `SkippedPage`. Patterns are shell patterns on the URL path and query
  (`"/fi/news/*"`). Links to files (PDF, images, archives, office documents) are not
  followed.
- `crawl(start_url, *, max_pages=10, max_depth=2, ...) -> CrawlResult` takes the same arguments and collects `iter_crawl`.

### Results

- `ScrapedPage`: `url`, `final_url`, `status_code`, `title`, `description`,
  `language`, `published`, `canonical_url`, `markdown`, `links` (`PageLink` with
  `url`, `text`, `internal`), `structured_data` (JSON-LD), `depth`, `parent_url`,
  `rendered`, `fetched_at`, `elapsed_s`, and `word_count`. `to_markdown()` heads the
  page with its title and `Source:` URL; `to_model_text(max_chars)` puts that in a
  `<web_page>` block marked as data.
- `CrawlResult`: `pages`, `skipped`, `duration_s`, `to_markdown(max_chars_per_page)`,
  `to_model_text(max_chars_per_page)`, `to_dict()`, `save(directory)`.

## Limits

- Each host's checked addresses are kept for five minutes
  (`policy.ADDRESS_TTL_SECONDS`); after that the name is looked up and checked
  again, so a long-running scraper follows a host that moved.
- With `render_js`, Chromium resolves names itself: every browser request is still
  checked against the policy, but it is not held to the checked address. The same
  holds for a custom `transport` and for a proxy from `HTTP_PROXY`/`HTTPS_PROXY`:
  the proxy connects to the site itself.
- The block marking in `to_model_text()` tells a model what is data; it does not make
  a model ignore a page's text. Keep a person's review or a schema check on what a
  model produces from scraped pages.
- The scraper is synchronous and not thread-safe; use one per thread. Playwright's
  sync API does not run in a thread with a running asyncio loop, so call
  `render_js` scrapers from a worker thread in an async server.
- Only HTML pages are read. Use the parsers for PDFs and office files.

See the [example](../../../../examples/software_components/web_scraper/web_scraper_example.py)
for a complete script.

## License

MIT - see [LICENSE](../../../../../LICENSE)
