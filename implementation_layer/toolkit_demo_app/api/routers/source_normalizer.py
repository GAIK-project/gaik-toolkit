"""Source Normalizer router: convert uploaded files to Markdown texts.

One request converts every uploaded file with gaik's SourceNormalizer and returns the
files ``NormalizedSources.save`` writes (``normalized/<id>.md`` and
``normalized/sources.json``) as text. Nothing is kept on the server.

gaik is imported inside the handler (``_gaik``): the image installs gaik from PyPI, so a
release without ``source_normalizer`` breaks only this router, not the whole API.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

try:
    from utils import get_api_config, sse_event
except ImportError:
    from api.utils import get_api_config, sse_event

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_FILES = 20


class _Source(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    source_class: Literal["primary", "secondary"]


class _Options(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcription_model: str | None = Field(default=None, max_length=100)
    vision_model: str | None = Field(default=None, max_length=100)
    language: str = Field(default="auto", min_length=1, max_length=20)


class _Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[_Source] = Field(min_length=1, max_length=MAX_FILES)
    options: _Options = _Options()


def _errors(exc: ValidationError) -> str:
    """The validation errors without the submitted values."""
    return "; ".join(
        f"{'.'.join(map(str, e['loc'])) or 'input'}: {e['msg']}"
        for e in exc.errors(include_input=False, include_url=False)
    )


def _gaik():
    """gaik's SourceNormalizer, imported per request (see the module docstring)."""
    from gaik.software_components.source_normalizer import SourceNormalizer

    return SourceNormalizer


def _not_a_file_name(name: str) -> bool:
    """Whether a name can't name a file on any OS. The last test keeps a Windows dev
    server, where a backslash and ``C:`` split paths, inside ``inputs/``."""
    return name in (".", "..") or "/" in name or "\x00" in name or Path(name).name != name


@router.post("/run")
async def run(manifest: str = Form(...), files: list[UploadFile] = File(...)):
    """Convert the uploaded files. Returns a Server-Sent Events stream.

    ``manifest`` is JSON: ``{"sources": [{"name", "source_class"}], "options":
    {"transcription_model", "vision_model", "language"}}``. ``files`` pair with
    ``sources`` by position, because browsers escape some characters of a multipart
    file name while the manifest carries names exactly.

    Events:
        ``progress``  {"message": str}  — one per file
        ``result``    {"artifacts": {path: text}, "usage": {...}}
        ``error``     {"message": str}
    """
    normalizer_class = _gaik()
    try:
        parsed = _Manifest.model_validate_json(manifest)
    except ValidationError as exc:
        raise HTTPException(400, f"Invalid manifest: {_errors(exc)}") from exc
    names = [s.name for s in parsed.sources]
    if bad := [n for n in names if _not_a_file_name(n)]:
        raise HTTPException(400, f"Sources must be file names, not paths: {bad}")
    if len(set(names)) != len(names):
        raise HTTPException(400, f"File names must be distinct: {names}")
    if len(files) != len(names):
        raise HTTPException(
            400,
            f"Upload one file per manifest source, in order: expected {len(names)}, "
            f"got {len(files)}",
        )

    config = get_api_config()
    tmp = Path(tempfile.mkdtemp(prefix="source_normalizer_"))
    inputs, out = tmp / "inputs", tmp / "normalized"
    try:
        inputs.mkdir()
        for name, upload in zip(names, files):
            try:
                # "x" refuses to overwrite: names that differ only in case collide on a
                # case-insensitive dev machine.
                with (inputs / name).open("xb") as target:
                    target.write(await upload.read())
            except OSError as exc:
                raise HTTPException(
                    400, f"The server cannot store the file name {name!r}: {exc}"
                ) from exc
    except BaseException:
        shutil.rmtree(tmp)
        raise

    groups: dict[str, list[Path]] = {"primary": [], "secondary": []}
    for source in parsed.sources:
        groups[source.source_class].append(inputs / source.name)
    options = parsed.options

    messages: queue.Queue[str] = queue.Queue()
    outcome: dict = {}
    done = threading.Event()
    cancelled = threading.Event()

    def progress(message: str) -> None:
        if cancelled.is_set():
            raise RuntimeError("Cancelled by the client")
        messages.put(message)

    def work() -> None:
        # The worker owns the temp dir, so a disconnect cannot delete files under it.
        try:
            normalizer = normalizer_class(
                config,
                vision_model=options.vision_model,
                transcription_model=options.transcription_model,
                language=options.language,
            )
            sources = normalizer.normalize(groups, progress_callback=progress)
            sources.save(out)
            outcome["result"] = {
                "artifacts": {
                    f"normalized/{p.name}": p.read_text(encoding="utf-8")
                    for p in sorted(out.iterdir())
                },
                "usage": sources.usage,
            }
        except Exception as exc:
            logger.exception("Source Normalizer failed")
            outcome["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                shutil.rmtree(tmp)
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
