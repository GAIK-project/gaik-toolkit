"""POST /sessions/{id}/blueprint/undo: go back to the draft before the last write.

Every write keeps the full draft with its version, so an undo restores the
draft of an older version as a new version (note ``"Undo"``), through the flow
of an edit. Repeated undos walk back (``undo_cursor``); any other write starts
the walk again from the newest version.
"""

import copy
import json
import os

import pytest
from helpers import requires_postgres
from test_blueprint_operations_api import (
    RENAME,
    _create,
    _post,
    _read_bytes,
    _session,
    _versions,
    _write_draft,
)
from test_blueprint_ops import _draft
from wizard_api.ownership import USER_HEADER
from wizard_api.services import (
    agent_service,
    artifact_sync,
    blueprint_edit_service,
    blueprint_ops,
    blueprint_service,
    session_service,
)

pytestmark = pytest.mark.skipif(
    not blueprint_ops.solution_wizard_available(),
    reason="solution_wizard package not installed",
)


@pytest.fixture
def not_busy(monkeypatch):
    monkeypatch.setattr(agent_service, "is_busy", lambda session_id: False)


def _undo(client, sid: str, base: int):
    return client.post(f"/sessions/{sid}/blueprint/undo", json={"base_version": base})


def _undo_as(client, sid: str, base: int, headers: dict):
    return client.post(
        f"/sessions/{sid}/blueprint/undo", json={"base_version": base}, headers=headers
    )


def _on_disk(output_dir: str) -> dict:
    return json.loads(_read_bytes(output_dir))


def _rename(client, sid: str, name: str) -> dict:
    base = client.get(f"/sessions/{sid}").json()["active_version"]
    res = _post(client, sid, base, {**RENAME, "name": name})
    assert res.status_code == 200, res.text
    return res.json()["session"]


def _active(client, sid: str) -> int:
    return client.get(f"/sessions/{sid}").json()["active_version"]


@requires_postgres
def test_undo_restores_the_previous_drafts_file_and_diagram(client, db_session, not_busy) -> None:
    created = _create(client)
    sid = created["id"]
    original = _on_disk(created["output_dir"])
    edited = _rename(client, sid, "Read the invoice")
    assert "Read the invoice" in client.get(f"/sessions/{sid}/bpmn").text

    res = _undo(client, sid, edited["active_version"])

    assert res.status_code == 200, res.text
    body = res.json()
    assert _on_disk(created["output_dir"]) == original
    assert body["active_version"] == edited["active_version"] + 1
    diagram = client.get(f"/sessions/{sid}/bpmn")
    assert diagram.status_code == 200
    # A step with a component is drawn as "[C] <name>".
    assert 'name="[C] Extract"' in diagram.text
    assert "Read the invoice" not in diagram.text
    newest = _versions(db_session, sid)[-1]
    assert newest.note == "Undo"
    assert newest.draft == original
    assert any(s["name"] == "Extract" for s in newest.content["steps"])
    # The next chat turn adopts nothing, and the agent hears of the undo.
    metadata = body["metadata"]
    assert metadata[artifact_sync.ADOPTED_DRAFT_KEY] == artifact_sync.content_digest(newest.content)
    assert metadata["pending_user_edits"][-1].startswith("Undid the user's workspace edit")


@requires_postgres
def test_undo_with_nothing_before_answers_409(client, db_session, not_busy) -> None:
    created = _create(client)
    sid = created["id"]
    before = _read_bytes(created["output_dir"])

    res = _undo(client, sid, created["active_version"])

    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "nothing_to_undo"
    assert _read_bytes(created["output_dir"]) == before
    assert len(_versions(db_session, sid)) == 1


@requires_postgres
def test_two_edits_then_two_undos_restore_the_original(client, db_session, not_busy) -> None:
    created = _create(client)
    sid = created["id"]
    original = _on_disk(created["output_dir"])
    _rename(client, sid, "First name")
    after_first = _on_disk(created["output_dir"])
    _rename(client, sid, "Second name")

    assert _undo(client, sid, _active(client, sid)).status_code == 200
    assert _on_disk(created["output_dir"]) == after_first

    assert _undo(client, sid, _active(client, sid)).status_code == 200
    assert _on_disk(created["output_dir"]) == original

    # Nothing older is left.
    res = _undo(client, sid, _active(client, sid))
    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "nothing_to_undo"
    assert _on_disk(created["output_dir"]) == original


@requires_postgres
def test_an_edit_after_an_undo_starts_the_walk_again(client, db_session, not_busy) -> None:
    created = _create(client)
    sid = created["id"]
    _rename(client, sid, "First name")
    assert _undo(client, sid, _active(client, sid)).status_code == 200
    before_new_edit = _on_disk(created["output_dir"])
    session = _rename(client, sid, "Second name")
    assert "undo_cursor" not in session["metadata"]

    assert _undo(client, sid, _active(client, sid)).status_code == 200

    assert _on_disk(created["output_dir"]) == before_new_edit


@requires_postgres
def test_an_adopted_agent_draft_starts_the_walk_again(client, db_session, not_busy) -> None:
    created = _create(client)
    sid = created["id"]
    _rename(client, sid, "First name")
    assert _undo(client, sid, _active(client, sid)).status_code == 200
    assert "undo_cursor" in client.get(f"/sessions/{sid}").json()["metadata"]
    agent_draft = _draft()
    agent_draft["workflow"]["steps"][1]["name"] = "Written by the agent"

    session = _session(db_session, sid)
    assert artifact_sync.sync_blueprint_from_draft(db_session, session, agent_draft)

    assert "undo_cursor" not in _session(db_session, sid).session_metadata


@requires_postgres
def test_a_stored_draft_that_no_longer_validates_answers_409_cannot_undo(
    client, db_session, not_busy
) -> None:
    created = _create(client)
    sid = created["id"]
    session = _session(db_session, sid)
    blueprint_service.add_version(
        db_session, session, note="old", content=None, draft={"workflow": "not a workflow"}
    )
    db_session.commit()
    _rename(client, sid, "Read the invoice")
    # The edit kept the file's draft in a version of its own: that is the first
    # step back. The one before it is the stored draft that cannot be restored.
    assert _undo(client, sid, _active(client, sid)).status_code == 200
    before = _read_bytes(created["output_dir"])
    versions = len(_versions(db_session, sid))
    active = _active(client, sid)

    res = _undo(client, sid, active)

    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "cannot_undo"
    assert _read_bytes(created["output_dir"]) == before
    assert len(_versions(db_session, sid)) == versions
    assert _session(db_session, sid).active_version == active


@requires_postgres
def test_undo_while_the_agent_replies_answers_409_agent_busy(
    client, db_session, monkeypatch
) -> None:
    monkeypatch.setattr(agent_service, "is_busy", lambda session_id: False)
    created = _create(client)
    sid = created["id"]
    edited = _rename(client, sid, "Read the invoice")
    before = _read_bytes(created["output_dir"])
    monkeypatch.setattr(agent_service, "is_busy", lambda session_id: True)

    res = _undo(client, sid, edited["active_version"])

    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "agent_busy"
    assert _read_bytes(created["output_dir"]) == before


@requires_postgres
def test_undo_on_a_stale_base_answers_409_changed_elsewhere(client, db_session, not_busy) -> None:
    created = _create(client)
    sid = created["id"]
    edited = _rename(client, sid, "Read the invoice")
    before = _read_bytes(created["output_dir"])

    res = _undo(client, sid, edited["active_version"] - 1)

    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "changed_elsewhere"
    assert _read_bytes(created["output_dir"]) == before


@requires_postgres
def test_undo_of_another_users_session_is_not_found(client, db_session, not_busy) -> None:
    alice = {USER_HEADER: "alice@example.com"}
    bob = {USER_HEADER: "bob@example.com"}
    created = client.post(
        "/sessions", json={"user_id": "alice@example.com", "title": "Undo"}, headers=alice
    ).json()
    sid = created["id"]
    _write_draft(created["output_dir"])
    _post(client, sid, created["active_version"], RENAME, headers=alice)

    res = _undo_as(client, sid, 2, bob)

    assert res.status_code == 404
    assert _undo_as(client, sid, 2, alice).status_code == 200


@requires_postgres
def test_the_undo_cursor_is_server_owned(client, db_session, not_busy) -> None:
    assert "undo_cursor" in session_service.SERVER_OWNED_METADATA_KEYS
    created = _create(client)

    res = client.patch(f"/sessions/{created['id']}", json={"metadata": {"undo_cursor": 1}})

    assert res.status_code >= 400
    assert "undo_cursor" not in _session(db_session, created["id"]).session_metadata


def _write_file(output_dir: str, draft: dict) -> None:
    with open(os.path.join(output_dir, artifact_sync.DRAFT_BLUEPRINT_FILE), "w") as fh:
        json.dump(draft, fh, indent=2)


@requires_postgres
def test_undo_keeps_the_agents_unsaved_work_in_a_version(client, db_session, not_busy) -> None:
    created = _create(client)
    sid = created["id"]
    original = _on_disk(created["output_dir"])
    _rename(client, sid, "First name")
    after_first = _on_disk(created["output_dir"])
    _rename(client, sid, "Second name")
    # The agent changes what the reduced view does not show: no version is added.
    agent_file = _on_disk(created["output_dir"])
    agent_file["business_spec"]["current_process"] = "by hand, written by the agent"
    _write_file(created["output_dir"], agent_file)
    session = _session(db_session, sid)
    assert artifact_sync.sync_blueprint_from_draft(db_session, session) is False
    active = _active(client, sid)

    assert _undo(client, sid, active).status_code == 200

    assert _on_disk(created["output_dir"]) == after_first
    by_number = {v.version: v for v in _versions(db_session, sid)}
    kept = by_number[active + 1]
    assert kept.note == "Before undo"
    assert kept.draft == agent_file
    assert kept.content == by_number[active].content
    assert by_number[active + 2].note == "Undo"
    # The walk goes on past the version restored, not to the kept one.
    assert _undo(client, sid, _active(client, sid)).status_code == 200
    assert _on_disk(created["output_dir"]) == original


@requires_postgres
def test_undo_brings_back_the_ai_step_marks_of_the_version_restored(
    client, db_session, not_busy
) -> None:
    created = _create(client)
    sid = created["id"]
    session = _session(db_session, sid)
    artifact_sync.sync_blueprint_from_draft(db_session, session)
    content = copy.deepcopy(client.get(f"/sessions/{sid}").json()["blueprint"])
    assert content["steps"][0]["id"] == "upload"
    content["steps"][0]["type"] = "ai"
    marked = client.patch(f"/sessions/{sid}/blueprint", json={"content": content})
    assert marked.status_code == 200, marked.text
    assert marked.json()["metadata"][artifact_sync.AI_STEPS_KEY] == ["upload"]
    content = copy.deepcopy(marked.json()["blueprint"])
    content["steps"][0]["component"] = "custom"
    given = client.patch(f"/sessions/{sid}/blueprint", json={"content": content})
    assert given.status_code == 200, given.text
    assert artifact_sync.AI_STEPS_KEY not in given.json()["metadata"]

    res = _undo(client, sid, given.json()["active_version"])

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["blueprint"]["steps"][0]["type"] == "ai"
    assert body["metadata"][artifact_sync.AI_STEPS_KEY] == ["upload"]


@requires_postgres
def test_undo_passes_over_a_version_that_shows_the_same(client, db_session, not_busy) -> None:
    created = _create(client)
    sid = created["id"]
    original = _on_disk(created["output_dir"])
    _rename(client, sid, "First name")
    session = _session(db_session, sid)
    # A version that changed nothing in the draft or its AI steps.
    blueprint_service.add_version(
        db_session,
        session,
        note="same again",
        content=None,
        draft=_on_disk(created["output_dir"]),
    )
    db_session.commit()

    assert _undo(client, sid, _active(client, sid)).status_code == 200

    assert _on_disk(created["output_dir"]) == original


def _agent_changes_a_hidden_field(client, db_session, created: dict) -> dict:
    """The agent edits what the reduced view does not show: its file differs from
    the active version's draft, and the sync adds no version for it."""
    agent_file = _on_disk(created["output_dir"])
    agent_file["business_spec"]["current_process"] = "by hand, written by the agent"
    _write_file(created["output_dir"], agent_file)
    session = _session(db_session, created["id"])
    assert artifact_sync.sync_blueprint_from_draft(db_session, session) is False
    return agent_file


@requires_postgres
def test_an_edit_keeps_the_agents_unsaved_work_in_a_version(client, db_session, not_busy) -> None:
    created = _create(client)
    sid = created["id"]
    _rename(client, sid, "First name")
    agent_file = _agent_changes_a_hidden_field(client, db_session, created)
    active = _active(client, sid)

    edited = _rename(client, sid, "Second name")

    by_number = {v.version: v for v in _versions(db_session, sid)}
    kept = by_number[active + 1]
    assert kept.note == "Agent changes kept"
    assert kept.draft == agent_file
    assert by_number[active + 2].note != "Agent changes kept"
    assert edited["active_version"] == active + 2
    # The undo of the edit gives the agent's work back, not the version before it.
    assert _undo(client, sid, edited["active_version"]).status_code == 200
    assert _on_disk(created["output_dir"]) == agent_file


@requires_postgres
def test_an_edit_adds_no_extra_version_when_the_file_is_the_active_draft(
    client, db_session, not_busy
) -> None:
    created = _create(client)
    sid = created["id"]
    _rename(client, sid, "First name")
    count = len(_versions(db_session, sid))

    _rename(client, sid, "Second name")

    assert len(_versions(db_session, sid)) == count + 1
    assert all(v.note != "Agent changes kept" for v in _versions(db_session, sid))


@requires_postgres
def test_a_failed_edit_leaves_no_version_for_the_agents_work(
    client, db_session, not_busy, monkeypatch
) -> None:
    created = _create(client)
    sid = created["id"]
    _rename(client, sid, "First name")
    agent_file = _agent_changes_a_hidden_field(client, db_session, created)
    count = len(_versions(db_session, sid))
    active = _active(client, sid)
    before = _read_bytes(created["output_dir"])

    def fail(*args, **kwargs):
        raise RuntimeError("the write failed")

    monkeypatch.setattr(blueprint_edit_service.draft_store, "write_draft", fail)
    with pytest.raises(RuntimeError):
        _rename(client, sid, "Second name")

    assert len(_versions(db_session, sid)) == count
    assert _session(db_session, sid).active_version == active
    assert _read_bytes(created["output_dir"]) == before
    assert _on_disk(created["output_dir"]) == agent_file


@requires_postgres
def test_undo_after_kept_agent_work_still_walks_back_one_step_at_a_time(
    client, db_session, not_busy
) -> None:
    created = _create(client)
    sid = created["id"]
    original = _on_disk(created["output_dir"])
    _rename(client, sid, "First name")
    after_first = _on_disk(created["output_dir"])
    agent_file = _agent_changes_a_hidden_field(client, db_session, created)
    edited = _rename(client, sid, "Second name")

    assert _undo(client, sid, edited["active_version"]).status_code == 200
    assert _on_disk(created["output_dir"]) == agent_file
    assert _undo(client, sid, _active(client, sid)).status_code == 200
    assert _on_disk(created["output_dir"]) == after_first
    assert _undo(client, sid, _active(client, sid)).status_code == 200
    assert _on_disk(created["output_dir"]) == original


def _last_edit_note(client, sid: str) -> str:
    return client.get(f"/sessions/{sid}").json()["metadata"]["pending_user_edits"][-1]


@requires_postgres
def test_undo_names_the_users_edit_it_reverts(client, db_session, not_busy) -> None:
    created = _create(client)
    sid = created["id"]
    edited = _rename(client, sid, "Read the invoice")

    assert _undo(client, sid, edited["active_version"]).status_code == 200

    note = _last_edit_note(client, sid)
    assert note == (
        f"Undid the user's workspace edit (version {edited['active_version']}): "
        f"the blueprint is back to version {edited['active_version'] - 1}."
    )
    assert "package" not in note


@requires_postgres
def test_undo_right_after_the_agents_turn_says_the_agents_change_was_undone(
    client, db_session, not_busy
) -> None:
    created = _create(client)
    sid = created["id"]
    _rename(client, sid, "First name")
    agent_draft = _on_disk(created["output_dir"])
    agent_draft["workflow"]["steps"][1]["name"] = "Written by the agent"
    _write_file(created["output_dir"], agent_draft)
    session = _session(db_session, sid)
    assert artifact_sync.sync_blueprint_from_draft(db_session, session)
    agent_version = _active(client, sid)
    assert _versions(db_session, sid)[-1].note == artifact_sync.AGENT_DRAFT_NOTE

    assert _undo(client, sid, agent_version).status_code == 200

    note = _last_edit_note(client, sid)
    assert note.startswith(
        f"Undid the agent's last change (version {agent_version}): "
        f"the blueprint is back to version {agent_version - 1}."
    )
    assert "PoC package" in note and "rebuild" in note
    assert "workspace edit" not in note


@requires_postgres
def test_undo_that_keeps_the_agents_unsaved_file_names_that_version(
    client, db_session, not_busy
) -> None:
    created = _create(client)
    sid = created["id"]
    _rename(client, sid, "First name")
    _rename(client, sid, "Second name")
    _agent_changes_a_hidden_field(client, db_session, created)
    active = _active(client, sid)

    assert _undo(client, sid, active).status_code == 200

    note = _last_edit_note(client, sid)
    assert note.startswith(f"Undid the user's workspace edit (version {active})")
    assert f"kept as version {active + 1}" in note


@requires_postgres
def test_undo_of_a_version_nobody_is_known_to_have_written_claims_no_writer(
    client, db_session, not_busy
) -> None:
    created = _create(client)
    sid = created["id"]
    _rename(client, sid, "First name")
    session = _session(db_session, sid)
    blueprint_service.add_version(
        db_session,
        session,
        note="Vaihe 5",
        content=None,
        draft={**_on_disk(created["output_dir"]), "marker": "x"},
    )
    db_session.commit()
    active = _active(client, sid)

    assert _undo(client, sid, active).status_code == 200

    note = _last_edit_note(client, sid)
    assert note.startswith(f"Undid version {active}: the blueprint is back to version")
    assert not note.startswith(("Undid the user's", "Undid the agent's"))
