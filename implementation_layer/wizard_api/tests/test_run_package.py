"""A test run opens Gate 3 only for the package it tested.

Seen in a policy Q&A walk-through (12 Nov 2026): after the wizard fixed the PoC
the tab still showed the old result with "Run succeeded" and an enabled approve
button. "Succeeded" was kept as the session's proof whatever happened to the
package afterwards, so Gate 3 could be approved on a run of a package that no
longer existed.
"""

import os
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from helpers import requires_postgres, write_gate_artifacts
from wizard_api.routers import sessions as sessions_router
from wizard_api.schemas.session import SessionUpdate
from wizard_api.services import sandbox_runner, session_service

RUN_PACKAGE = session_service.RUN_PACKAGE_KEY
PASSED_PACKAGE = session_service.SUCCESSFUL_RUN_PACKAGE_KEY


def _write_package(output_dir: str) -> str:
    """A complete package with a prompt the run reads; returns its folder."""
    write_gate_artifacts(output_dir, "gate_3")
    poc = os.path.join(output_dir, "poc")
    os.makedirs(os.path.join(poc, "prompts"), exist_ok=True)
    with open(os.path.join(poc, "run_poc.py"), "w", encoding="utf-8") as fh:
        fh.write("from gaik.software_components.extractor import Extractor\n")
    with open(os.path.join(poc, "requirements.txt"), "w", encoding="utf-8") as fh:
        fh.write("gaik[extract]\n")
    with open(os.path.join(poc, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("# PoC\n")
    _write_prompt(poc, "Answer from the numbered policy passages.\n")
    return poc


def _write_prompt(poc: str, text: str) -> None:
    with open(os.path.join(poc, "prompts", "answer.md"), "w", encoding="utf-8") as fh:
        fh.write(text)


@pytest.fixture
def sandbox(monkeypatch):
    """A deployment with a sandbox: Gate 3 then needs a run that succeeded."""
    monkeypatch.setattr(sandbox_runner, "kubernetes_available", lambda: True)
    monkeypatch.setenv("WIZARD_POC_RUNNER_IMAGE", "runner:test")
    monkeypatch.delenv("WIZARD_GATE_READINESS", raising=False)


def _session(output_dir, **metadata):
    """What ``_check_gate_readiness`` reads of a session at the PoC step."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        step=10,
        gate_statuses={"gate_1": "approved", "gate_2": "approved", "gate_3": "pending"},
        session_metadata=metadata,
        output_dir=str(output_dir),
    )


def _approve_gate_3(session) -> None:
    sessions_router._check_gate_readiness(
        session, SessionUpdate(gate_statuses={"gate_3": "approved"})
    )


def test_the_digest_of_a_package_covers_its_prompts(tmp_path) -> None:
    poc = _write_package(str(tmp_path))
    before = sessions_router._approved_package_digest(poc)

    _write_prompt(poc, "Answer in one sentence.\n")

    assert sessions_router._approved_package_digest(poc) != before


def test_a_run_of_the_package_as_it_is_opens_gate_3(tmp_path, sandbox) -> None:
    poc = _write_package(str(tmp_path))
    tested = sessions_router._approved_package_digest(poc)

    _approve_gate_3(_session(tmp_path, last_successful_run="run-1", **{PASSED_PACKAGE: tested}))


def test_a_prompt_changed_after_the_run_keeps_gate_3_closed(tmp_path, sandbox) -> None:
    poc = _write_package(str(tmp_path))
    tested = sessions_router._approved_package_digest(poc)
    session = _session(tmp_path, last_successful_run="run-1", **{PASSED_PACKAGE: tested})

    _write_prompt(poc, "Answer from the passages, and name each one you used.\n")

    with pytest.raises(HTTPException) as refused:
        _approve_gate_3(session)
    assert refused.value.status_code == 409
    assert refused.value.detail == {
        "error": "gate_not_ready",
        "gate": "gate_3",
        "missing": "a successful sandbox run of the package as it is now",
        "reason": "package_changed",
        "message": (
            "The package changed after the last successful test run. "
            "Run the test again, then approve."
        ),
    }

    # The package as it was tested opens the gate again.
    _write_prompt(poc, "Answer from the numbered policy passages.\n")
    _approve_gate_3(session)


def test_changed_code_after_the_run_keeps_gate_3_closed_too(tmp_path, sandbox) -> None:
    poc = _write_package(str(tmp_path))
    tested = sessions_router._approved_package_digest(poc)
    with open(os.path.join(poc, "run_poc.py"), "a", encoding="utf-8") as fh:
        fh.write("print('fixed')\n")

    with pytest.raises(HTTPException) as refused:
        _approve_gate_3(_session(tmp_path, last_successful_run="run-1", **{PASSED_PACKAGE: tested}))
    assert refused.value.detail["reason"] == "package_changed"


def test_a_run_recorded_before_the_digest_was_kept_opens_gate_3_as_it_did(
    tmp_path, sandbox
) -> None:
    poc = _write_package(str(tmp_path))
    _write_prompt(poc, "Changed since the run.\n")

    _approve_gate_3(_session(tmp_path, last_successful_run="run-1"))
    _approve_gate_3(_session(tmp_path, last_successful_run="run-1", **{PASSED_PACKAGE: None}))


class _Rows:
    """One session row, for ``_record_successful_run`` without a database."""

    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _record(monkeypatch, session, run_id: str) -> None:
    """Record ``run_id`` as the session's successful run, as the run stream does."""
    import wizard_api.db

    def update(db, row, payload):
        row.session_metadata = {**row.session_metadata, **payload.metadata}

    monkeypatch.setattr(wizard_api.db, "SessionLocal", lambda: _Rows(session))
    monkeypatch.setattr(session_service, "get_session", lambda db, session_id: session)
    monkeypatch.setattr(session_service, "update_session", update)
    sessions_router._record_successful_run(session.id, run_id)


def test_a_successful_run_without_a_digest_closes_gate_3_after_one_with_a_digest(
    tmp_path, sandbox, monkeypatch
) -> None:
    """Run A passed with its digest, run B passed without one, then the package changed.

    B's record wrote None over A's digest, and None reads as "recorded before
    the digest was kept": Gate 3 was approved without comparing anything.
    """
    poc = _write_package(str(tmp_path))
    tested = sessions_router._approved_package_digest(poc)
    session = _session(tmp_path, latest_run="run-a", **{RUN_PACKAGE: tested})
    _record(monkeypatch, session, "run-a")
    assert session.session_metadata[PASSED_PACKAGE] == tested
    _approve_gate_3(session)

    # Run B is the session's latest, and nothing says which package it started on.
    session.session_metadata = {**session.session_metadata, "latest_run": "run-b"}
    del session.session_metadata[RUN_PACKAGE]
    _record(monkeypatch, session, "run-b")

    assert session.session_metadata["last_successful_run"] == "run-b"
    assert session.session_metadata[PASSED_PACKAGE] == session_service.UNKNOWN_RUN_PACKAGE
    # Neither A's digest nor the package on disk is taken for what B tested.
    with pytest.raises(HTTPException) as unknown:
        _approve_gate_3(session)
    assert unknown.value.detail["reason"] == "package_changed"

    _write_prompt(poc, "Answer from the passages, and name each one you used.\n")

    with pytest.raises(HTTPException) as refused:
        _approve_gate_3(session)
    assert refused.value.status_code == 409
    assert refused.value.detail == {
        "error": "gate_not_ready",
        "gate": "gate_3",
        "missing": "a successful sandbox run of the package as it is now",
        "reason": "package_changed",
        "message": (
            "The last successful test run does not say which package it tested. "
            "Run the test again, then approve."
        ),
    }

    # A run with a known package is the session's proof again.
    current = sessions_router._approved_package_digest(poc)
    session.session_metadata = {
        **session.session_metadata,
        "latest_run": "run-c",
        RUN_PACKAGE: current,
    }
    _record(monkeypatch, session, "run-c")
    assert session.session_metadata[PASSED_PACKAGE] == current
    _approve_gate_3(session)


def test_a_run_without_a_digest_after_a_reopened_gate_closes_gate_3_too(
    tmp_path, sandbox, monkeypatch
) -> None:
    """Reopening a gate leaves the key with None: the session still keeps digests."""
    _write_package(str(tmp_path))
    session = _session(tmp_path, latest_run=None, **{RUN_PACKAGE: None, PASSED_PACKAGE: None})

    _record(monkeypatch, session, "run-elsewhere")

    assert session.session_metadata[PASSED_PACKAGE] == session_service.UNKNOWN_RUN_PACKAGE
    with pytest.raises(HTTPException):
        _approve_gate_3(session)


def test_a_session_that_never_kept_a_digest_records_its_run_as_it_did(
    tmp_path, sandbox, monkeypatch
) -> None:
    _write_package(str(tmp_path))
    session = _session(tmp_path, latest_run="run-old")

    _record(monkeypatch, session, "run-old")

    assert session.session_metadata == {"latest_run": "run-old", "last_successful_run": "run-old"}
    _approve_gate_3(session)


def test_without_a_successful_run_the_gate_asks_for_one_first(tmp_path, sandbox) -> None:
    _write_package(str(tmp_path))

    with pytest.raises(HTTPException) as refused:
        _approve_gate_3(_session(tmp_path))
    assert refused.value.detail["missing"] == "a successful sandbox run"
    assert "reason" not in refused.value.detail


def test_without_a_sandbox_no_run_is_asked_for_and_none_is_compared(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(sandbox_runner, "kubernetes_available", lambda: False)
    _write_package(str(tmp_path))

    _approve_gate_3(_session(tmp_path, last_successful_run="run-1", **{PASSED_PACKAGE: "other"}))


def test_only_a_new_approval_of_gate_3_is_checked(tmp_path, sandbox) -> None:
    _write_package(str(tmp_path))
    session = _session(tmp_path, last_successful_run="run-1", **{PASSED_PACKAGE: "other"})

    # Gate 4, and a patch that approves nothing, do not read the package.
    session.gate_statuses["gate_3"] = "approved"
    sessions_router._check_gate_readiness(
        session, SessionUpdate(gate_statuses={"gate_3": "approved", "gate_4": "approved"})
    )
    sessions_router._check_gate_readiness(session, SessionUpdate(metadata={"title": "t"}))


# -- through the API: the digest is kept with the run, and goes with it ----------


class _Starts:
    """A sandbox that starts every run it is asked for."""

    runs: list[str] = []

    def __init__(self, *args, **kwargs):
        pass

    def create_run(self, session_id, user_id=None):
        run_id = f"run-{len(self.runs) + 1}"
        self.runs.append(run_id)
        return run_id


def _session_at_the_poc_step(client, monkeypatch, user: str) -> dict:
    monkeypatch.setattr(sandbox_runner, "SandboxRunner", type("S", (_Starts,), {"runs": []}))
    created = client.post("/sessions", json={"user_id": user, "title": "Run"}).json()
    sid = created["id"]
    _write_package(created["output_dir"])
    client.patch(f"/sessions/{sid}", json={"step": 4})
    client.patch(f"/sessions/{sid}", json={"gate_statuses": {"gate_1": "approved"}})
    client.patch(f"/sessions/{sid}", json={"step": 9})
    client.patch(f"/sessions/{sid}", json={"gate_statuses": {"gate_2": "approved"}})
    client.patch(f"/sessions/{sid}", json={"step": 10})
    return created


def _metadata(client, db_session, sid: str) -> dict:
    db_session.expire_all()
    return client.get(f"/sessions/{sid}").json()["metadata"]


def _approve(client, sid: str):
    return client.patch(f"/sessions/{sid}", json={"gate_statuses": {"gate_3": "approved"}})


@requires_postgres
def test_a_successful_run_with_no_later_change_is_approved(
    client, db_session, monkeypatch, sandbox
) -> None:
    created = _session_at_the_poc_step(client, monkeypatch, "run-same")
    sid = created["id"]
    digest = sessions_router._approved_package_digest(os.path.join(created["output_dir"], "poc"))

    started = client.post(f"/sessions/{sid}/runs")
    assert started.status_code == 201
    run_id = started.json()["run_id"]
    assert _metadata(client, db_session, sid)[RUN_PACKAGE] == digest
    assert client.get(f"/sessions/{sid}/poc/files").json()["package_digest"] == digest

    sessions_router._record_successful_run(uuid.UUID(sid), run_id)
    metadata = _metadata(client, db_session, sid)
    assert metadata["last_successful_run"] == run_id
    assert metadata[PASSED_PACKAGE] == digest

    approved = _approve(client, sid)
    assert approved.status_code == 200
    assert approved.json()["gate_statuses"]["gate_3"] == "approved"


@requires_postgres
def test_a_prompt_edited_after_the_successful_run_refuses_the_approval(
    client, db_session, monkeypatch, sandbox
) -> None:
    created = _session_at_the_poc_step(client, monkeypatch, "run-stale")
    sid = created["id"]
    poc = os.path.join(created["output_dir"], "poc")
    run_id = client.post(f"/sessions/{sid}/runs").json()["run_id"]
    sessions_router._record_successful_run(uuid.UUID(sid), run_id)
    db_session.expire_all()

    _write_prompt(poc, "Answer from the passages, and name each one you used.\n")

    refused = _approve(client, sid)
    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert detail["error"] == "gate_not_ready"
    assert detail["gate"] == "gate_3"
    assert detail["reason"] == "package_changed"
    assert "Run the test again" in detail["message"]
    assert client.get(f"/sessions/{sid}").json()["gate_statuses"]["gate_3"] == "pending"
    current = client.get(f"/sessions/{sid}/poc/files").json()["package_digest"]
    assert current != _metadata(client, db_session, sid)[PASSED_PACKAGE]

    # A run of the changed package is the session's proof again.
    again = client.post(f"/sessions/{sid}/runs").json()["run_id"]
    sessions_router._record_successful_run(uuid.UUID(sid), again)
    db_session.expire_all()
    assert _metadata(client, db_session, sid)[PASSED_PACKAGE] == current
    assert _approve(client, sid).status_code == 200


@requires_postgres
def test_a_session_whose_run_has_no_digest_is_approved_as_before(
    client, db_session, monkeypatch, sandbox
) -> None:
    created = _session_at_the_poc_step(client, monkeypatch, "run-legacy")
    sid = created["id"]
    session = session_service.get_session(db_session, uuid.UUID(sid))
    session_service.update_session(
        db_session, session, SessionUpdate(metadata={"last_successful_run": "run-old"})
    )
    _write_prompt(os.path.join(created["output_dir"], "poc"), "Changed since the run.\n")

    assert _approve(client, sid).status_code == 200


@requires_postgres
def test_a_run_recorded_without_its_digest_keeps_gate_3_closed(
    client, db_session, monkeypatch, sandbox
) -> None:
    """A run the session did not start through ``create_poc_run`` says nothing of the package.

    It does not keep the older run's digest, and it does not turn the check
    off either: Gate 3 waits for a run whose package is known.
    """
    created = _session_at_the_poc_step(client, monkeypatch, "run-unknown")
    sid = created["id"]
    run_id = client.post(f"/sessions/{sid}/runs").json()["run_id"]
    sessions_router._record_successful_run(uuid.UUID(sid), run_id)
    db_session.expire_all()
    session = session_service.get_session(db_session, uuid.UUID(sid))
    session_service.update_session(
        db_session, session, SessionUpdate(metadata={"latest_run": None})
    )

    sessions_router._record_successful_run(uuid.UUID(sid), "run-elsewhere")

    metadata = _metadata(client, db_session, sid)
    assert metadata["last_successful_run"] == "run-elsewhere"
    assert metadata[PASSED_PACKAGE] == session_service.UNKNOWN_RUN_PACKAGE

    _write_prompt(os.path.join(created["output_dir"], "poc"), "Changed since the runs.\n")
    refused = _approve(client, sid)
    assert refused.status_code == 409
    assert refused.json()["detail"]["reason"] == "package_changed"
    assert client.get(f"/sessions/{sid}").json()["gate_statuses"]["gate_3"] == "pending"

    again = client.post(f"/sessions/{sid}/runs").json()["run_id"]
    sessions_router._record_successful_run(uuid.UUID(sid), again)
    db_session.expire_all()
    assert _approve(client, sid).status_code == 200


@requires_postgres
def test_reopening_a_gate_clears_the_digests_with_the_runs(
    client, db_session, monkeypatch, sandbox
) -> None:
    created = _session_at_the_poc_step(client, monkeypatch, "run-reopen")
    sid = created["id"]
    run_id = client.post(f"/sessions/{sid}/runs").json()["run_id"]
    sessions_router._record_successful_run(uuid.UUID(sid), run_id)
    db_session.expire_all()
    assert _approve(client, sid).status_code == 200

    client.post(f"/sessions/{sid}/gates/2/reopen")

    metadata = _metadata(client, db_session, sid)
    for key in ("last_successful_run", "latest_run", RUN_PACKAGE, PASSED_PACKAGE):
        assert metadata[key] is None


@requires_postgres
def test_the_digests_are_the_servers_own(client) -> None:
    sid = client.post("/sessions", json={"user_id": "run-keys", "title": "K"}).json()["id"]

    for key in (RUN_PACKAGE, PASSED_PACKAGE):
        refused = client.patch(
            f"/sessions/{sid}", json={"metadata": {key: "made up by the client"}}
        )
        assert refused.status_code == 422
        assert refused.json()["detail"]["keys"] == [key]
