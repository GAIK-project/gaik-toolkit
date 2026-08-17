"""Tabular text-to-SQL agent router.

Exposes the gaik ``TabularAgent``: upload a spreadsheet, then ask questions
about it in natural language. Profiling a file costs a full pass over it, so
``/upload`` loads it once into a short-lived session and ``/ask`` reuses that
session -- rather than re-uploading on every question.

The user submits a file and a question, never a path. Uploads land in a
per-session temporary directory that is removed when the session is evicted, so
there is no way to point the agent at anything on the server.
"""

import asyncio
import datetime
import decimal
import logging
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path

try:
    from utils import validate_file_size
except ImportError:
    from api.utils import validate_file_size
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_EXTENSIONS = {".csv", ".tsv", ".txt", ".xlsx", ".xlsm", ".xls", ".parquet", ".json"}
# Uploads are throwaway. Keeping a handful alive is enough for the demo, and
# bounding both count and age stops a public page from filling the pod's disk.
MAX_SESSIONS = 20
SESSION_TTL_SECONDS = 30 * 60

# session_id -> {"agent", "dir", "created", "filename", "tables"}
_SESSIONS: dict[str, dict] = {}
_SESSIONS_LOCK = asyncio.Lock()


def _llm_config() -> dict | None:
    """Return an OpenAI/Azure config dict, or None when no API key is set.

    Auto-detects the provider: Azure OpenAI when ``AZURE_API_KEY`` is set,
    otherwise standard OpenAI when ``OPENAI_API_KEY`` is set.
    """
    from gaik.software_components.config import get_openai_config

    if os.getenv("AZURE_API_KEY"):
        return get_openai_config(use_azure=True)
    if os.getenv("OPENAI_API_KEY"):
        return get_openai_config(use_azure=False)
    return None


def _jsonable(value):
    """Coerce a query value into a JSON-friendly primitive.

    DuckDB hands back ``Decimal``, ``date`` and ``datetime`` objects that
    ``JSONResponse`` cannot serialize on its own.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (datetime.date, datetime.datetime, datetime.time)):
        return value.isoformat()
    return str(value)


def _discard(session: dict) -> None:
    """Close a session's agent and delete its upload directory."""
    try:
        session["agent"].close()
    except Exception as exc:  # pragma: no cover - best-effort cleanup
        logger.warning("Could not close tabular_agent session: %s", exc)
    shutil.rmtree(session["dir"], ignore_errors=True)


async def _evict_stale() -> None:
    """Drop expired sessions, then the oldest ones over the cap."""
    now = time.time()
    async with _SESSIONS_LOCK:
        expired = [
            sid
            for sid, s in _SESSIONS.items()
            if now - s["created"] > SESSION_TTL_SECONDS
        ]
        for sid in expired:
            _discard(_SESSIONS.pop(sid))
        while len(_SESSIONS) >= MAX_SESSIONS:
            oldest = min(_SESSIONS, key=lambda sid: _SESSIONS[sid]["created"])
            _discard(_SESSIONS.pop(oldest))


# ---------- Models ----------


class ColumnInfo(BaseModel):
    name: str
    data_type: str
    null_fraction: float = 0.0
    distinct_count: int = 0
    min_value: str | None = None
    max_value: str | None = None
    top_values: list[str] = Field(default_factory=list)
    samples: list[str] = Field(default_factory=list)


class TableInfo(BaseModel):
    name: str
    source: str
    row_count: int
    columns: list[ColumnInfo]


class UploadResponse(BaseModel):
    session_id: str
    filename: str
    tables: list[TableInfo]
    schema_text: str


class AskRequest(BaseModel):
    session_id: str
    question: str


class AskResponse(BaseModel):
    question: str
    answer: str
    succeeded: bool
    sql: str | None = None
    reasoning: str | None = None
    rows: list[dict] = Field(default_factory=list)
    row_count: int = 0
    attempts: int = 0
    error: str | None = None


class StatusResponse(BaseModel):
    component_available: bool
    llm_configured: bool
    allowed_extensions: list[str]
    max_file_size_mb: int
    detail: str | None = None


# ---------- Endpoints ----------


@router.get("/status", response_model=StatusResponse)
async def tabular_agent_status():
    """Report whether the component and an LLM are available in this build."""
    try:
        from api.utils.config import MAX_FILE_SIZE_MB
    except ImportError:
        from utils.config import MAX_FILE_SIZE_MB

    available, detail = True, None
    try:
        import gaik.software_components.tabular_agent  # noqa: F401
    except ImportError as exc:
        available, detail = False, str(exc)

    return StatusResponse(
        component_available=available,
        llm_configured=bool(os.getenv("AZURE_API_KEY") or os.getenv("OPENAI_API_KEY")),
        allowed_extensions=sorted(ALLOWED_EXTENSIONS),
        max_file_size_mb=MAX_FILE_SIZE_MB,
        detail=detail,
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    layout_inference: str = Form("auto"),
):
    """Load a spreadsheet and return its profiled schema plus a session id."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type: {suffix}. "
                f"Supported: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        )
    if layout_inference not in ("auto", "always", "never"):
        raise HTTPException(
            status_code=400,
            detail="layout_inference must be 'auto', 'always', or 'never'.",
        )

    content = await validate_file_size(file)
    await _evict_stale()

    # Keep the original filename: it becomes the table name the user sees.
    session_dir = tempfile.mkdtemp(prefix="gaik_tabular_")
    stored = Path(session_dir) / Path(file.filename).name
    stored.write_bytes(content)

    try:
        agent, tables, schema_text = await asyncio.to_thread(
            _load_agent, stored, layout_inference
        )
    except ImportError as e:
        shutil.rmtree(session_dir, ignore_errors=True)
        raise HTTPException(
            status_code=503,
            detail=f"tabular_agent component is not available in this build: {e}",
        ) from e
    except Exception as e:
        shutil.rmtree(session_dir, ignore_errors=True)
        logger.error("tabular_agent upload failed: %s", e)
        raise HTTPException(status_code=400, detail=f"Could not read the file: {e}") from e

    session_id = uuid.uuid4().hex[:12]
    async with _SESSIONS_LOCK:
        _SESSIONS[session_id] = {
            "agent": agent,
            "dir": session_dir,
            "created": time.time(),
            "filename": file.filename,
            "tables": tables,
        }
    logger.info("tabular_agent session %s loaded %s", session_id, file.filename)

    return UploadResponse(
        session_id=session_id,
        filename=file.filename,
        tables=tables,
        schema_text=schema_text,
    )


@router.post("/ask", response_model=AskResponse)
async def ask_question(req: AskRequest):
    """Answer a natural-language question against an uploaded file."""
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question must not be empty.")

    async with _SESSIONS_LOCK:
        session = _SESSIONS.get(req.session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found or expired. Please upload the file again.",
        )

    if not (os.getenv("AZURE_API_KEY") or os.getenv("OPENAI_API_KEY")):
        raise HTTPException(
            status_code=503, detail="No LLM API key configured on the server."
        )

    try:
        return await asyncio.to_thread(_run_ask, session["agent"], question)
    except Exception as e:
        logger.error("tabular_agent ask failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/session/{session_id}")
async def end_session(session_id: str):
    """Drop a session and delete its uploaded file."""
    async with _SESSIONS_LOCK:
        session = _SESSIONS.pop(session_id, None)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    _discard(session)
    return {"status": "closed"}


# ---------- Internal helpers ----------


def _load_agent(path: Path, layout_inference: str):
    """Build an agent for ``path`` and profile it (blocking)."""
    from gaik.software_components.tabular_agent import TabularAgent

    agent = TabularAgent(
        path,
        config=_llm_config(),
        layout_inference=layout_inference,
    )
    try:
        schema = agent.get_schema()
    except Exception:
        agent.close()
        raise

    tables = [
        TableInfo(
            name=t.name,
            source=t.source,
            row_count=t.row_count,
            columns=[
                ColumnInfo(
                    name=c.name,
                    data_type=c.data_type,
                    null_fraction=c.null_fraction,
                    distinct_count=c.distinct_count,
                    min_value=c.min_value,
                    max_value=c.max_value,
                    top_values=c.top_values,
                    samples=c.samples,
                )
                for c in t.columns
            ],
        )
        for t in schema.tables
    ]
    return agent, tables, schema.to_prompt_text()


def _run_ask(agent, question: str) -> AskResponse:
    """Ask the agent one question (blocking). The session stays open."""
    result = agent.ask(question)
    qr = result.query_result
    return AskResponse(
        question=result.question,
        answer=result.answer,
        succeeded=qr.succeeded,
        sql=qr.sql,
        reasoning=qr.reasoning,
        rows=[{k: _jsonable(v) for k, v in row.items()} for row in qr.rows],
        row_count=qr.row_count,
        attempts=qr.attempts,
        error=qr.error,
    )
