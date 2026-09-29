"""Knowledge Curator router: curate fact units from normalized sources, and verify quotes.

``/run`` curates every section with gaik's KnowledgeCurator and returns the
``knowledge/<section_id>.json`` files as text. ``/verify`` re-checks the quotes of
(possibly hand-edited) knowledge files against the normalized sources; it calls no model.
The client keeps the files between requests, so nothing is stored on the server.

gaik is imported inside the handlers (``_gaik``): the image installs gaik from PyPI, so a
release without the curator's drop-unverified support breaks only this router.
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import re
import threading
from types import SimpleNamespace
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

try:
    from utils import get_api_config, sse_event
except ImportError:
    from api.utils import get_api_config, sse_event

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_SECTIONS = 12
_NORMALIZED = re.compile(r"normalized/[\w.-]+\.md|normalized/sources\.json", re.ASCII)
_KNOWLEDGE = re.compile(r"knowledge/[\w.-]+\.json", re.ASCII)
_FILES = TypeAdapter(dict[str, str])


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z0-9_-]+$", max_length=64)
    title: str = Field(min_length=1, max_length=200)
    instructions: str = Field(default="", max_length=5000)
    required_items: list[str] = Field(default=[], max_length=50)


class _Options(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str | None = Field(default=None, max_length=100)
    reasoning_effort: Literal["minimal", "low", "medium", "high"] | None = None
    max_workers: int = Field(default=4, ge=1, le=8)


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sections: list[_Section] = Field(min_length=1, max_length=MAX_SECTIONS)
    instructions: str = Field(default="", max_length=10000)
    options: _Options = _Options()


def _errors(exc: ValidationError) -> str:
    """The validation errors without the submitted values."""
    return "; ".join(
        f"{'.'.join(map(str, e['loc'])) or 'input'}: {e['msg']}"
        for e in exc.errors(include_input=False, include_url=False)
    )


def _gaik():
    """gaik's curator components, imported per request (see the module docstring)."""
    from gaik.software_components.knowledge_curator import (
        KnowledgeBase,
        KnowledgeCurator,
        SectionKnowledge,
        SectionSpec,
    )
    from gaik.software_components.source_normalizer import NormalizedSource, NormalizedSources

    return SimpleNamespace(
        KnowledgeCurator=KnowledgeCurator,
        KnowledgeBase=KnowledgeBase,
        SectionKnowledge=SectionKnowledge,
        SectionSpec=SectionSpec,
        NormalizedSource=NormalizedSource,
        NormalizedSources=NormalizedSources,
    )


async def _read_files(upload: UploadFile, allowed: re.Pattern[str]) -> dict[str, str]:
    """The path-to-text map of an upload, whose paths must match ``allowed``."""
    try:
        files = _FILES.validate_json(await upload.read())
    except ValidationError as exc:
        raise HTTPException(
            400, f"artifacts must be a JSON object of path to text: {_errors(exc)}"
        ) from exc
    if bad := [k for k in files if not allowed.fullmatch(k)]:
        raise HTTPException(400, f"Artifact paths not allowed: {bad}")
    return files


def _normalized_sources(files: dict[str, str]):
    """The NormalizedSources of ``normalized/`` files, as NormalizedSources.save writes them."""
    gaik = _gaik()
    if "normalized/sources.json" not in files:
        raise HTTPException(400, "normalized/sources.json is missing")
    try:
        manifest = json.loads(files["normalized/sources.json"])
        if not isinstance(manifest, list) or not manifest:
            raise ValueError("it must be a non-empty list")
        sources = []
        for entry in manifest:
            path = f"normalized/{entry['id']}.md"
            if path not in files:
                raise ValueError(f"{path} is missing")
            sources.append(gaik.NormalizedSource(**entry, text=files[path]))
        return gaik.NormalizedSources(sources=sources)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, f"Invalid normalized/sources.json: {exc}") from exc


@router.post("/run")
async def run(request: str = Form(...), artifacts: UploadFile = File(...)):
    """Curate the sections. Returns a Server-Sent Events stream.

    ``request`` is JSON: ``{"sections": [{"id", "title", "instructions",
    "required_items"}], "instructions", "options": {"model", "reasoning_effort",
    "max_workers"}}``. ``artifacts`` is a JSON file of the ``normalized/`` files.

    Events:
        ``progress``  {"message": str}  — section starts and ends, dropped facts
        ``result``    {"artifacts": {path: text}, "usage": {...}, "dropped": [...]}
        ``error``     {"message": str}
    """
    gaik = _gaik()
    try:
        parsed = _Request.model_validate_json(request)
    except ValidationError as exc:
        raise HTTPException(400, f"Invalid request: {_errors(exc)}") from exc
    sections = [gaik.SectionSpec(**s.model_dump()) for s in parsed.sections]
    ids = [s.id for s in sections]
    if len(set(ids)) != len(ids):
        raise HTTPException(400, f"Topic ids must be distinct: {ids}")
    sources = _normalized_sources(await _read_files(artifacts, _NORMALIZED))
    config = get_api_config()
    options = parsed.options
    chat_options = (
        {"reasoning_effort": options.reasoning_effort} if options.reasoning_effort else {}
    )

    messages: queue.Queue[str] = queue.Queue()
    outcome: dict = {}
    done = threading.Event()
    cancelled = threading.Event()

    def progress(message: str) -> None:
        if cancelled.is_set():
            raise RuntimeError("Cancelled by the client")
        messages.put(message)

    def work() -> None:
        try:
            knowledge = gaik.KnowledgeCurator(
                config,
                options.model,
                max_workers=options.max_workers,
                chat_options=chat_options,
            ).curate(
                sources,
                sections,
                instructions=parsed.instructions,
                progress_callback=progress,
            )
            outcome["result"] = {
                "artifacts": {
                    f"knowledge/{s.section_id}.json": s.model_dump_json(indent=2)
                    for s in knowledge.sections
                },
                "usage": knowledge.usage,
                # Older gaik releases stop on an unverifiable quote instead of dropping the fact.
                "dropped": [d.model_dump() for d in getattr(knowledge, "dropped", [])],
            }
        except Exception as exc:
            logger.exception("Knowledge Curator failed")
            outcome["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            done.set()

    threading.Thread(target=work, daemon=True).start()

    async def event_stream():
        loop = asyncio.get_running_loop()
        last_heartbeat = loop.time()
        try:
            while not done.is_set() or not messages.empty():
                try:
                    message = messages.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.1)
                    if loop.time() - last_heartbeat > 15:
                        # SSE comment — keeps proxy connections alive
                        yield ": heartbeat\n\n"
                        last_heartbeat = loop.time()
                    continue
                yield sse_event("progress", {"message": message})
            if "error" in outcome:
                yield sse_event("error", {"message": outcome["error"]})
            else:
                yield sse_event("result", outcome["result"])
        finally:
            # A closed or cancelled stream means the client left: stop at the next message.
            cancelled.set()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.post("/verify")
async def verify(artifacts: UploadFile = File(...)):
    """Check every quote of the knowledge files against the normalized sources.

    ``artifacts`` is a JSON file holding the ``normalized/`` and ``knowledge/`` files.
    Returns ``{"units": n, "failures": [{"section_id", "unit_id", "file", "quote",
    "reason"}]}``; no failures means every quote occurs verbatim in its source.
    """
    gaik = _gaik()
    files = await _read_files(artifacts, re.compile(f"{_NORMALIZED.pattern}|{_KNOWLEDGE.pattern}"))
    sources = _normalized_sources({k: v for k, v in files.items() if k.startswith("normalized/")})
    knowledge_files = {k: v for k, v in files.items() if k.startswith("knowledge/")}
    if not knowledge_files:
        raise HTTPException(400, "No knowledge files to verify")
    sections = []
    for path, text in sorted(knowledge_files.items()):
        try:
            sections.append(gaik.SectionKnowledge.model_validate_json(text))
        except ValidationError as exc:
            raise HTTPException(400, f"{path} is not valid knowledge: {_errors(exc)}") from exc
    known = {s.file for s in sources.sources}
    failures = [
        {
            "section_id": section.section_id,
            "unit_id": unit.id,
            "file": unit.source.file,
            "quote": unit.quote,
            "reason": (
                "quote not found in source" if unit.source.file in known else "file is not a source"
            ),
        }
        for section in sections
        for unit in gaik.KnowledgeBase(sections=[section]).verify_quotes(sources)
    ]
    return {"units": sum(len(s.units) for s in sections), "failures": failures}
