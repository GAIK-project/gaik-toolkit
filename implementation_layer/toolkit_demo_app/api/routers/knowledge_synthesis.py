"""Knowledge Synthesis router: write a report from curated knowledge, and rebuild it.

``/run`` writes and reviews every section with gaik's ReportSynthesizer, from the
``knowledge/`` files of the Knowledge Curator, and returns the report, the review log and
the token usage. ``/rebuild`` reassembles ``report.md`` and ``report.docx`` from edited
section texts; it calls no model. The client keeps the files between requests, so nothing
is stored on the server.

gaik is imported inside the handlers (``_gaik``): the image installs gaik from PyPI. A release
before ReportSynthesizer's ``citations`` option still writes reports (with citations, as it
always did); asking for a report without citations is then refused with a clear message.
"""

from __future__ import annotations

import asyncio
import base64
import inspect
import logging
import queue
import re
import shutil
import tempfile
import threading
from pathlib import Path
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
_ID = r"^[A-Za-z0-9_-]+$"
_KNOWLEDGE = re.compile(r"knowledge/[\w.-]+\.json", re.ASCII)
_FILES = TypeAdapter(dict[str, str])
_SAMPLE_TEXT = {".md", ".txt"}
_SAMPLE_CONVERTED = {".docx", ".pdf"}
Effort = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=_ID, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    instructions: str = Field(default="", max_length=5000)
    required_items: list[str] = Field(default=[], max_length=50)
    depends_on: list[str] = Field(default=[], max_length=MAX_SECTIONS)


class _Options(BaseModel):
    model_config = ConfigDict(extra="forbid")

    writer_model: str | None = Field(default=None, max_length=100)
    reviewer_model: str | None = Field(default=None, max_length=100)
    writer_effort: Effort | None = None
    reviewer_effort: Effort | None = None
    review_attempts: int = Field(default=5, ge=1, le=8)
    strict_review: bool = False
    citations: bool = True
    docx: bool = True


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    language: str = Field(default="English", min_length=1, max_length=50)
    instructions: str = Field(default="", max_length=10000)
    sections: list[_Section] = Field(min_length=1, max_length=MAX_SECTIONS)
    options: _Options = _Options()


class _RebuildSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=_ID, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(max_length=200000)


class _Rebuild(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    sections: list[_RebuildSection] = Field(min_length=1, max_length=MAX_SECTIONS)
    docx: bool = True


def _errors(exc: ValidationError) -> str:
    """The validation errors without the submitted values."""
    return "; ".join(
        f"{'.'.join(map(str, e['loc'])) or 'input'}: {e['msg']}"
        for e in exc.errors(include_input=False, include_url=False)
    )


def _gaik():
    """gaik's synthesis classes, imported per request (see the module docstring)."""
    from gaik.software_components.knowledge_curator import (
        KnowledgeBase,
        SectionKnowledge,
        SectionSpec,
    )
    from gaik.software_components.report_synthesizer import (
        Report,
        ReportSection,
        ReportSynthesizer,
    )
    from gaik.software_components.source_normalizer import SourceNormalizer

    return SimpleNamespace(
        KnowledgeBase=KnowledgeBase,
        SectionKnowledge=SectionKnowledge,
        SectionSpec=SectionSpec,
        Report=Report,
        ReportSection=ReportSection,
        ReportSynthesizer=ReportSynthesizer,
        SourceNormalizer=SourceNormalizer,
    )


def _docx(report) -> bytes:
    """The report as a DOCX. Needs pypandoc and the Pandoc binary."""
    tmp = Path(tempfile.mkdtemp(prefix="knowledge_synthesis_"))
    try:
        paths = report.save(tmp, docx=True)
        return paths["docx"].read_bytes()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _docx_or_error(report, wanted: bool) -> tuple[str | None, str | None]:
    """``(base64, None)``, ``(None, message)`` when DOCX failed, ``(None, None)`` if unwanted."""
    if not wanted:
        return None, None
    try:
        return base64.b64encode(_docx(report)).decode(), None
    except Exception as exc:  # a missing Pandoc must not lose the report
        logger.warning("DOCX export failed: %s", exc)
        return None, f"{type(exc).__name__}: {exc}"


async def _sample_markdown(upload: UploadFile, gaik) -> str:
    """The sample report as Markdown: text files as they are, DOCX and PDF converted locally."""
    suffix = Path(upload.filename or "").suffix.lower()
    data = await upload.read()
    if suffix in _SAMPLE_TEXT:
        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(400, "The sample report is not UTF-8 text") from exc
    if suffix in _SAMPLE_CONVERTED:
        tmp = Path(tempfile.mkdtemp(prefix="knowledge_synthesis_sample_"))
        try:
            path = tmp / f"sample{suffix}"
            path.write_bytes(data)
            try:
                return gaik.SourceNormalizer().to_markdown(path)
            except Exception as exc:
                raise HTTPException(400, f"Cannot read the sample report: {exc}") from exc
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    allowed = ", ".join(sorted(_SAMPLE_TEXT | _SAMPLE_CONVERTED))
    raise HTTPException(
        400, f"The sample report must be one of {allowed}, not {suffix or 'unknown'}"
    )


def _knowledge(files: dict[str, str], gaik):
    """The KnowledgeBase of ``knowledge/`` files; a malformed file names itself in the error."""
    if not files:
        raise HTTPException(
            400, "No knowledge files: curate knowledge in the Knowledge Curator first"
        )
    sections = []
    for path, text in sorted(files.items()):
        try:
            sections.append(gaik.SectionKnowledge.model_validate_json(text))
        except ValidationError as exc:
            raise HTTPException(400, f"{path} is not valid knowledge: {_errors(exc)}") from exc
    return gaik.KnowledgeBase(sections=sections)


@router.post("/run")
async def run(
    request: str = Form(...),
    artifacts: UploadFile = File(...),
    sample_report: UploadFile | None = File(None),
):
    """Write the report. Returns a Server-Sent Events stream.

    ``request`` is JSON: ``{"title", "language", "instructions", "sections": [{"id", "title",
    "instructions", "required_items", "depends_on"}], "options": {...}}``. ``artifacts`` is a
    JSON file of the ``knowledge/`` files. ``sample_report`` is optional (.md, .txt, .docx,
    .pdf).

    Events:
        ``progress``  {"message": str}  — sections written and reviewed
        ``result``    {"title", "markdown", "sections", "review_log", "usage",
                      "docx_b64", "docx_error"}
        ``error``     {"message": str}
    """
    gaik = _gaik()
    try:
        parsed = _Request.model_validate_json(request)
    except ValidationError as exc:
        raise HTTPException(400, f"Invalid request: {_errors(exc)}") from exc
    ids = [s.id for s in parsed.sections]
    if len(set(ids)) != len(ids):
        raise HTTPException(400, f"Section ids must be distinct: {ids}")
    try:
        files = _FILES.validate_json(await artifacts.read())
    except ValidationError as exc:
        raise HTTPException(
            400, f"artifacts must be a JSON object of path to text: {_errors(exc)}"
        ) from exc
    if bad := [k for k in files if not _KNOWLEDGE.fullmatch(k)]:
        raise HTTPException(400, f"Artifact paths not allowed: {bad}")
    knowledge = _knowledge(files, gaik)
    sample = await _sample_markdown(sample_report, gaik) if sample_report else None
    sections = [gaik.SectionSpec(**s.model_dump()) for s in parsed.sections]
    options = parsed.options
    # Older gaik releases have no `citations` option and always cite: leave it out when on, and
    # say so when it is off, instead of failing with a TypeError after the request was accepted.
    can_toggle = "citations" in inspect.signature(gaik.ReportSynthesizer.__init__).parameters
    if not options.citations and not can_toggle:
        raise HTTPException(
            400,
            "This server's gaik release cannot write a report without citations yet. "
            "Turn Citations on, or use a server with a newer gaik.",
        )
    citations = {"citations": options.citations} if can_toggle else {}
    config = get_api_config()

    def step(effort: str | None) -> dict:
        return {"reasoning_effort": effort} if effort else {}

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
            report = gaik.ReportSynthesizer(
                config,
                options.writer_model,
                reviewer_model=options.reviewer_model,
                strict_review=options.strict_review,
                review_attempts=options.review_attempts,
                writer_options=step(options.writer_effort),
                reviewer_options=step(options.reviewer_effort),
                **citations,
            ).synthesize(
                knowledge,
                sections,
                title=parsed.title,
                language=parsed.language,
                instructions=parsed.instructions,
                sample_report=sample,
                progress_callback=progress,
            )
            docx_b64, docx_error = _docx_or_error(report, options.docx)
            outcome["result"] = {
                "title": report.title,
                "markdown": report.markdown,
                "sections": [s.model_dump() for s in report.sections],
                "review_log": [e.model_dump() for e in report.review_log],
                "usage": report.usage,
                "docx_b64": docx_b64,
                "docx_error": docx_error,
            }
        except Exception as exc:
            logger.exception("Knowledge Synthesis failed")
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


@router.post("/rebuild")
async def rebuild(request: str = Form(...)):
    """Reassemble the report from (edited) section texts. Calls no model.

    ``request`` is JSON: ``{"title", "sections": [{"id", "title", "text"}], "docx"}``.
    Returns ``{"markdown", "docx_b64", "docx_error"}``.
    """
    gaik = _gaik()
    try:
        parsed = _Rebuild.model_validate_json(request)
    except ValidationError as exc:
        raise HTTPException(400, f"Invalid request: {_errors(exc)}") from exc
    ids = [s.id for s in parsed.sections]
    if len(set(ids)) != len(ids):
        raise HTTPException(400, f"Section ids must be distinct: {ids}")
    report = gaik.Report(
        title=parsed.title,
        sections=[gaik.ReportSection(**s.model_dump()) for s in parsed.sections],
        review_log=[],
    )
    docx_b64, docx_error = await asyncio.to_thread(_docx_or_error, report, parsed.docx)
    return {"markdown": report.markdown, "docx_b64": docx_b64, "docx_error": docx_error}
