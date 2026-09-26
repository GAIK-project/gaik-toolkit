"""Report Writer v2 router: one CURACT stage of gaik's ReportWriter per request.

The client keeps the workspace between stages. A request sends the workspace files
the stage reads as ``artifacts``, and the result returns every workspace file after
the stage, so a person can edit them before running the next one.

gaik is imported inside the handlers (``_gaik``): the image installs gaik from PyPI,
so a release without ``report_writer`` breaks only this router, not the whole API.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import queue
import re
import shutil
import tempfile
import threading
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import TypeAdapter, ValidationError

try:
    from utils import get_api_config, sse_event
except ImportError:
    from api.utils import get_api_config, sse_event

logger = logging.getLogger(__name__)
router = APIRouter()

_EXAMPLES = Path("implementation_layer/examples/software_modules/report_writer")
_STAGES = ("normalize", "curate", "synthesize", "rebuild")
_ARTIFACT = re.compile(
    r"normalized/[\w.-]+\.(md|json)|knowledge/[\w.-]+\.json|report/sections/[\w.-]+\.md"
    r"|report/review_log\.json|report/report\.md|sample_report\.md",
    re.ASCII,
)
_ARTIFACTS = TypeAdapter(dict[str, str])


def _gaik():
    """gaik's Report Writer, imported per request (see the module docstring)."""
    from gaik.software_modules.report_writer import ReportSpec, ReportWriter

    return ReportWriter, ReportSpec


def _examples_root() -> Path:
    """The repository's report_writer examples; the image copies them to the same path."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / _EXAMPLES).is_dir():
            return parent / _EXAMPLES
    raise HTTPException(500, f"Examples not found: no {_EXAMPLES.as_posix()} above {here}")


def _example_ids() -> list[str]:
    return sorted(p.parent.name for p in _examples_root().glob("*/report_spec.json"))


def _not_a_file_name(name: str) -> bool:
    """Whether a spec name can't name a file on any OS. Other names, whatever their
    characters, are allowed: gaik slugs them into the ASCII ids of the workspace files.
    The last test keeps a Windows dev server, where a backslash and ``C:`` split paths, inside
    ``inputs/``."""
    return name in (".", "..") or "/" in name or "\x00" in name or Path(name).name != name


def _paths(spec) -> list[Path]:
    """The source files of a spec, then its sample report."""
    sample = [spec.sample_report] if spec.sample_report else []
    return [p for paths in spec.sources.values() for p in paths] + sample


def _example(example_id: str):
    """Load an example spec, whose files must all exist under distinct names."""
    if example_id not in _example_ids():
        raise HTTPException(404, f"Unknown example: {example_id}")
    spec = _gaik()[1].load(_examples_root() / example_id / "report_spec.json")
    missing = [str(p.resolve()) for p in _paths(spec) if not p.is_file()]
    if missing:
        raise HTTPException(500, f"Example {example_id} is missing files: {', '.join(missing)}")
    names = [p.name for p in _paths(spec)]
    if len(set(names)) != len(names):
        raise HTTPException(500, f"Example {example_id} repeats a file name: {names}")
    return spec


def _result(stage: str, workspace: Path, result) -> dict:
    """Every allowed workspace file as text, the DOCX if the stage wrote one, and the token
    usage of the stage (empty for rebuild, which calls no model)."""
    files = {p.relative_to(workspace).as_posix(): p for p in workspace.rglob("*") if p.is_file()}
    docx = workspace / "report" / "report.docx"
    return {
        "stage": stage,
        "artifacts": {
            path: file.read_text(encoding="utf-8")
            for path, file in sorted(files.items())
            if _ARTIFACT.fullmatch(path)
        },
        "docx_b64": base64.b64encode(docx.read_bytes()).decode() if docx.is_file() else None,
        "usage": result.usage,
    }


# ---------------------------------------------------------------------------
# Example endpoints
# ---------------------------------------------------------------------------


@router.get("/examples")
async def list_examples():
    """Every example folder with a report_spec.json, with its files."""
    examples = []
    for example_id in _example_ids():
        spec = _example(example_id)
        sample = spec.sample_report
        examples.append(
            {
                "id": example_id,
                "title": spec.title,
                "description": spec.description,
                "files": [
                    {"name": p.name, "source_class": source_class, "size": p.stat().st_size}
                    for source_class, paths in spec.sources.items()
                    for p in paths
                ],
                "sample_report": (
                    {"name": sample.name, "size": sample.stat().st_size} if sample else None
                ),
            }
        )
    return {"examples": examples}


@router.get("/examples/{example_id}/spec")
async def get_example_spec(example_id: str):
    """The example spec with every file reduced to its name, as ``/run`` takes it."""
    spec = _example(example_id)
    data = spec.model_dump(mode="json")
    data["sources"] = {k: [p.name for p in v] for k, v in spec.sources.items()}
    data["sample_report"] = spec.sample_report.name if spec.sample_report else None
    return data


@router.get("/examples/{example_id}/files/{name}")
async def get_example_file(example_id: str, name: str):
    """Serve a source or the sample report of an example; any other name is a 404."""
    files = {p.name: p for p in _paths(_example(example_id))}
    if name not in files:
        raise HTTPException(404, f"{name} is not a file of example {example_id}")
    return FileResponse(files[name], filename=name)


# ---------------------------------------------------------------------------
# Stage endpoint (SSE streaming)
# ---------------------------------------------------------------------------


@router.post("/run")
async def run_stage(
    stage: str = Form(...),
    spec: str = Form(...),
    artifacts: str = Form(...),
    files: list[UploadFile] = File([]),
    sample_report: UploadFile | None = File(None),
):
    """Run one stage in a fresh workspace. Returns a Server-Sent Events stream.

    Events:
        ``progress``  {"message": str}  — one per progress message of the stage
        ``result``    {"stage", "artifacts", "docx_b64", "usage"}
        ``error``     {"message": str}
    """
    writer_class, spec_class = _gaik()
    if stage not in _STAGES:
        raise HTTPException(400, f"Unknown stage {stage!r}; use one of {', '.join(_STAGES)}")
    try:
        parsed = spec_class.model_validate_json(spec)
    except ValidationError as exc:
        raise HTTPException(400, f"Invalid spec: {exc}") from exc
    names = [str(p) for p in _paths(parsed)]
    if bad := [n for n in names if _not_a_file_name(n)]:
        raise HTTPException(400, f"Spec files must be file names, not paths: {bad}")
    if len(set(names)) != len(names):
        raise HTTPException(400, f"Spec file names must be distinct: {names}")
    try:
        workspace_files = _ARTIFACTS.validate_json(artifacts)
    except ValidationError as exc:
        raise HTTPException(400, f"artifacts must be a JSON object of path to text: {exc}") from exc
    if bad := [k for k in workspace_files if not _ARTIFACT.fullmatch(k)]:
        raise HTTPException(400, f"Artifact paths not allowed: {bad}; allowed: {_ARTIFACT.pattern}")
    # Uploads pair with the spec names by position: browsers and undici escape some
    # characters of a multipart file name, while the spec JSON carries names exactly.
    uploads = [*files, *([sample_report] if sample_report else [])]
    if stage == "normalize":
        expected = sum(len(paths) for paths in parsed.sources.values())
        if len(files) != expected:
            raise HTTPException(
                400, f"Upload one file per spec source, in spec order: expected {expected}, "
                f"got {len(files)}"
            )
        if (sample_report is None) != (parsed.sample_report is None):
            raise HTTPException(400, "Upload a sample_report exactly when the spec names one")
    elif files or sample_report:
        raise HTTPException(400, f"Upload files only for normalize, not for {stage}")

    config = get_api_config()
    tmp = Path(tempfile.mkdtemp(prefix="report_writer_v2_"))
    inputs, workspace = tmp / "inputs", tmp / "workspace"
    try:
        inputs.mkdir()
        (inputs / "report_spec.json").write_text(spec, encoding="utf-8")
        report_spec = spec_class.load(inputs / "report_spec.json")
        (inputs / "report_spec.json").unlink()  # a source may have the same name
        for name, upload in zip(names, uploads):
            try:
                # "x" refuses to overwrite: names that differ only in case collide on a
                # case-insensitive dev machine.
                with (inputs / name).open("xb") as out:
                    out.write(await upload.read())
            except OSError as exc:
                raise HTTPException(
                    400, f"The server cannot store the file name {name!r}: {exc}"
                ) from exc
        for path, text in workspace_files.items():
            (workspace / path).parent.mkdir(parents=True, exist_ok=True)
            (workspace / path).write_text(text, encoding="utf-8")
    except BaseException:
        shutil.rmtree(tmp)
        raise

    messages: queue.Queue[str] = queue.Queue()
    outcome: dict = {}
    done = threading.Event()
    cancelled = threading.Event()

    def progress(message: str) -> None:
        if cancelled.is_set():
            raise RuntimeError("Cancelled by the client")
        messages.put(message)

    def run() -> None:
        # The worker owns the temp dir, so a disconnect cannot delete files under it.
        try:
            writer = writer_class(config)
            if stage == "rebuild":
                result = writer.rebuild(report_spec, workspace)
            else:
                result = getattr(writer, stage)(report_spec, workspace, progress_callback=progress)
            outcome["result"] = _result(stage, workspace, result)
        except Exception as exc:
            logger.exception("Report Writer v2 %s failed", stage)
            outcome["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                shutil.rmtree(tmp)
            finally:
                done.set()

    threading.Thread(target=run, daemon=True).start()

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
