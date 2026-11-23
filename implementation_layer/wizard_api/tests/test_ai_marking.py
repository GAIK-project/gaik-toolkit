"""What the wizard hands out says, in a form a machine reads, that AI generated it."""

import io
import json
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from helpers import requires_postgres
from wizard_api.models import WizardSession
from wizard_api.services import ai_marking, poc_service

MARKER = f"poc/{ai_marking.MARKER_FILE}"


@pytest.fixture
def package(client, db_session, tmp_path, monkeypatch) -> str:
    monkeypatch.setenv("WIZARD_SESSION_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_MODEL", "test-model")
    monkeypatch.setattr(poc_service, "package_problems", lambda _poc: [])
    res = client.post("/sessions", json={"user_id": "u", "title": "t"})
    assert res.status_code == 201
    body = res.json()
    poc = Path(body["output_dir"]) / "poc"
    poc.mkdir(parents=True)
    (poc / "README.md").write_text("package")
    (poc / ai_marking.MARKER_FILE).write_text('{"ai_generated": false}')
    row = db_session.get(WizardSession, uuid.UUID(body["id"]))
    row.session_metadata = {**row.session_metadata, "last_successful_run": "run-1"}
    db_session.commit()
    return body["id"]


def _marker(content: bytes) -> dict:
    archive = zipfile.ZipFile(io.BytesIO(content))
    assert archive.namelist().count(MARKER) == 1
    return json.loads(archive.read(MARKER))


@requires_postgres
@pytest.mark.parametrize(
    ("path", "content"),
    [("poc", "poc-package"), ("poc/deployable", "poc-package-deployable")],
)
def test_a_package_carries_the_marker_and_headers(client, package, path, content) -> None:
    res = client.get(f"/sessions/{package}/{path}")
    assert res.status_code == 200
    assert res.headers["X-AI-Generated"] == "true"
    assert res.headers["X-AI-Model"] == "test-model"
    marker = _marker(res.content)
    assert marker["ai_generated"] is True
    assert marker["model"] == "test-model"
    assert marker["content"] == content
    assert marker["session_id"] == package


def test_the_marker_names_its_source_and_time() -> None:
    session = SimpleNamespace(id=uuid.uuid4(), active_version=3)
    now = datetime(2026, 11, 7, 12, tzinfo=UTC)
    marker = ai_marking.marker(session, "poc-package", now)
    assert marker["schema"] == "gaik.ai-generated/1"
    assert marker["digital_source_type"].endswith("/trainedAlgorithmicMedia")
    assert marker["generator"] == "GAIK Solution Wizard"
    assert marker["blueprint_version"] == 3
    assert marker["exported_at"] == "2026-11-07T12:00:00+00:00"


def test_the_diagram_opens_with_the_mark(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_MODEL", "test-model")
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<bpmn:definitions/>'
    marked = ai_marking.mark_xml(xml)
    assert marked.splitlines()[0] == '<?xml version="1.0" encoding="UTF-8"?>'
    assert marked.splitlines()[1] == (
        "<!-- ai_generated: true; generator: GAIK Solution Wizard; model: test-model -->"
    )
    assert marked.endswith("<bpmn:definitions/>")
    assert ai_marking.mark_xml("<a/>").startswith("<!-- ai_generated: true;")
    # A diagram the session kept is marked already, and a second mark adds nothing.
    assert ai_marking.mark_xml(marked) == marked


def test_extra_fields_follow_the_standard_ones() -> None:
    session = SimpleNamespace(id=uuid.uuid4(), active_version=4)
    marker = json.loads(
        ai_marking.marker_json(session, "solution-files", files={"workflow.bpmn": {"v": 4}})
    )
    assert marker["content"] == "solution-files"
    assert marker["files"] == {"workflow.bpmn": {"v": 4}}
    assert list(marker)[-1] == "files"
