"""Report Writer router — multi-source report generation endpoints."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import queue
import shutil
import tempfile
import threading
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

try:
    from utils import get_api_config, sse_event
except ImportError:
    from api.utils import get_api_config, sse_event

logger = logging.getLogger(__name__)
router = APIRouter()


# Locate the multi_source_report_generator example assets.
#
# In the repo they live under <repo>/implementation_layer/examples/...; in the
# flattened container image that tree is absent, so the assets are bundled at
# /app/report_examples via the Dockerfile. Resolve safely so a missing tree
# never raises at import (a bare ``parents[4]`` raised IndexError in the
# container and crashed the entire API).
def _find_example_dir() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = (
            parent
            / "implementation_layer"
            / "examples"
            / "software_modules"
            / "multi_source_report_generator"
        )
        if candidate.exists():
            return candidate
    # Container layout: bundled copy next to the app root (/app/report_examples).
    return here.parent.parent / "report_examples"


_EXAMPLE_DIR = _find_example_dir()
_EXAMPLE_INPUTS = _EXAMPLE_DIR / "sample_inputs"
_EXAMPLE_CONFIG = _EXAMPLE_DIR / "report_config.json"
_EXAMPLE_SAMPLE = _EXAMPLE_DIR / "sample_report.md"

# Supported extensions (mirror pipeline.py SUPPORTED_EXTENSIONS)
_SUPPORTED_EXTS = {
    ".txt",
    ".md",
    ".markdown",
    ".pdf",
    ".docx",
    ".csv",
    ".xlsx",
    ".xls",
    ".mp3",
    ".wav",
    ".m4a",
    ".aac",
    ".flac",
    ".ogg",
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".webm",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".tiff",
    ".tif",
    ".bmp",
    ".gif",
}


# ---------------------------------------------------------------------------
# Example endpoints
# ---------------------------------------------------------------------------


@router.get("/example/config")
async def get_example_config():
    """Return the cleaned example report configuration."""
    if not _EXAMPLE_CONFIG.exists():
        raise HTTPException(status_code=404, detail="Example config not found")
    raw = json.loads(_EXAMPLE_CONFIG.read_text(encoding="utf-8"))
    # Strip server-side absolute paths so the frontend gets clean values
    raw["input_paths"] = []
    raw["output_dir"] = None
    if raw.get("transcriber_options"):
        ctor = raw["transcriber_options"].get("ctor", {})
        if "output_dir" in ctor:
            ctor["output_dir"] = "output/transcripts"
    return {"config": raw}


@router.get("/example/files")
async def list_example_files():
    """Return metadata for files in the example sample_inputs folder."""
    if not _EXAMPLE_INPUTS.exists():
        return {"files": []}
    files = []
    for p in sorted(_EXAMPLE_INPUTS.iterdir()):
        if p.is_file() and p.suffix.lower() in _SUPPORTED_EXTS:
            files.append({"name": p.name, "size": p.stat().st_size, "suffix": p.suffix.lower()})
    return {"files": files}


@router.get("/example/file/{filename}")
async def get_example_file(filename: str):
    """Serve one example input file."""
    path = _EXAMPLE_INPUTS / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Example file not found: {filename}")
    return FileResponse(str(path), filename=filename)


@router.get("/example/sample-report")
async def get_example_sample_report():
    """Serve the example sample_report.md format reference."""
    if not _EXAMPLE_SAMPLE.exists():
        raise HTTPException(status_code=404, detail="Example sample report not found")
    return FileResponse(str(_EXAMPLE_SAMPLE), filename="sample_report.md")


# ---------------------------------------------------------------------------
# Generation endpoint (SSE streaming)
# ---------------------------------------------------------------------------


@router.post("/run")
async def generate_report(
    files: list[UploadFile] = File(...),
    sample_report: UploadFile | None = File(None),
    config: str = Form(...),
):
    """Start a report generation run.  Returns a Server-Sent Events stream.

    Events:
        ``progress``  {"message": str}         — one per normalization / agentic step
        ``result``    {"markdown", "sections", "usage", "docx_b64"}  — final output
        ``error``     {"message": str}          — on failure
    """
    try:
        run_config: dict = json.loads(config)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid config JSON: {exc}") from exc

    # Save uploaded files to a temp directory
    tmp_dir = Path(tempfile.mkdtemp())
    input_paths: list[str] = []
    sample_path: str | None = None

    try:
        for uf in files:
            if not uf.filename:
                continue
            dest = tmp_dir / uf.filename
            dest.write_bytes(await uf.read())
            input_paths.append(str(dest))

        if sample_report and sample_report.filename:
            dest = tmp_dir / sample_report.filename
            dest.write_bytes(await sample_report.read())
            sample_path = str(dest)
    except Exception as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not input_paths:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="No input files provided")

    msg_queue: queue.Queue[str] = queue.Queue()
    result_holder: dict = {}
    done_event = threading.Event()

    def progress_cb(msg: str) -> None:
        msg_queue.put(msg)

    def run_report() -> None:
        try:
            from gaik.software_modules.multi_source_report_generator import (
                MultiSourceReportGenerator,
            )

            api_config = get_api_config()
            gen = MultiSourceReportGenerator(api_config=api_config)

            output_dir = tmp_dir / "output"
            output_dir.mkdir(exist_ok=True)

            result = gen.run(
                input_paths=input_paths,
                report_title=run_config.get("report_title", "Generated Report"),
                report_description=run_config.get("report_description"),
                report_language=run_config.get("report_language"),
                sections=run_config.get("sections", []),
                sample_report_path=sample_path,
                output_dir=str(output_dir),
                output_docx=run_config.get("output_docx", False),
                include_evidence_index=run_config.get("include_evidence_index", True),
                include_source_references=run_config.get("include_source_references", True),
                max_evidence_chars=run_config.get("max_evidence_chars"),
                parser_choice=run_config.get("parser_choice", "auto"),
                parser_options=run_config.get("parser_options") or {},
                transcriber_options=run_config.get("transcriber_options") or {},
                image_options=run_config.get("image_options") or {},
                writer_options=run_config.get("writer_options") or {},
                agentic=run_config.get("agentic", False),
                review_options=run_config.get("review_options"),
                polish=run_config.get("polish", False),
                # strict_review would raise before result; surface as warnings instead
                strict_review=False,
                curate_evidence=run_config.get("curate_evidence", False),
                verbose=False,
                progress_callback=progress_cb,
            )
            result_holder["result"] = result
        except Exception as exc:  # noqa: BLE001
            logger.exception("Report generation failed")
            result_holder["error"] = str(exc)
        finally:
            done_event.set()

    thread = threading.Thread(target=run_report, daemon=True)
    thread.start()

    async def event_stream():
        last_heartbeat = asyncio.get_event_loop().time()
        try:
            while not done_event.is_set() or not msg_queue.empty():
                drained = False
                while not msg_queue.empty():
                    try:
                        msg = msg_queue.get_nowait()
                        yield sse_event("progress", {"message": msg})
                        drained = True
                    except queue.Empty:
                        break
                if not drained:
                    await asyncio.sleep(0.1)
                    now = asyncio.get_event_loop().time()
                    if now - last_heartbeat > 15:
                        # SSE comment — keeps proxy connections alive
                        yield ": heartbeat\n\n"
                        last_heartbeat = now

            thread.join(timeout=10)

            if "error" in result_holder:
                yield sse_event("error", {"message": result_holder["error"]})
            elif "result" in result_holder:
                result = result_holder["result"]
                docx_b64: str | None = None
                if result.docx_path and Path(result.docx_path).exists():
                    docx_b64 = base64.b64encode(Path(result.docx_path).read_bytes()).decode()
                sections_data = [
                    {
                        "title": s.title,
                        "content_markdown": s.content_markdown,
                        "revision_warnings": s.revision_warnings,
                    }
                    for s in result.sections
                ]
                yield sse_event(
                    "result",
                    {
                        "markdown": result.markdown,
                        "sections": sections_data,
                        "usage": result.usage or {},
                        "docx_b64": docx_b64,
                    },
                )
            else:
                yield sse_event("error", {"message": "No result produced"})
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
