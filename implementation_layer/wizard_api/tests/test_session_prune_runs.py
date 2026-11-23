"""Old test runs can be pruned so the sessions volume does not fill; the latest run stays."""

import os
import time
import uuid
from pathlib import Path

import pytest
from helpers import requires_postgres
from wizard_api import session_admin
from wizard_api.models import WizardSession
from wizard_api.ownership import USER_HEADER

ALICE = {USER_HEADER: "alice@example.com"}


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("WIZARD_SESSION_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.delenv("WIZARD_AGENT_STATE_DIR", raising=False)
    return tmp_path


def _session_with_runs(
    client, db_session, names: list[str], latest: str | None
) -> tuple[str, Path]:
    res = client.post(
        "/sessions", json={"user_id": "alice@example.com", "title": "t"}, headers=ALICE
    )
    assert res.status_code == 201, res.text
    sid = res.json()["id"]
    row = db_session.get(WizardSession, uuid.UUID(sid))
    if latest:
        row.session_metadata = {**row.session_metadata, "latest_run": latest}
        db_session.commit()
    runs = Path(row.output_dir) / "runs"
    now = time.time()
    # names[0] is the oldest
    for age, name in enumerate(reversed(names)):
        folder = runs / name / "output"
        folder.mkdir(parents=True)
        (folder.parent / "log.txt").write_text("log " * 100)
        (folder / "result.json").write_text("{}")
        os.utime(runs / name, (now - age * 60, now - age * 60))
    return sid, runs


@requires_postgres
def test_without_apply_nothing_is_removed(client, db_session, root, capsys) -> None:
    _, runs = _session_with_runs(client, db_session, ["r1", "r2", "r3", "r4", "r5"], latest="r5")
    session_admin.main(["prune-runs"])
    assert sorted(p.name for p in runs.iterdir()) == ["r1", "r2", "r3", "r4", "r5"]
    assert "2 run(s) to remove" in capsys.readouterr().out


@requires_postgres
def test_the_newest_runs_and_the_latest_one_are_kept(client, db_session, root) -> None:
    # The session points at r1 (an older run approved at Gate 3, say): it stays too.
    _, runs = _session_with_runs(client, db_session, ["r1", "r2", "r3", "r4", "r5"], latest="r1")
    session_admin.main(["prune-runs", "--keep", "2", "--apply"])
    assert sorted(p.name for p in runs.iterdir()) == ["r1", "r4", "r5"]


@requires_postgres
def test_a_session_without_runs_is_fine(client, db_session, root, capsys) -> None:
    _session_with_runs(client, db_session, [], latest=None)
    session_admin.main(["prune-runs", "--apply"])
    assert "0 run folder(s) removed" in capsys.readouterr().out


def test_keep_must_be_at_least_one() -> None:
    with pytest.raises(SystemExit):
        session_admin.main(["prune-runs", "--keep", "0"])
