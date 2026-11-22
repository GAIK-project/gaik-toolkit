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

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

try:
    from utils import get_api_config, sse_event
    from utils.model_allow_list import chat_models, check_model, transcription_models
    from utils.report_runs import report_writer_limits, require_report_run_grant
    from utils.upload_check import upload_problem
except ImportError:
    from api.utils import get_api_config, sse_event
    from api.utils.model_allow_list import chat_models, check_model, transcription_models
    from api.utils.report_runs import report_writer_limits, require_report_run_grant
    from api.utils.upload_check import upload_problem

try:
    from utils.errors import error_detail
except ImportError:
    from api.utils.errors import error_detail

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
# Refused at upload: openpyxl reads no .xls, so a run would fail on it after the
# sources before it were parsed and transcribed.
_REFUSED_EXTS = {".xls": "the old Excel format .xls is not supported; save it as .xlsx"}


# ---------------------------------------------------------------------------
# Upload names and run options
# ---------------------------------------------------------------------------

# The option keys the report writer page sets. Anything else in the posted
# config (folders, endpoints, other constructor arguments) is not passed on.
_OPTION_KEYS: dict[str, frozenset[str]] = {
    "image_options": frozenset({"mode", "user_requirements"}),
    "writer_options": frozenset({"model", "temperature", "reasoning_effort"}),
    "review_options": frozenset({"model"}),
}
_TRANSCRIBER_CTOR_KEYS = frozenset(
    {
        "transcription_model",
        "language",
        "enhanced_transcript",
        "diarization",
        "speaker_count",
        "initial_prompt",
    }
)


# Control characters, and the bidi controls that can make "x.exe.md" read as
# "x.dm.exe", have no place in a name the report quotes.
_NAME_DROP = (
    {chr(c) for c in range(32)}
    | {"\x7f"}
    | {chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A))}
)
_NAME_MAX = 150


def _upload_name(filename: str, used: set[str]) -> str:
    """The client's file name reduced to a plain name inside the run folder.

    The name is kept (the report cites its sources by it), but only its last
    part: no folders, no drive, nothing that leaves the folder. A colon becomes
    "_" rather than costing the name its suffix ("Meeting: notes.pdf" is still
    a PDF), control characters go, and a long name is cut before its suffix. A
    repeated name gets a number so one upload does not replace another.
    """
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if ch not in _NAME_DROP).replace(":", "_")
    name = name.strip().lstrip(".")
    if not name:
        name = "upload"
    stem, dot, suffix = name.rpartition(".")
    if not dot:
        stem, suffix = name, ""
    if len(name) > _NAME_MAX:
        stem = stem[: _NAME_MAX - len(suffix) - 1].rstrip() or "upload"
        name = f"{stem}.{suffix}" if suffix else stem
    candidate, number = name, 1
    while candidate.lower() in used:
        number += 1
        candidate = f"{stem}-{number}.{suffix}" if suffix else f"{stem}-{number}"
    used.add(candidate.lower())
    return candidate


def _apply_limits(run_config: dict, uploads: list[UploadFile]) -> None:
    """Hold the page's limits here too (utils/report_runs.py): the number of
    sections and the total upload size are refused over the limit, and the
    evidence ceiling is capped at it."""
    limits = report_writer_limits()
    sections = run_config.get("sections", [])
    if isinstance(sections, list) and len(sections) > limits["max_sections"]:
        raise HTTPException(
            status_code=400, detail=f"Too many sections (max {limits['max_sections']})"
        )
    if sum(uf.size or 0 for uf in uploads) > limits["max_upload_bytes"]:
        raise HTTPException(
            status_code=413,
            detail=f"Uploads exceed the {limits['max_upload_bytes'] // (1024 * 1024)} MB limit",
        )
    requested = run_config.get("max_evidence_chars")
    run_config["max_evidence_chars"] = (
        min(requested, limits["max_evidence_chars"])
        if isinstance(requested, int) and not isinstance(requested, bool) and requested > 0
        else limits["max_evidence_chars"]
    )


def _run_options(run_config: dict, work_dir: Path) -> dict:
    """The component options for one run: only the keys the page sets."""
    options: dict = {"parser_options": {}}
    for key, allowed in _OPTION_KEYS.items():
        given = run_config.get(key)
        options[key] = (
            {k: v for k, v in given.items() if k in allowed} if isinstance(given, dict) else {}
        )
    if not options["review_options"]:
        options["review_options"] = None
    given = run_config.get("transcriber_options")
    ctor = given.get("ctor") if isinstance(given, dict) else None
    ctor = (
        {k: v for k, v in ctor.items() if k in _TRANSCRIBER_CTOR_KEYS}
        if isinstance(ctor, dict)
        else {}
    )
    ctor["output_dir"] = str(work_dir / "transcripts")
    options["transcriber_options"] = {"ctor": ctor}
    return options


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
    if path.resolve().parent != _EXAMPLE_INPUTS.resolve() or not path.is_file():
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


def _check_run_models(run_config: dict) -> None:
    """The writer, review and transcription models must be ones the demo offers."""

    def named(key: str, field: str):
        given = run_config.get(key)
        value = given.get(field) if isinstance(given, dict) else None
        return value if isinstance(value, str) else None

    offered = chat_models()
    check_model(named("writer_options", "model"), offered, "writer model")
    check_model(named("review_options", "model"), offered, "review model")
    transcriber = run_config.get("transcriber_options")
    ctor = transcriber.get("ctor") if isinstance(transcriber, dict) else None
    model = ctor.get("transcription_model") if isinstance(ctor, dict) else None
    check_model(
        model if isinstance(model, str) else None,
        transcription_models(),
        "transcription model",
    )


@router.post("/run", dependencies=[Depends(require_report_run_grant)])
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
    if not isinstance(run_config, dict):
        raise HTTPException(status_code=400, detail="Config must be a JSON object")
    _check_run_models(run_config)

    _apply_limits(run_config, [*files, *([sample_report] if sample_report else [])])

    # Save uploaded files to a temp directory
    tmp_dir = Path(tempfile.mkdtemp())
    input_paths: list[str] = []
    sample_path: str | None = None

    used_names: set[str] = {"output", "transcripts"}

    async def checked(upload: UploadFile) -> tuple[str, bytes]:
        # The route takes many kinds of file and keeps its own type rules, so
        # the shared check skips only the type step (utils/upload_check.py).
        name = _upload_name(upload.filename, used_names)
        refused = _REFUSED_EXTS.get(Path(name).suffix.lower())
        if refused is not None:
            raise HTTPException(415, f"{name}: {refused}")
        data = await upload.read()
        problem = await upload_problem(Path(name).suffix, data, check_type=False)
        if problem is not None:
            raise HTTPException(problem.status, f"{name}: {problem.message}")
        return name, data

    try:
        for uf in files:
            if not uf.filename:
                continue
            name, data = await checked(uf)
            dest = tmp_dir / name
            dest.write_bytes(data)
            input_paths.append(str(dest))

        if sample_report and sample_report.filename:
            name, data = await checked(sample_report)
            dest = tmp_dir / name
            dest.write_bytes(data)
            sample_path = str(dest)
    except HTTPException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.warning("Cannot store the uploads: %s", type(exc).__name__)
        raise HTTPException(
            status_code=400,
            detail="The server cannot store the uploaded files. Rename them and try again.",
        ) from exc

    if not input_paths:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="No input files provided")

    msg_queue: queue.Queue[str] = queue.Queue()
    result_holder: dict = {}
    done_event = threading.Event()
    cancelled = threading.Event()

    def progress_cb(msg: str) -> None:
        if cancelled.is_set():
            raise RuntimeError("Cancelled by the client")
        msg_queue.put(msg)

    def run_report() -> None:
        # The worker owns the run folder: it reads the inputs and writes the output
        # there until it ends, so only it removes the folder. A disconnect sets
        # ``cancelled`` and the run stops at its next progress message.
        try:
            from gaik.software_modules.multi_source_report_generator import (
                MultiSourceReportGenerator,
            )

            api_config = get_api_config()
            gen = MultiSourceReportGenerator(api_config=api_config)

            output_dir = tmp_dir / "output"
            output_dir.mkdir(exist_ok=True)
            options = _run_options(run_config, tmp_dir)

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
                **options,
                agentic=run_config.get("agentic", False),
                polish=run_config.get("polish", False),
                # strict_review would raise before result; surface as warnings instead
                strict_review=False,
                curate_evidence=run_config.get("curate_evidence", False),
                verbose=False,
                progress_callback=progress_cb,
            )
            # Read the Word file here, while the folder still exists.
            docx_b64: str | None = None
            if result.docx_path and Path(result.docx_path).exists():
                docx_b64 = base64.b64encode(Path(result.docx_path).read_bytes()).decode()
            result_holder["result"] = {
                "markdown": result.markdown,
                "sections": [
                    {
                        "title": s.title,
                        "content_markdown": s.content_markdown,
                        "revision_warnings": s.revision_warnings,
                    }
                    for s in result.sections
                ],
                "usage": result.usage or {},
                "docx_b64": docx_b64,
            }
        except Exception as exc:  # noqa: BLE001
            if cancelled.is_set():
                logger.info("Report generation stopped: the client left")
                result_holder["error"] = "Report generation stopped: the client left."
            else:
                result_holder["error"] = error_detail(exc, "Report generation")
        finally:
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            finally:
                done_event.set()

    threading.Thread(target=run_report, daemon=True).start()

    async def event_stream():
        loop = asyncio.get_running_loop()
        last_heartbeat = loop.time()
        try:
            while not done_event.is_set() or not msg_queue.empty():
                try:
                    msg = msg_queue.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.1)
                    if loop.time() - last_heartbeat > 15:
                        # SSE comment — keeps proxy connections alive
                        yield ": heartbeat\n\n"
                        last_heartbeat = loop.time()
                    continue
                yield sse_event("progress", {"message": msg})

            if "error" in result_holder:
                yield sse_event("error", {"message": result_holder["error"]})
            elif "result" in result_holder:
                yield sse_event("result", result_holder["result"])
            else:
                yield sse_event("error", {"message": "No result produced"})
        finally:
            # A closed or cancelled stream means the client left: stop at the next message.
            cancelled.set()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
