"""A person can delete a whole session, and nothing of it stays behind."""

import logging
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from helpers import requires_postgres
from wizard_api import session_admin
from wizard_api.models import BlueprintVersion, WizardSession
from wizard_api.ownership import USER_HEADER
from wizard_api.routers import sessions as sessions_router
from wizard_api.services import agent_service, sandbox_runner, session_removal

ALICE = {USER_HEADER: "alice@example.com"}
BOB = {USER_HEADER: "bob@example.com"}
STORED = "11111111-1111-4111-8111-111111111111"
EARLIER = "22222222-2222-4222-8222-222222222222"
OTHER = "33333333-3333-4333-8333-333333333333"
MENTIONS = "44444444-4444-4444-8444-444444444444"
CLAIMED = "55555555-5555-4555-8555-555555555555"


@pytest.fixture
def root(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("WIZARD_SESSION_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.delenv("WIZARD_AGENT_STATE_DIR", raising=False)
    return tmp_path


def _create(client) -> dict:
    res = client.post(
        "/sessions", json={"user_id": "alice@example.com", "title": "t"}, headers=ALICE
    )
    assert res.status_code == 201, res.text
    return res.json()


def _row(db_session, session_id: str) -> WizardSession | None:
    db_session.expire_all()
    return db_session.get(WizardSession, uuid.UUID(session_id))


def _set_metadata(db_session, session_id: str, **values) -> None:
    row = _row(db_session, session_id)
    row.session_metadata = {**row.session_metadata, **values}
    db_session.commit()


def _conversation(root: Path, conversation: str, text: str) -> list[Path]:
    project = root / ".claude-agent" / "projects" / "-solution-wizard"
    (project / conversation / "tool-results").mkdir(parents=True)
    env = root / ".claude-agent" / "session-env" / conversation
    env.mkdir(parents=True)
    transcript = project / f"{conversation}.jsonl"
    transcript.write_text(text)
    return [transcript, project / conversation, env]


@requires_postgres
def test_everything_of_the_session_goes(client, db_session, root) -> None:
    session = _create(client)
    sid = session["id"]
    (Path(session["output_dir"]) / "poc" / "input").mkdir(parents=True)
    (Path(session["output_dir"]) / "poc" / "input" / "a.txt").write_text("x")
    _set_metadata(db_session, sid, agent_sdk_session_id=STORED)
    gone = _conversation(root, STORED, "latest")
    # A conversation it replaced names its folder, as the agent's first message does.
    gone += _conversation(root, EARLIER, f"cwd {session['output_dir']}")
    kept = _conversation(root, OTHER, "another session")
    # Another session's conversation where this session's id was pasted (review of #324).
    kept += _conversation(root, MENTIONS, f"the user pasted session {sid} here")
    # One that names the folder too, but that another session stored as its own.
    other = _create(client)
    _set_metadata(db_session, other["id"], agent_sdk_session_id=CLAIMED)
    kept += _conversation(root, CLAIMED, f"cwd {session['output_dir']}")

    assert client.delete(f"/sessions/{sid}", headers=ALICE).status_code == 204

    assert _row(db_session, sid) is None
    assert db_session.query(BlueprintVersion).filter_by(session_id=uuid.UUID(sid)).count() == 0
    assert not Path(session["output_dir"]).exists()
    assert not any(path.exists() for path in gone)
    assert all(path.exists() for path in kept)
    assert client.get(f"/sessions/{sid}", headers=ALICE).status_code == 404


@requires_postgres
def test_the_deletion_is_logged_with_its_reason(client, root, caplog) -> None:
    session = _create(client)
    url = f"/sessions/{session['id']}?reason=owner-left"
    with caplog.at_level(logging.WARNING, logger="wizard_api.routers.sessions"):
        assert client.delete(url, headers=ALICE).status_code == 204
    assert f"session.delete session={session['id']} reason=owner-left" in caplog.text


@requires_postgres
def test_another_user_cannot_delete_it(client, db_session, root) -> None:
    session = _create(client)
    assert client.delete(f"/sessions/{session['id']}", headers=BOB).status_code == 404
    assert _row(db_session, session["id"]) is not None
    assert Path(session["output_dir"]).exists()


@requires_postgres
def test_a_call_that_names_no_user_deletes_nothing(client, db_session, root) -> None:
    session = _create(client)
    res = client.delete(f"/sessions/{session['id']}")
    assert res.status_code == 400
    assert res.json()["detail"]["error"] == "user_required"
    assert _row(db_session, session["id"]) is not None


@requires_postgres
def test_a_protected_session_stays(client, db_session, root) -> None:
    session = _create(client)
    _set_metadata(db_session, session["id"], protected=True)
    res = client.delete(f"/sessions/{session['id']}", headers=ALICE)
    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "session_protected"
    assert _row(db_session, session["id"]) is not None
    assert Path(session["output_dir"]).exists()


@requires_postgres
def test_a_caller_cannot_set_or_clear_protection(client, root) -> None:
    session = _create(client)
    res = client.patch(
        f"/sessions/{session['id']}", json={"metadata": {"protected": True}}, headers=ALICE
    )
    assert res.status_code == 422


@requires_postgres
def test_a_session_in_mid_turn_is_not_deleted(client, db_session, root, monkeypatch) -> None:
    session = _create(client)
    monkeypatch.setattr(agent_service, "is_busy", lambda _sid: True)
    res = client.delete(f"/sessions/{session['id']}", headers=ALICE)
    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "session_busy"
    assert _row(db_session, session["id"]) is not None


@requires_postgres
def test_the_live_agent_is_ended_first(client, root, monkeypatch) -> None:
    session = _create(client)
    ended = []

    async def end(session_id: str) -> bool:
        ended.append((session_id, Path(session["output_dir"]).exists()))
        return True

    monkeypatch.setattr(agent_service, "end_session", end)
    assert client.delete(f"/sessions/{session['id']}", headers=ALICE).status_code == 204
    assert ended == [(session["id"], True)]


@requires_postgres
def test_a_failed_removal_can_be_repeated(client, db_session, root, monkeypatch) -> None:
    session = _create(client)

    def fail(_session) -> None:
        raise RuntimeError("cluster unavailable")

    monkeypatch.setattr(session_removal, "_stop_runs", fail)
    res = client.delete(f"/sessions/{session['id']}", headers=ALICE)
    assert res.status_code == 503
    assert res.json()["detail"]["error"] == "session_delete_failed"
    assert "cluster" not in res.text
    assert _row(db_session, session["id"]) is not None
    assert Path(session["output_dir"]).exists()

    monkeypatch.undo()
    monkeypatch.setenv("WIZARD_SESSION_OUTPUT_ROOT", str(root))
    assert client.delete(f"/sessions/{session['id']}", headers=ALICE).status_code == 204
    assert _row(db_session, session["id"]) is None


@pytest.mark.parametrize(
    "output_dir",
    ["{root}", "{root}/alice", "{root}/../{id}", "/tmp/elsewhere/{id}", "{root}/alice/other"],
)
def test_only_the_sessions_own_folder_is_accepted(root, output_dir) -> None:
    sid = uuid.uuid4()
    session = SimpleNamespace(id=sid, output_dir=output_dir.format(root=root, id=sid))
    with pytest.raises(session_removal.SessionFolderError):
        session_removal.session_folder(session)


def test_the_sessions_folder_is_accepted(root) -> None:
    sid = uuid.uuid4()
    session = SimpleNamespace(id=sid, output_dir=f"{root}/alice/{sid}")
    assert session_removal.session_folder(session) == (root / "alice" / str(sid)).resolve()


def _session(output_dir: Path, **metadata) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), output_dir=str(output_dir), session_metadata=metadata)


def test_the_conversations_the_session_listed_are_its_own(root) -> None:
    session = _session(
        root / "alice" / "s", agent_sdk_session_id=STORED, agent_sdk_session_ids=[EARLIER, STORED]
    )
    _conversation(root, STORED, "latest")
    _conversation(root, EARLIER, "nothing that names the session")
    _conversation(root, OTHER, "another session")
    found = session_removal.conversation_ids(root / ".claude-agent", session)
    assert found == {STORED, EARLIER}


def test_a_transcript_that_only_mentions_the_session_id_is_not_its_own(root) -> None:
    session = _session(root / "alice" / "s", agent_sdk_session_id=STORED)
    _conversation(root, MENTIONS, f"see session {session.id}")
    found = session_removal.conversation_ids(root / ".claude-agent", session)
    # Its stored id is its own; the transcript that only names the id is not.
    assert found == {STORED}


def test_a_conversation_another_session_stored_is_never_this_ones(root) -> None:
    session = _session(root / "alice" / "s", agent_sdk_session_id=STORED)
    _conversation(root, CLAIMED, f"cwd {session.output_dir}")
    _conversation(root, EARLIER, f"cwd {session.output_dir}")
    found = session_removal.conversation_ids(
        root / ".claude-agent", session, frozenset({CLAIMED, STORED})
    )
    # Its own stored id is left out too when another session also claims it.
    assert found == {EARLIER}


def test_stored_ids_of_another_shape_are_not_conversations() -> None:
    metadata = {"agent_sdk_session_id": "../x", "agent_sdk_session_ids": [STORED, 7, "../y"]}
    assert session_removal.stored_conversation_ids(metadata) == {STORED}
    assert session_removal.stored_conversation_ids({"agent_sdk_session_ids": "x"}) == set()


def test_a_stored_id_of_another_shape_reaches_no_path(root) -> None:
    (root / ".claude-agent" / "projects").mkdir(parents=True)
    session = SimpleNamespace(
        id=uuid.uuid4(), session_metadata={"agent_sdk_session_id": "../../other"}
    )
    assert session_removal.conversation_ids(root / ".claude-agent", session) == set()


class _Batch:
    def __init__(self, error=None):
        self.deleted: list[str] = []
        self.error = error

    def delete_namespaced_job(self, name, namespace, propagation_policy):
        if self.error is not None:
            raise self.error
        self.deleted.append(name)


def _runner(batch, labels_seen: list) -> sandbox_runner.SandboxRunner:
    runner = sandbox_runner.SandboxRunner.__new__(sandbox_runner.SandboxRunner)
    runner.namespace = "ns"
    runner._batch = batch
    runner._require_config = lambda: None
    runner._load_clients = lambda: None

    def jobs(**labels):
        labels_seen.append(labels)
        return [SimpleNamespace(metadata=SimpleNamespace(name="job-1"))]

    runner._jobs = jobs
    return runner


def test_every_job_of_the_session_is_deleted() -> None:
    batch, seen = _Batch(), []
    _runner(batch, seen).delete_session_runs("sid")
    assert batch.deleted == ["job-1"]
    assert seen == [{sandbox_runner.SESSION_LABEL: "sid"}]


def test_a_job_already_gone_is_fine_and_other_errors_stop_the_removal() -> None:
    gone = RuntimeError("gone")
    gone.status = 404
    _runner(_Batch(gone), []).delete_session_runs("sid")
    with pytest.raises(RuntimeError):
        _runner(_Batch(RuntimeError("no")), []).delete_session_runs("sid")


def test_a_run_ending_after_the_delete_does_not_bring_the_folder_back(tmp_path) -> None:
    folder = tmp_path / "deleted"
    status = SimpleNamespace(phase="Succeeded", finished=True)
    runner = SimpleNamespace(read_log=lambda _id: "", check_version=lambda _id: "1")
    sessions_router._save_run_for_agent(runner, str(folder), "run-1", status)
    sessions_router._save_check_for_agent(runner, str(folder), "run-1", status)
    assert not folder.exists()


def test_the_operator_command_names_a_reason() -> None:
    with pytest.raises(SystemExit):
        session_admin.main(["delete", str(uuid.uuid4())])
    with pytest.raises(SystemExit):
        session_admin.main(["delete", str(uuid.uuid4()), "--reason", "because"])


@requires_postgres
def test_the_operator_protects_lists_and_deletes(
    client, db_session, root, monkeypatch, capsys
) -> None:
    session = _create(client)
    sid = session["id"]
    session_admin.main(["protect", sid])
    assert _row(db_session, sid).session_metadata["protected"] is True
    session_admin.main(["list", "alice@example.com"])
    assert f"{sid}" in capsys.readouterr().out

    sent = []

    class Opener:
        def open(self, request, timeout):
            sent.append(request)
            return SimpleNamespace(close=lambda: None)

    monkeypatch.setattr(session_admin.urllib.request, "build_opener", lambda *_a: Opener())
    session_admin.main(["delete", sid, "--reason", "owner-left"])
    assert sent[0].get_method() == "DELETE"
    assert sent[0].full_url.endswith(f"/sessions/{sid}?reason=owner-left")
    assert sent[0].get_header(USER_HEADER.capitalize()) == "alice@example.com"
