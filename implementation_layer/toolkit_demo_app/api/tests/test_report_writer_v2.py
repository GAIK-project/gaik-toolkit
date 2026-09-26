"""Report Writer v2 endpoints: the examples and one CURACT stage per request.

A fake ReportWriter stands in for gaik's, so no test calls a model; the spec is
validated by gaik's real ReportSpec.
"""

from __future__ import annotations

import asyncio
import base64
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from api.routers import report_writer_v2 as route
from fastapi import FastAPI
from fastapi.testclient import TestClient
from gaik.software_modules.report_writer import ReportSpec

CONFIG = {"provider": "fake", "model": "fake-model"}
SPEC = {
    "title": "Demo report",
    "sections": [{"id": "summary", "title": "Summary"}],
    "sources": {"primary": ["notes.txt"], "secondary": ["budget.csv"]},
    "sample_report": "sample.md",
}
SOURCES = [("notes.txt", b"Meeting notes"), ("budget.csv", b"item,cost\nroof,100\n")]
SAMPLE = ("sample.md", b"# Sample report\n")
RUNS: list[tuple[str, Path]] = []


def _write(workspace: Path, files: dict[str, str]) -> None:
    for path, text in files.items():
        (workspace / path).parent.mkdir(parents=True, exist_ok=True)
        (workspace / path).write_text(text, encoding="utf-8")


class FakeWriter:
    def __init__(self, config: dict) -> None:
        assert config is CONFIG

    def normalize(self, spec, workspace: Path, *, progress_callback):
        RUNS.append(("normalize", workspace))
        sources = spec.sources["primary"] + spec.sources["secondary"]
        for i, path in enumerate(sources, start=1):
            progress_callback(f"Normalizing {path.name} ({i}/{len(sources)})")
        _write(
            workspace,
            {
                "normalized/01_notes.md": sources[0].read_text(encoding="utf-8"),
                "normalized/02_budget.md": sources[1].read_text(encoding="utf-8"),
                "normalized/sources.json": "[]",
                "normalized/scratch.txt": "not an artifact",
                "sample_report.md": spec.sample_report.read_text(encoding="utf-8"),
            },
        )
        return SimpleNamespace(usage={"audio_seconds": 30})

    def curate(self, spec, workspace: Path, *, progress_callback):
        RUNS.append(("curate", workspace))
        progress_callback("Curating Summary")
        raise ValueError("The curator answer failed validation")

    def synthesize(self, spec, workspace: Path, *, progress_callback):
        RUNS.append(("synthesize", workspace))
        assert (workspace / "knowledge/summary.json").read_text(encoding="utf-8") == "{}"
        progress_callback("Writing Summary")
        _write(
            workspace,
            {
                "report/sections/01_summary.md": "## Summary\n\nDone.\n",
                "report/review_log.json": "[]",
                "report/report.md": "# Demo report\n\n## Summary\n\nDone.\n",
            },
        )
        (workspace / "report/report.docx").write_bytes(b"docx bytes")
        return SimpleNamespace(usage={"input_tokens": 10, "output_tokens": 5})

    def rebuild(self, spec, workspace: Path):
        RUNS.append(("rebuild", workspace))
        if spec.settings.docx:
            (workspace / "report/report.docx").write_bytes(b"rebuilt docx")
        return SimpleNamespace(usage={})


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    RUNS.clear()
    monkeypatch.setattr(route, "_gaik", lambda: (FakeWriter, ReportSpec))
    monkeypatch.setattr(route, "get_api_config", lambda: CONFIG)
    app = FastAPI()
    app.include_router(route.router, prefix="/report-writer-v2")
    return TestClient(app)


@pytest.fixture
def examples(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """One example whose files live in its own folder and in a sibling folder."""
    root = tmp_path / "examples"
    (root / "demo" / "inputs").mkdir(parents=True)
    (root / "shared").mkdir()
    (root / "demo" / "inputs" / "notes.txt").write_bytes(SOURCES[0][1])
    (root / "shared" / "budget.csv").write_bytes(SOURCES[1][1])
    (root / "demo" / "sample.md").write_bytes(SAMPLE[1])
    sources = {"primary": ["inputs/notes.txt"], "secondary": ["../shared/budget.csv"]}
    (root / "demo" / "report_spec.json").write_text(json.dumps({**SPEC, "sources": sources}))
    (tmp_path / "secret").write_text("not an example file")
    monkeypatch.setattr(route, "_examples_root", lambda: root)
    return root


def _run(client, stage="normalize", spec=SPEC, artifacts=None, files=SOURCES, sample=SAMPLE):
    uploads = [("files", f) for f in files] + ([("sample_report", sample)] if sample else [])
    return client.post(
        "/report-writer-v2/run",
        data={
            "stage": stage,
            "spec": spec if isinstance(spec, str) else json.dumps(spec),
            "artifacts": artifacts if isinstance(artifacts, str) else json.dumps(artifacts or {}),
        },
        files=uploads,
    )


def _events(response) -> list[tuple[str, dict]]:
    assert response.status_code == 200, response.text
    events = []
    for block in response.text.split("\n\n"):
        if block.startswith("event: "):
            head, data = block.split("\n", 1)
            events.append((head.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return events


# ---------------------------------------------------------------------------
# Examples
# ---------------------------------------------------------------------------


def test_examples_lists_each_folder_with_a_spec(client, examples):
    response = client.get("/report-writer-v2/examples")

    assert response.status_code == 200
    assert response.json() == {
        "examples": [
            {
                "id": "demo",
                "title": "Demo report",
                "description": "",
                "files": [
                    {"name": "notes.txt", "source_class": "primary", "size": 13},
                    {"name": "budget.csv", "source_class": "secondary", "size": 19},
                ],
                "sample_report": {"name": "sample.md", "size": 16},
            }
        ]
    }


def test_example_spec_names_files_only(client, examples):
    spec = client.get("/report-writer-v2/examples/demo/spec").json()

    assert spec["sources"] == SPEC["sources"]
    assert spec["sample_report"] == "sample.md"
    assert ReportSpec.model_validate(spec).title == "Demo report"
    assert client.get("/report-writer-v2/examples/unknown/spec").status_code == 404


def test_example_files_serves_only_the_spec_files(client, examples):
    base = "/report-writer-v2/examples/demo/files"

    assert client.get(f"{base}/budget.csv").content == SOURCES[1][1]
    assert client.get(f"{base}/sample.md").content == SAMPLE[1]
    assert client.get(f"{base}/report_spec.json").status_code == 404
    assert client.get(f"{base}/..%2F..%2Fsecret").status_code == 404
    assert client.get("/report-writer-v2/examples/unknown/files/notes.txt").status_code == 404


def test_a_missing_example_file_is_a_500_that_names_it(client, examples):
    (examples / "shared" / "budget.csv").unlink()

    for path in ("/examples", "/examples/demo/spec", "/examples/demo/files/notes.txt"):
        response = client.get(f"/report-writer-v2{path}")
        assert response.status_code == 500
        assert "budget.csv" in response.json()["detail"]


def test_the_project_meeting_example_from_the_repository(client):
    spec = client.get("/report-writer-v2/examples/project_meeting/spec").json()

    assert spec["sources"]["primary"] == ["meeting_recording.mp3", "notes.txt"]
    assert spec["sample_report"] == "sample_report.md"
    response = client.get("/report-writer-v2/examples/project_meeting/files/notes.txt")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# /run validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("request_changes", "detail"),
    [
        ({"stage": "publish"}, "Unknown stage 'publish'"),
        ({"spec": "{not json"}, "Invalid spec"),
        ({"spec": {**SPEC, "api_key": "sk-secret"}}, "api_key"),
        ({"spec": {**SPEC, "settings": {"review_attempts": 0}}}, "review_attempts"),
        ({"spec": {**SPEC, "settings": {"writer": {"top_p": 1}}}}, "top_p"),
        ({"spec": {**SPEC, "sources": {"primary": ["../notes.txt"]}}}, "not paths"),
        ({"spec": {**SPEC, "sources": {"primary": ["sub/notes.txt"]}}}, "not paths"),
        ({"spec": {**SPEC, "sources": {"primary": [".."]}}}, "not paths"),
        ({"spec": {**SPEC, "sources": {"primary": [""]}}}, "not paths"),
        ({"spec": {**SPEC, "sources": {"primary": ["a\x00.txt"]}}}, "not paths"),
        ({"spec": {**SPEC, "sample_report": "notes.txt"}}, "must be distinct"),
        ({"artifacts": "{not json"}, "artifacts must be a JSON object"),
        ({"artifacts": {"report/report.md": 5}}, "artifacts must be a JSON object"),
        ({"artifacts": {"../x.md": ""}}, "Artifact paths not allowed: ['../x.md']"),
        ({"artifacts": {"knowledge/../../x.json": ""}}, "Artifact paths not allowed"),
        ({"artifacts": {"inputs/a.md": ""}}, "Artifact paths not allowed"),
        ({"artifacts": {"normalized/01_ä.md": ""}}, "Artifact paths not allowed"),
        ({"files": SOURCES[:1]}, "expected 2, got 1"),
        ({"files": [*SOURCES, ("extra.txt", b"x")]}, "expected 2, got 3"),
        ({"sample": None}, "Upload a sample_report exactly when the spec names one"),
        ({"spec": {**SPEC, "sample_report": None}}, "Upload a sample_report exactly when"),
        ({"stage": "curate", "sample": None}, "Upload files only for normalize"),
        ({"stage": "synthesize", "files": []}, "Upload files only for normalize"),
    ],
)
def test_run_rejects_a_bad_request_before_any_work(client, request_changes, detail):
    response = _run(client, **request_changes)

    assert response.status_code == 400
    assert detail in response.json()["detail"]
    assert RUNS == []


# ---------------------------------------------------------------------------
# /run stages
# ---------------------------------------------------------------------------


def test_normalize_streams_progress_and_returns_the_workspace(client):
    events = _events(_run(client))

    assert events[:2] == [
        ("progress", {"message": "Normalizing notes.txt (1/2)"}),
        ("progress", {"message": "Normalizing budget.csv (2/2)"}),
    ]
    assert events[2:] == [
        (
            "result",
            {
                "stage": "normalize",
                "artifacts": {
                    "normalized/01_notes.md": "Meeting notes",
                    "normalized/02_budget.md": "item,cost\nroof,100\n",
                    "normalized/sources.json": "[]",
                    "sample_report.md": "# Sample report\n",
                },
                "docx_b64": None,
                "usage": {"audio_seconds": 30},
            },
        )
    ]
    [(_, workspace)] = RUNS
    assert not workspace.parent.exists()


def test_uploads_are_stored_under_the_spec_names_in_spec_order(client, monkeypatch):
    seen: dict[str, bytes] = {}

    class RecordingWriter(FakeWriter):
        def normalize(self, spec, workspace, *, progress_callback):
            for path in [*spec.sources["primary"], *spec.sources["secondary"], spec.sample_report]:
                seen[path.name] = path.read_bytes()
            return SimpleNamespace(usage={})

    monkeypatch.setattr(route, "_gaik", lambda: (RecordingWriter, ReportSpec))
    names = ["floor_plan (1).png", "kuntoarvio_ä.txt", "Offer – v2, final.txt", "Raportti ä.md"]
    spec = {
        **SPEC,
        "sources": {"primary": names[:2], "secondary": names[2:3]},
        "sample_report": names[3],
    }
    # The multipart names differ on purpose: pairing is by position.
    uploads = [("a.png", b"png"), ("b.txt", b"txt"), ("c.txt", b"offer")]

    _events(_run(client, spec=spec, files=uploads, sample=("d.md", b"# Sample")))

    assert seen == dict(zip(names, [b"png", b"txt", b"offer", b"# Sample"]))


def test_a_name_the_server_cannot_store_is_a_400(client):
    spec = {**SPEC, "sources": {"primary": ["n" * 300 + ".txt"], "secondary": []}}

    response = _run(client, spec=spec, files=SOURCES[:1])

    assert response.status_code == 400
    assert "The server cannot store the file name" in response.json()["detail"]
    assert RUNS == []


def test_synthesize_returns_the_docx_and_usage(client):
    artifacts = {"knowledge/summary.json": "{}", "sample_report.md": "# Sample report\n"}
    events = _events(_run(client, "synthesize", artifacts=artifacts, files=[], sample=None))

    assert events[0] == ("progress", {"message": "Writing Summary"})
    kind, result = events[-1]
    assert kind == "result"
    assert result["artifacts"] == {
        **artifacts,
        "report/report.md": "# Demo report\n\n## Summary\n\nDone.\n",
        "report/review_log.json": "[]",
        "report/sections/01_summary.md": "## Summary\n\nDone.\n",
    }
    assert base64.b64decode(result["docx_b64"]) == b"docx bytes"
    assert result["usage"] == {"input_tokens": 10, "output_tokens": 5}


def test_rebuild_returns_the_docx_without_usage(client):
    artifacts = {"report/report.md": "# Demo report\n"}
    [(kind, result)] = _events(_run(client, "rebuild", artifacts=artifacts, files=[], sample=None))

    assert kind == "result"
    assert base64.b64decode(result["docx_b64"]) == b"rebuilt docx"
    assert result["usage"] == {}


def test_without_docx_the_result_has_none(client):
    spec = {**SPEC, "settings": {"docx": False}}
    artifacts = {"report/report.md": "# Demo report\n"}
    [(kind, result)] = _events(
        _run(client, "rebuild", spec=spec, artifacts=artifacts, files=[], sample=None)
    )

    assert kind == "result"
    assert result["docx_b64"] is None
    assert "report/report.md" in result["artifacts"]


def test_a_failing_stage_streams_an_error_and_removes_the_temp_dir(client):
    events = _events(_run(client, "curate", files=[], sample=None))

    assert events == [
        ("progress", {"message": "Curating Summary"}),
        ("error", {"message": "ValueError: The curator answer failed validation"}),
    ]
    [(_, workspace)] = RUNS
    assert not workspace.parent.exists()


def test_closing_the_stream_stops_the_stage_at_its_next_message(monkeypatch):
    closed = threading.Event()
    stopped: list[str] = []

    class SlowWriter(FakeWriter):
        def curate(self, spec, workspace, *, progress_callback):
            RUNS.append(("curate", workspace))
            progress_callback("Curating Summary")
            assert closed.wait(5)
            try:
                progress_callback("Curating Background")
            except RuntimeError as exc:
                stopped.append(str(exc))
                raise

    RUNS.clear()
    monkeypatch.setattr(route, "_gaik", lambda: (SlowWriter, ReportSpec))
    monkeypatch.setattr(route, "get_api_config", lambda: CONFIG)

    async def disconnect_after_the_first_event() -> None:
        response = await route.run_stage(
            stage="curate", spec=json.dumps(SPEC), artifacts="{}", files=[], sample_report=None
        )
        assert "Curating Summary" in await anext(response.body_iterator)
        await response.body_iterator.aclose()
        closed.set()

    asyncio.run(disconnect_after_the_first_event())
    [(_, workspace)] = RUNS
    deadline = time.monotonic() + 5
    while workspace.parent.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert stopped == ["Cancelled by the client"]
    assert not workspace.parent.exists()
