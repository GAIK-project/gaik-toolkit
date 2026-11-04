"""Web Scraper router: crawl an allowed site, then extract structured data from it.

``POST /web-scraper/run`` streams Server-Sent Events while gaik's WebScraper crawls,
one event per page as it arrives. When the request carries requirements, the schema
generator and the extractor then turn the pages into records, each value with a
quote checked against the page text and the URL of the page it came from.

Only the domains in ``WEB_SCRAPER_ALLOWED_DOMAINS`` (default gaik.ai and
haaga-helia.fi) can be scraped, on every redirect hop: the demo is not an open proxy.
Nothing is stored.

gaik is imported inside the worker: the image installs gaik from PyPI, so a release
without ``web_scraper`` breaks only this router, not the whole API.
"""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import logging
import os
import queue
import re
import threading
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, create_model

try:
    from utils import (
        get_api_config,
        get_model_options,
        sse_event,
        wrap_schema_with_numeric_normalizers,
    )
    from utils.citations import ask_for_sources, trace_text_results
    from utils.field_names import field_name_mapping, rename_described_fields, rename_keys
    from utils.model_settings import provider_error_detail
    from utils.schema_view import schema_summary
    from utils.session_schemas import shorten_schema_name
except ImportError:
    from api.utils import (
        get_api_config,
        get_model_options,
        sse_event,
        wrap_schema_with_numeric_normalizers,
    )
    from api.utils.citations import ask_for_sources, trace_text_results
    from api.utils.field_names import field_name_mapping, rename_described_fields, rename_keys
    from api.utils.model_settings import provider_error_detail
    from api.utils.schema_view import schema_summary
    from api.utils.session_schemas import shorten_schema_name

logger = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_DOMAINS = tuple(
    domain.strip().lower()
    for domain in os.getenv("WEB_SCRAPER_ALLOWED_DOMAINS", "gaik.ai,haaga-helia.fi").split(",")
    if domain.strip()
)
SITES = [
    {
        "id": "gaik",
        "label": "GAIK project",
        "url": "https://gaik.ai/",
        "domain": "gaik.ai",
        "description": "The project site: toolkit, use cases, news and events",
    },
    {
        "id": "haaga-helia",
        "label": "Haaga-Helia",
        "url": "https://www.haaga-helia.fi/fi",
        "domain": "haaga-helia.fi",
        "description": "The university of applied sciences: degrees, research and news",
    },
]
MAX_PAGES = 12
MAX_DEPTH = 2
# Each page's share of the text the extractor reads, and the whole text's ceiling.
MAX_CHARS_PER_PAGE = 6000
MAX_EVENT_MARKDOWN = 6000
MAX_EVENT_LINKS = 150
# Crawls at once on one API pod: each holds a thread and a connection pool.
_running = threading.BoundedSemaphore(int(os.getenv("WEB_SCRAPER_MAX_RUNNING", "3")))
# Schemas made for a requirements text, so a preset runs its schema step once.
_schema_cache: dict[str, tuple[Any, Any]] = {}
_SCHEMA_CACHE_LIMIT = 32

TASK_CONTEXT = (
    "The text is a set of web pages. Each page starts with a '# <title>' heading and a "
    "'Source: <url>' line; when a field asks for a URL or a source page, use that URL."
)


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=8, max_length=500)
    max_pages: int = Field(default=6, ge=1, le=MAX_PAGES)
    max_depth: int = Field(default=1, ge=0, le=MAX_DEPTH)
    include_pattern: str | None = Field(default=None, max_length=200)
    requirements: str | None = Field(default=None, max_length=2000)


@router.get("/sites")
async def sites():
    """The sites the demo may scrape, and the run limits."""
    return {
        "allowed_domains": list(ALLOWED_DOMAINS),
        "sites": [site for site in SITES if site["domain"] in ALLOWED_DOMAINS],
        "limits": {"max_pages": MAX_PAGES, "max_depth": MAX_DEPTH},
    }


def _page_event(page) -> dict:
    markdown = page.markdown
    if len(markdown) > MAX_EVENT_MARKDOWN:
        markdown = markdown[:MAX_EVENT_MARKDOWN].rstrip() + "\n\n[…]"
    types = sorted(
        {
            str(t)
            for item in page.structured_data
            for t in (
                item.get("@type") if isinstance(item.get("@type"), list) else [item.get("@type")]
            )
            if t
        }
    )
    return {
        "url": page.url,
        "final_url": page.final_url,
        "title": page.title,
        "description": page.description,
        "language": page.language,
        "published": page.published,
        "depth": page.depth,
        "parent_url": page.parent_url,
        "word_count": page.word_count,
        "elapsed_s": page.elapsed_s,
        "markdown": markdown,
        "links": [link.url for link in page.internal_links][:MAX_EVENT_LINKS],
        "external_links": sum(1 for link in page.links if not link.internal),
        "structured_data_types": types,
    }


def _page_of(document: str, pages: list, position: int) -> str | None:
    """The URL of the page whose section of ``document`` holds ``position``."""
    owner = None
    start = 0
    for page in pages:
        marker = document.find(f"Source: {page.final_url}\n", start)
        if marker == -1 or marker > position:
            break
        owner, start = page.final_url, marker + 1
    return owner


def _named_fields(schema: type[BaseModel]) -> type[BaseModel]:
    """The schema with every top-level field name a usable snake_case identifier.

    Works around gaik's nested-list schema path, which takes the container name from
    the model's structure analysis as it is: an empty name gives a field called "",
    whose records the page cannot show or cite. The parent-with-children path already
    sanitizes its names.
    """
    fields = schema.model_fields
    if all(re.fullmatch(r"[a-z][a-z0-9_]*", name) for name in fields):
        return schema
    renamed: dict[str, Any] = {}
    for name, info in fields.items():
        clean = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
        if not re.match(r"[a-z]", clean):
            clean = f"records_{clean}".strip("_")
        while clean in renamed:
            clean += "_"
        renamed[clean] = (info.annotation, info)
    return create_model(
        schema.__name__,
        __config__=schema.model_config,
        __doc__=schema.__doc__,
        **renamed,
    )


def _schema_for(config: dict, requirements: str):
    """The schema and item requirements for this requirements text, made once."""
    from gaik.software_components.extractor import SchemaGenerator

    key = hashlib.sha256(requirements.strip().encode("utf-8")).hexdigest()
    if key not in _schema_cache:
        generator = SchemaGenerator(config, model=config["model"], **get_model_options(config))
        schema = shorten_schema_name(
            wrap_schema_with_numeric_normalizers(
                _named_fields(generator.generate_schema(user_requirements=requirements))
            )
        )
        if len(_schema_cache) >= _SCHEMA_CACHE_LIMIT:
            _schema_cache.pop(next(iter(_schema_cache)))
        _schema_cache[key] = (schema, generator.item_requirements)
    return _schema_cache[key]


@router.post("/run")
async def run(request: RunRequest):
    """Crawl the site and, with ``requirements``, extract records. Returns an SSE stream.

    Events:
        ``request``     {url, depth, parent_url}           — a page is being fetched
        ``page``        {url, final_url, title, ..., links} — a page arrived
        ``skipped``     {url, reason, depth, parent_url}
        ``crawl_done``  {pages, skipped, words, duration_s}
        ``progress``    {stage, message}                    — schema and extraction steps
        ``schema``      {schema_name, field_table, structure_type}
        ``result``      {records, sources, document_chars}
        ``error``       {message}
    """
    from gaik.software_components.web_scraper import UrlPolicy, normalize_url

    try:
        start_url = normalize_url(request.url)
    except ValueError as exc:
        raise HTTPException(400, "Not a valid URL") from exc
    if not UrlPolicy(ALLOWED_DOMAINS).in_allowed_domains(start_url) or not start_url.startswith(
        ("http://", "https://")
    ):
        raise HTTPException(
            400,
            f"This demo scrapes only {', '.join(ALLOWED_DOMAINS)}. Pick one of those sites.",
        )
    requirements = (request.requirements or "").strip()
    # Read the per-request model settings here: the worker thread does not see them.
    config = get_api_config() if requirements else None
    if not _running.acquire(blocking=False):
        raise HTTPException(429, "Too many crawls are running. Try again in a moment.")

    events: queue.Queue[tuple[str, dict]] = queue.Queue()
    done = threading.Event()
    cancelled = threading.Event()

    def emit(kind: str, data: dict) -> None:
        if cancelled.is_set():
            raise RuntimeError("Cancelled by the client")
        events.put((kind, data))

    def work() -> None:
        try:
            from gaik.software_components.web_scraper import (
                CrawlResult,
                ScrapedPage,
                WebScraper,
            )

            result = CrawlResult(start_url=start_url)
            started = time.monotonic()
            with WebScraper(
                ALLOWED_DOMAINS, delay_seconds=0.4, timeout_seconds=15, max_page_bytes=3_000_000
            ) as scraper:
                crawl = scraper.iter_crawl(
                    start_url,
                    max_pages=request.max_pages,
                    max_depth=request.max_depth,
                    include_patterns=[request.include_pattern] if request.include_pattern else None,
                    on_request=lambda url, depth, parent: emit(
                        "request", {"url": url, "depth": depth, "parent_url": parent}
                    ),
                )
                for item in crawl:
                    if isinstance(item, ScrapedPage):
                        result.pages.append(item)
                        emit("page", _page_event(item))
                    else:
                        result.skipped.append(item)
                        emit("skipped", item.to_dict())
            emit(
                "crawl_done",
                {
                    "pages": len(result.pages),
                    "skipped": len(result.skipped),
                    "words": result.word_count,
                    "duration_s": round(time.monotonic() - started, 2),
                },
            )
            if not requirements or not result.pages:
                return

            from gaik.software_components.extractor import DataExtractor

            emit("progress", {"stage": "schema", "message": "Designing the extraction schema"})
            schema, item_requirements = _schema_for(config, requirements)
            mapping = field_name_mapping(schema, requirements)
            summary = schema_summary(schema, item_requirements, requirements)
            emit(
                "schema",
                {
                    "schema_name": summary["schema_name"],
                    "structure_type": summary["structure_type"],
                    "field_table": rename_described_fields(summary["field_table"], mapping),
                },
            )

            document = result.to_markdown(max_chars_per_page=MAX_CHARS_PER_PAGE)
            emit(
                "progress",
                {
                    "stage": "extract",
                    "message": f"Reading {len(result.pages)} pages ({len(document):,} characters)",
                },
            )
            traced_model, traced_task = ask_for_sources(schema, f"{requirements}\n\n{TASK_CONTEXT}")
            extractor = DataExtractor(config, model=config["model"], **get_model_options(config))
            records = extractor.extract(
                extraction_model=traced_model,
                requirements=item_requirements,
                user_requirements=traced_task,
                documents=[document],
            )
            traced = trace_text_results(records, document)
            sources = traced["sources"] if traced else []
            for source in sources:
                span = source.get("span")
                source["page_url"] = _page_of(document, result.pages, span[0]) if span else None
            emit(
                "result",
                {
                    "records": rename_keys(records, mapping),
                    "sources": [
                        {**s, "field": _renamed_path(s["field"], mapping)} for s in sources
                    ],
                    "document_chars": len(document),
                    "model": config.get("model"),
                },
            )
        except Exception as exc:
            if cancelled.is_set():
                return
            logger.exception("Web scraper run failed")
            events.put(("error", {"message": provider_error_detail(exc)}))
        finally:
            _running.release()
            done.set()

    # The worker runs in a copy of the request context, so the per-request model
    # settings and the credential redaction in utils.model_settings apply there too.
    context = contextvars.copy_context()
    threading.Thread(target=context.run, args=(work,), daemon=True).start()

    async def event_stream():
        loop = asyncio.get_running_loop()
        last_heartbeat = loop.time()
        try:
            while not done.is_set() or not events.empty():
                try:
                    kind, data = events.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.05)
                    if loop.time() - last_heartbeat > 15:
                        yield ": heartbeat\n\n"  # keeps proxy connections open
                        last_heartbeat = loop.time()
                    continue
                yield sse_event(kind, data)
            yield sse_event("done", {})
        finally:
            # A closed stream means the client left: the worker stops at its next event.
            cancelled.set()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


def _renamed_path(path: str, mapping: dict[str, str]) -> str:
    """A citation path such as ``events[0].title`` with the field names restored."""
    return re.sub(r"[A-Za-z_][A-Za-z0-9_]*", lambda m: mapping.get(m.group(0), m.group(0)), path)
