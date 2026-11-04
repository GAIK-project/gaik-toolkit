"""Web Scraper Example

Crawls a few pages of gaik.ai into Markdown and saves them, then (with --extract)
pulls the upcoming GAIK events out of the pages with the schema generator and the
extractor. Scraping needs no credentials; extraction uses the LLM provider in your
.env (LLM_PROVIDER, default Azure).

Usage:
    python web_scraper_example.py             # crawl and save only
    python web_scraper_example.py --extract   # also extract structured data
    python web_scraper_example.py --render    # render pages in headless Chromium
                                              # (needs gaik[web-scraper-browser])
"""

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Allow running without `pip install -e .`
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.web_scraper import (  # noqa: E402
    CrawlResult,
    ScrapedPage,
    WebScraper,
)

START_URL = "https://gaik.ai/"
OUTPUT_DIR = Path(__file__).parent / "output"


def crawl_example(render: bool = False) -> CrawlResult:
    """Crawl five pages of gaik.ai, printing each page as it arrives."""
    with WebScraper(allowed_domains=["gaik.ai"], render_js=render) as scraper:
        result = CrawlResult(start_url=START_URL)
        for item in scraper.iter_crawl(START_URL, max_pages=5, max_depth=1):
            if isinstance(item, ScrapedPage):
                result.pages.append(item)
                print(f"page  {item.final_url}  {item.title!r}  {item.word_count} words")
            else:
                result.skipped.append(item)
                print(f"skip  {item.url}  ({item.reason})")

    paths = result.save(OUTPUT_DIR / "gaik-site")
    print(f"\nSaved {len(paths) - 1} pages and crawl.json to {OUTPUT_DIR / 'gaik-site'}")
    return result


def single_page_example() -> None:
    """One page, with what it says about itself."""
    with WebScraper(allowed_domains=["gaik.ai"]) as scraper:
        page = scraper.scrape("https://gaik.ai/news-events/")
    print(f"\n{page.title} ({page.language}, {page.published})")
    print(f"{len(page.internal_links)} internal links, {len(page.structured_data)} JSON-LD objects")
    print(page.markdown[:600])


def extraction_example(result: CrawlResult) -> None:
    """Turn the crawled Markdown into structured records with the extractor."""
    from gaik.software_components.extractor import DataExtractor, SchemaGenerator
    from gaik.software_components.llm import get_llm_config

    requirements = (
        "List every event or workshop mentioned: its title, date (YYYY-MM-DD), "
        "time, and the source page URL from the 'Source:' line above it."
    )
    config = get_llm_config()
    generator = SchemaGenerator(config=config)
    schema = generator.generate_schema(user_requirements=requirements)
    records = DataExtractor(config=config).extract(
        extraction_model=schema,
        requirements=generator.item_requirements,
        user_requirements=requirements,
        documents=[result.to_markdown(max_chars_per_page=6000)],
    )
    print(json.dumps(records, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    crawled = crawl_example(render="--render" in sys.argv)
    single_page_example()
    if "--extract" in sys.argv:
        extraction_example(crawled)
