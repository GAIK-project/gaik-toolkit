"""POST /sessions/{id}/blueprint/operations: diagram edits change the agent's draft.

The full draft (``use_case.blueprint.json``) is the canonical blueprint. An edit
is a list of typed operations applied to it (``blueprint_ops``); the route
writes the new draft, stores it with a new version, and tells the next chat
sync it has nothing to adopt.
"""

import json
import os
import uuid

import pytest
from helpers import requires_postgres, write_gate_artifacts
from test_blueprint_ops import _draft
from wizard_api.models import BlueprintVersion
from wizard_api.ownership import USER_HEADER
from wizard_api.routers import sessions as sessions_router
from wizard_api.schemas.session import SessionUpdate
from wizard_api.services import (
    agent_service,
    artifact_sync,
    blueprint_ops,
    blueprint_service,
    session_service,
)

pytestmark = pytest.mark.skipif(
    not blueprint_ops.solution_wizard_available(),
    reason="solution_wizard package not installed",
)

RENAME = {"op": "rename_step", "step_id": "extract", "name": "Read the invoice"}


def _draft_path(output_dir: str) -> str:
    return os.path.join(output_dir, artifact_sync.DRAFT_BLUEPRINT_FILE)


def _write_draft(output_dir: str, draft: dict | None = None) -> None:
    os.makedirs(output_dir, exist_ok=True)
    with open(_draft_path(output_dir), "w", encoding="utf-8") as fh:
        json.dump(draft if draft is not None else _draft(), fh, indent=2)


def _read_bytes(output_dir: str) -> bytes:
    with open(_draft_path(output_dir), "rb") as fh:
        return fh.read()


def _create(client, user: str = "ops-user", *, draft: bool = True) -> dict:
    created = client.post("/sessions", json={"user_id": user, "title": "Ops"}).json()
    if draft:
        _write_draft(created["output_dir"])
    return created


def _post(client, sid: str, base: int, *operations: dict, headers: dict | None = None):
    return client.post(
        f"/sessions/{sid}/blueprint/operations",
        json={"base_version": base, "operations": list(operations)},
        headers=headers or {},
    )


def _versions(db_session, sid: str) -> list[BlueprintVersion]:
    db_session.expire_all()
    return blueprint_service.list_versions(db_session, uuid.UUID(sid))


def _session(db_session, sid: str):
    db_session.expire_all()
    return session_service.get_session(db_session, uuid.UUID(sid))


@pytest.fixture
def not_busy(monkeypatch):
    monkeypatch.setattr(agent_service, "is_busy", lambda session_id: False)


@requires_postgres
def test_operations_change_the_agents_file_and_add_a_version(client, db_session, not_busy) -> None:
    created = _create(client)
    sid = created["id"]
    base = created["active_version"]

    res = _post(client, sid, base, RENAME)

    assert res.status_code == 200, res.text
    body = res.json()
    on_disk = json.loads(_read_bytes(created["output_dir"]))
    names = {s["id"]: s["name"] for s in on_disk["workflow"]["steps"]}
    assert names["extract"] == "Read the invoice"
    assert body["session"]["active_version"] == base + 1
    assert _session(db_session, sid).active_version == base + 1
    assert {"warnings", "needs_attention", "bpmn_changed"} <= set(body)
    assert body["bpmn_changed"] is True
    # The new version carries the draft as written and its mapped V2 content.
    newest = _versions(db_session, sid)[-1]
    assert newest.draft == on_disk
    assert newest.note.startswith("Workspace edit: ")
    assert "Read the invoice" in newest.note
    assert any(s["name"] == "Read the invoice" for s in newest.content["steps"])
    # Told to the agent with its next turn (Task 9).
    assert body["session"]["metadata"]["pending_user_edits"] == [
        'Renamed step "Extract" to "Read the invoice"'
    ]


@requires_postgres
def test_no_draft_answers_409_no_draft(client, db_session, not_busy) -> None:
    created = _create(client, draft=False)

    res = _post(client, created["id"], created["active_version"], RENAME)

    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "no_draft"


@requires_postgres
def test_a_busy_agent_answers_409_agent_busy_and_changes_nothing(
    client, db_session, monkeypatch
) -> None:
    created = _create(client)
    before = _read_bytes(created["output_dir"])
    monkeypatch.setattr(agent_service, "is_busy", lambda session_id: True)

    res = _post(client, created["id"], created["active_version"], RENAME)

    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "agent_busy"
    assert _read_bytes(created["output_dir"]) == before
    assert len(_versions(db_session, created["id"])) == 1


@requires_postgres
def test_a_stale_base_answers_409_changed_elsewhere(client, db_session, not_busy) -> None:
    created = _create(client)
    sid = created["id"]
    base = created["active_version"]
    assert _post(client, sid, base, RENAME).status_code == 200
    after_first = _read_bytes(created["output_dir"])

    # A second tab still on the first version.
    res = _post(client, sid, base, {**RENAME, "name": "Something else"})

    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "changed_elsewhere"
    assert _read_bytes(created["output_dir"]) == after_first
    assert _session(db_session, sid).active_version == base + 1


@requires_postgres
def test_another_users_session_is_not_found(client, db_session, not_busy) -> None:
    alice = {USER_HEADER: "alice@example.com"}
    bob = {USER_HEADER: "bob@example.com"}
    created = client.post(
        "/sessions", json={"user_id": "alice@example.com", "title": "Ops"}, headers=alice
    ).json()
    _write_draft(created["output_dir"])
    before = _read_bytes(created["output_dir"])

    res = _post(client, created["id"], created["active_version"], RENAME, headers=bob)

    assert res.status_code == 404
    assert _read_bytes(created["output_dir"]) == before
    assert _post(client, created["id"], created["active_version"], RENAME, headers=alice).is_success


@requires_postgres
def test_more_than_50_operations_are_refused(client, db_session, not_busy) -> None:
    created = _create(client)
    before = _read_bytes(created["output_dir"])

    res = _post(client, created["id"], created["active_version"], *([RENAME] * 51))

    assert res.status_code == 422
    assert _read_bytes(created["output_dir"]) == before
    assert len(_versions(db_session, created["id"])) == 1


@requires_postgres
def test_a_body_over_64_kb_is_refused(client, db_session, not_busy) -> None:
    created = _create(client)
    before = _read_bytes(created["output_dir"])
    padded = {**RENAME, "name": "x" * 150}

    res = client.post(
        f"/sessions/{created['id']}/blueprint/operations",
        content=json.dumps({"base_version": created["active_version"], "operations": [padded] * 50})
        + " " * 70_000,
        headers={"content-type": "application/json"},
    )

    assert res.status_code == 413
    assert _read_bytes(created["output_dir"]) == before


@requires_postgres
def test_an_operation_the_draft_cannot_take_answers_422_invalid_operation(
    client, db_session, not_busy
) -> None:
    created = _create(client)
    before = _read_bytes(created["output_dir"])

    res = _post(
        client,
        created["id"],
        created["active_version"],
        RENAME,
        {"op": "rename_step", "step_id": "nowhere", "name": "x"},
    )

    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["error"] == "invalid_operation"
    assert detail["field"] == "step_id"
    assert detail["index"] == 1
    assert detail["code"] == "not_found"
    assert "nowhere" in detail["message"]
    assert _read_bytes(created["output_dir"]) == before
    assert len(_versions(db_session, created["id"])) == 1


@requires_postgres
def test_the_next_chat_sync_does_not_adopt_the_written_draft_again(
    client, db_session, not_busy
) -> None:
    created = _create(client)
    sid = created["id"]
    assert _post(client, sid, created["active_version"], RENAME).status_code == 200
    count = len(_versions(db_session, sid))

    session = _session(db_session, sid)
    sessions_router._sync_artifacts_and_advance(db_session, session)

    assert len(_versions(db_session, sid)) == count
    assert artifact_sync.sync_blueprint_from_draft(db_session, _session(db_session, sid)) is False


@requires_postgres
def test_pending_user_edits_keep_the_last_50(client, db_session, not_busy) -> None:
    created = _create(client)
    sid = created["id"]
    session_service.update_session(
        db_session,
        _session(db_session, sid),
        SessionUpdate(metadata={"pending_user_edits": [f"old {i}" for i in range(50)]}),
    )

    res = _post(client, sid, created["active_version"], RENAME)

    assert res.status_code == 200, res.text
    edits = _session(db_session, sid).session_metadata["pending_user_edits"]
    assert len(edits) == 50
    assert edits[0] == "old 1"
    assert edits[-1] == 'Renamed step "Extract" to "Read the invoice"'


def _approved_through_gate_3(client, db_session) -> dict:
    """A session past Gate 3, its draft a full blueprint the operations can work on."""
    created = client.post("/sessions", json={"user_id": "ops-gate", "title": "Ops"}).json()
    sid = created["id"]
    write_gate_artifacts(created["output_dir"], "gate_3")
    _write_draft(created["output_dir"])
    poc = os.path.join(created["output_dir"], "poc")
    client.patch(f"/sessions/{sid}", json={"step": 4})
    client.patch(f"/sessions/{sid}", json={"gate_statuses": {"gate_1": "approved"}})
    client.patch(f"/sessions/{sid}", json={"step": 9})
    client.patch(f"/sessions/{sid}", json={"gate_statuses": {"gate_2": "approved"}})
    client.patch(f"/sessions/{sid}", json={"step": 10})
    digest = sessions_router._approved_package_digest(poc)
    session_service.update_session(
        db_session,
        _session(db_session, sid),
        SessionUpdate(
            metadata={
                "last_successful_run": "run-1",
                "agent_step": 10,
                session_service.RUN_PACKAGE_KEY: digest,
                session_service.SUCCESSFUL_RUN_PACKAGE_KEY: digest,
            }
        ),
    )
    client.patch(f"/sessions/{sid}", json={"step": 11})
    approved = client.patch(f"/sessions/{sid}", json={"gate_statuses": {"gate_3": "approved"}})
    assert approved.status_code == 200, approved.text
    return approved.json()


@requires_postgres
def test_an_edit_after_gate_3_reopens_gate_2(client, db_session, not_busy) -> None:
    detail = _approved_through_gate_3(client, db_session)
    sid = detail["id"]
    assert detail["gate_statuses"]["gate_3"] == "approved"

    res = _post(
        client,
        sid,
        detail["active_version"],
        {"op": "add_step", "name": "Archive copy", "type": "user_task", "after": "deliver"},
    )

    assert res.status_code == 200, res.text
    session = res.json()["session"]
    assert session["gate_statuses"]["gate_2"] == "pending"
    assert session["gate_statuses"]["gate_3"] == "pending"
    assert session["metadata"]["gate_reopened"]["gate"] == "gate_2"


@requires_postgres
def test_the_first_edit_of_an_old_session_backs_up_its_draft(client, db_session, not_busy) -> None:
    created = _create(client)
    sid = created["id"]
    # Saved before migration 004: the active version has no draft.
    assert all(v.draft is None for v in _versions(db_session, sid))
    before = json.loads(_read_bytes(created["output_dir"]))

    assert _post(client, sid, created["active_version"], RENAME).status_code == 200

    session = _session(db_session, sid)
    previous = blueprint_service.get_previous_draft_version(db_session, session)
    assert previous is not None
    assert previous.version == created["active_version"]
    assert previous.draft == before

    # And undo brings the file as it was before the edit back (Task 12).
    undone = client.post(
        f"/sessions/{sid}/blueprint/undo", json={"base_version": session.active_version}
    )
    assert undone.status_code == 200, undone.text
    assert json.loads(_read_bytes(created["output_dir"])) == before


@requires_postgres
def test_a_session_with_a_stored_draft_is_not_backfilled(client, db_session, not_busy) -> None:
    created = _create(client)
    sid = created["id"]
    stored = {**_draft(), "marker": "kept as stored"}
    session = _session(db_session, sid)
    blueprint_service.add_version(db_session, session, note="stored", content=None, draft=stored)
    db_session.commit()
    base = _session(db_session, sid).active_version

    assert _post(client, sid, base, RENAME).status_code == 200

    by_number = {v.version: v for v in _versions(db_session, sid)}
    # The stored draft is left as it is. The file differed from it, so the file's
    # draft is kept in a version of its own before the edit's version.
    assert by_number[base].draft == stored
    assert by_number[base + 1].note == "Agent changes kept"
    assert by_number[base + 2].draft["workflow"]["steps"][1]["name"] == "Read the invoice"


@requires_postgres
def test_an_old_session_nobody_edits_is_not_touched(client, db_session, not_busy) -> None:
    created = _create(client)
    sid = created["id"]
    before = _read_bytes(created["output_dir"])

    assert client.get(f"/sessions/{sid}").status_code == 200
    client.get(f"/sessions/{sid}/bpmn")

    assert all(v.draft is None for v in _versions(db_session, sid))
    assert _read_bytes(created["output_dir"]) == before


@requires_postgres
def test_a_failure_after_the_write_puts_the_file_back(client, db_session, monkeypatch) -> None:
    monkeypatch.setattr(agent_service, "is_busy", lambda session_id: False)
    created = _create(client)
    sid = created["id"]
    before = _read_bytes(created["output_dir"])

    def broken(*args, **kwargs):
        raise RuntimeError("the database went away")

    monkeypatch.setattr(blueprint_service, "add_version", broken)

    with pytest.raises(RuntimeError):
        _post(client, sid, created["active_version"], RENAME)

    assert _read_bytes(created["output_dir"]) == before
    versions = _versions(db_session, sid)
    assert len(versions) == 1
    # The backfill went with the rest of the transaction.
    assert versions[0].draft is None
    assert _session(db_session, sid).active_version == created["active_version"]


@requires_postgres
def test_a_step_made_an_ai_step_without_a_component_stays_an_ai_step(
    client, db_session, not_busy
) -> None:
    """The diagram's type menu makes a step an AI step: until the agent gives it
    a component, the page shows it as one (``AI_STEPS_KEY``), not as ``io``."""
    created = _create(client)
    sid = created["id"]
    made_ai = {"op": "set_step_type", "step_id": "review", "type": "automated_task"}

    res = _post(client, sid, created["active_version"], made_ai)

    assert res.status_code == 200, res.text
    body = res.json()
    assert "review: needs a component" in body["needs_attention"]
    types = {s["id"]: s["type"] for s in body["session"]["blueprint"]["steps"]}
    assert types["review"] == "ai"
    reloaded = client.get(f"/sessions/{sid}").json()
    assert {s["id"]: s["type"] for s in reloaded["blueprint"]["steps"]}["review"] == "ai"

    # Made a user task again, it is no AI step any more.
    back = {"op": "set_step_type", "step_id": "review", "type": "user_task"}
    res = _post(client, sid, body["session"]["active_version"], back)
    assert res.status_code == 200, res.text
    types = {s["id"]: s["type"] for s in res.json()["session"]["blueprint"]["steps"]}
    assert types["review"] == "io"
