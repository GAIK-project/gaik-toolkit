"""A person can take a copy of what the wizard holds for a session."""

import io
import json
import os
import uuid
import zipfile
from pathlib import Path

import pytest
from helpers import requires_postgres
from wizard_api import session_admin
from wizard_api.models import WizardSession
from wizard_api.ownership import USER_HEADER

ALICE = {USER_HEADER: "alice@example.com"}
BOB = {USER_HEADER: "bob@example.com"}


@pytest.fixture
def session(client, db_session, tmp_path, monkeypatch) -> dict:
    monkeypatch.setenv("WIZARD_SESSION_OUTPUT_ROOT", str(tmp_path))
    res = client.post(
        "/sessions", json={"user_id": "alice@example.com", "title": "My case"}, headers=ALICE
    )
    assert res.status_code == 201, res.text
    body = res.json()
    folder = Path(body["output_dir"])
    (folder / "poc" / "__pycache__").mkdir(parents=True)
    (folder / "poc" / "report.txt").write_text("result")
    (folder / "poc" / ".env").write_text("KEY=value")
    (folder / "poc" / "__pycache__" / "a.pyc").write_text("x")
    (tmp_path / "outside.txt").write_text("outside the session")
    os.symlink(tmp_path / "outside.txt", folder / "poc" / "link.txt")
    row = db_session.get(WizardSession, uuid.UUID(body["id"]))
    row.session_metadata = {
        **row.session_metadata,
        "messages": [{"role": "user", "content": "hello"}],
        "agent_sdk_session_id": "11111111-1111-4111-8111-111111111111",
    }
    db_session.commit()
    return body


def _read(content: bytes) -> tuple[dict, list[str]]:
    archive = zipfile.ZipFile(io.BytesIO(content))
    return json.loads(archive.read("session.json")), archive.namelist()


@requires_postgres
def test_the_owner_gets_the_conversation_blueprints_and_files(client, session) -> None:
    res = client.get(f"/sessions/{session['id']}/export", headers=ALICE)
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"
    assert f"session-{session['id']}.zip" in res.headers["content-disposition"]
    record, names = _read(res.content)
    assert record["session_id"] == session["id"]
    assert record["user_id"] == "alice@example.com"
    assert record["metadata"]["messages"] == [{"role": "user", "content": "hello"}]
    assert [v["version"] for v in record["blueprint_versions"]] == [1]
    assert "files/poc/report.txt" in names
    # The copy says a model made the blueprints and the package in it.
    assert res.headers["X-AI-Generated"] == "true"
    marker = json.loads(zipfile.ZipFile(io.BytesIO(res.content)).read("AI-GENERATED.json"))
    assert marker["ai_generated"] is True
    assert marker["content"] == "session-export"


@requires_postgres
def test_service_files_and_links_stay_out(client, session) -> None:
    res = client.get(f"/sessions/{session['id']}/export", headers=ALICE)
    record, names = _read(res.content)
    assert "agent_sdk_session_id" not in record["metadata"]
    assert "output_dir" not in record
    assert not [n for n in names if ".env" in n or "__pycache__" in n or "link.txt" in n]


@requires_postgres
def test_another_user_gets_nothing(client, session) -> None:
    assert client.get(f"/sessions/{session['id']}/export", headers=BOB).status_code == 404


@requires_postgres
def test_no_copy_stays_on_the_server(client, session, monkeypatch, tmp_path) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr("tempfile.tempdir", str(scratch))
    assert client.get(f"/sessions/{session['id']}/export", headers=ALICE).status_code == 200
    assert list(scratch.iterdir()) == []


@requires_postgres
def test_a_session_without_a_folder_still_exports(client, session) -> None:
    import shutil

    shutil.rmtree(session["output_dir"])
    res = client.get(f"/sessions/{session['id']}/export", headers=ALICE)
    assert res.status_code == 200
    assert _read(res.content)[1] == ["session.json", "AI-GENERATED.json"]


@requires_postgres
def test_the_operator_exports_all_of_a_users_sessions(session, tmp_path, capsys) -> None:
    out = tmp_path / "export"
    session_admin.main(["export", "alice@example.com", "--out", str(out)])
    assert [p.name for p in out.iterdir()] == [f"session-{session['id']}.zip"]
    assert "1 session(s)" in capsys.readouterr().out
