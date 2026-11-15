"""The report writer's run folder belongs to its worker, also when the client leaves."""

from __future__ import annotations

import asyncio
import io
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from api.routers import report_writer as route
from fastapi import UploadFile

CONFIG = json.dumps({"report_title": "Report", "sections": [], "output_docx": True})


def _generator(monkeypatch, run) -> None:
    class Generator:
        def __init__(self, api_config):
            pass

        def run(self, **kwargs):
            return run(**kwargs)

    monkeypatch.setattr(route, "get_api_config", lambda: {})
    monkeypatch.setattr(
        "gaik.software_modules.multi_source_report_generator.MultiSourceReportGenerator",
        Generator,
    )


async def _start():
    return await route.generate_report(
        files=[UploadFile(io.BytesIO(b"notes"), filename="notes.txt")],
        sample_report=None,
        config=CONFIG,
    )


def _wait_until_gone(folder: Path) -> None:
    deadline = time.monotonic() + 5
    while folder.exists() and time.monotonic() < deadline:
        time.sleep(0.05)


def test_a_disconnect_stops_the_run_and_the_worker_removes_its_folder(monkeypatch) -> None:
    closed = threading.Event()
    seen: dict = {}

    def run(input_paths, progress_callback, **kwargs):
        source = Path(input_paths[0])
        seen["folder"] = source.parent
        progress_callback("Reading notes.txt")
        assert closed.wait(5)
        # The client is gone, and the worker still has its inputs.
        seen["input_after_disconnect"] = source.read_bytes()
        try:
            progress_callback("Writing section 1")
        except RuntimeError as exc:
            seen["stopped"] = str(exc)
            raise
        seen["ran_on"] = True

    _generator(monkeypatch, run)

    async def disconnect_after_the_first_event() -> None:
        response = await _start()
        assert "Reading notes.txt" in await anext(response.body_iterator)
        await response.body_iterator.aclose()
        closed.set()

    asyncio.run(disconnect_after_the_first_event())
    _wait_until_gone(seen["folder"])

    assert seen["input_after_disconnect"] == b"notes"
    assert seen["stopped"] == "Cancelled by the client"
    assert "ran_on" not in seen
    assert not seen["folder"].exists()


def test_a_finished_run_returns_the_word_file_and_removes_the_folder(monkeypatch) -> None:
    seen: dict = {}

    def run(input_paths, output_dir, progress_callback, **kwargs):
        seen["folder"] = Path(input_paths[0]).parent
        progress_callback("Writing")
        docx = Path(output_dir) / "report.docx"
        docx.write_bytes(b"docx bytes")
        section = SimpleNamespace(title="Summary", content_markdown="Text", revision_warnings=[])
        return SimpleNamespace(
            markdown="# Report", sections=[section], usage={"total_tokens": 3}, docx_path=str(docx)
        )

    _generator(monkeypatch, run)

    async def read_all() -> str:
        response = await _start()
        return "".join([chunk async for chunk in response.body_iterator])

    events = asyncio.run(read_all())

    assert "event: progress" in events
    result = json.loads(events.split("event: result\ndata: ", 1)[1].split("\n", 1)[0])
    assert result["markdown"] == "# Report"
    assert result["sections"][0]["title"] == "Summary"
    assert result["docx_b64"] == "ZG9jeCBieXRlcw=="
    assert not seen["folder"].exists()
