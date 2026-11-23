"""The diagram is drawn from the agent's full draft, and the old saves change it.

``use_case.blueprint.json`` is the canonical blueprint. ``GET /bpmn`` draws it as
it is (its lanes, its data objects' names), and the Blueprint form's PATCH and
the diagram's ``/bpmn/sync`` apply what they changed to it as operations, through
the same flow as ``POST /blueprint/operations``.
"""

import copy
import json
import os
import re
import uuid

import pytest
from helpers import requires_postgres
from test_blueprint_ops import _draft
from wizard_api.services import (
    agent_service,
    artifact_sync,
    blueprint_ops,
    blueprint_service,
    bpmn_service,
    session_service,
)

pytestmark = pytest.mark.skipif(
    not blueprint_ops.solution_wizard_available(),
    reason="solution_wizard package not installed",
)


def _labelled_draft() -> dict:
    draft = _draft()
    draft["artifacts"]["fields"]["label"] = "Invoice fields"
    return draft


def _draft_path(output_dir: str) -> str:
    return os.path.join(output_dir, artifact_sync.DRAFT_BLUEPRINT_FILE)


def _read_draft(output_dir: str) -> dict:
    with open(_draft_path(output_dir), encoding="utf-8") as fh:
        return json.load(fh)


def _create(client, db_session, *, draft: dict | None = None) -> dict:
    """A session whose agent has written ``draft`` and whose blueprint shows it."""
    created = client.post("/sessions", json={"user_id": "patch-user", "title": "Patch"}).json()
    os.makedirs(created["output_dir"], exist_ok=True)
    with open(_draft_path(created["output_dir"]), "w", encoding="utf-8") as fh:
        json.dump(draft if draft is not None else _labelled_draft(), fh)
    # As after the chat turn that wrote it.
    session = session_service.get_session(db_session, uuid.UUID(created["id"]))
    artifact_sync.sync_blueprint_from_draft(db_session, session)
    return client.get(f"/sessions/{created['id']}").json()


def _versions(db_session, sid: str):
    db_session.expire_all()
    return blueprint_service.list_versions(db_session, uuid.UUID(sid))


def _lanes(xml: str) -> set[str]:
    return set(re.findall(r'<bpmn:lane id="[^"]*" name="([^"]*)"', xml))


@pytest.fixture
def not_busy(monkeypatch):
    monkeypatch.setattr(agent_service, "is_busy", lambda session_id: False)


# ---------------------------------------------------------------- the diagram


@pytest.mark.parametrize("data_objects", [True, False])
def test_the_diagram_has_the_drafts_lanes_and_data_names(data_objects) -> None:
    draft = _labelled_draft()
    reduced = artifact_sync.blueprint_from_draft(draft).model_dump()

    xml, mapping, drawn_from = bpmn_service.generate_bpmn_view(
        reduced, session_id="s", agent_draft=draft, include_data_objects=data_objects
    )

    assert {"Clerk", "AI system"} <= _lanes(xml)
    # Drawn from the draft itself: its manual step and its decision are there.
    assert "Archive" in xml
    assert "Readable?" in xml
    assert drawn_from["use_case"]["id"] == "invoices"
    if data_objects:
        assert 'name="Invoice fields"' in xml
        assert any(info["kind"] == "data_object" for info in mapping.values())
    else:
        assert "dataObjectReference" not in xml
        assert all(info["kind"] != "data_object" for info in mapping.values())


def test_a_draft_that_is_no_blueprint_falls_back() -> None:
    draft = _labelled_draft()
    reduced = artifact_sync.blueprint_from_draft(draft).model_dump()
    del draft["use_case"]

    xml = bpmn_service.generate_bpmn_xml(reduced, session_id="s", agent_draft=draft)

    assert "<bpmn:definitions" in xml
    assert "Archive" not in xml


def test_a_stored_mapping_is_not_the_one_returned() -> None:
    draft = _labelled_draft()
    draft["visualizations"] = {"bpmn_mapping": {"Activity_gone": {"kind": "step"}}}
    reduced = artifact_sync.blueprint_from_draft(draft).model_dump()

    _, mapping, _ = bpmn_service.generate_bpmn_view(reduced, session_id="s", agent_draft=draft)

    assert "Activity_gone" not in mapping


@requires_postgres
@pytest.mark.parametrize("data_objects", [0, 1])
def test_the_mapping_names_the_elements_of_the_diagram(client, db_session, data_objects) -> None:
    created = _create(client, db_session)
    sid = created["id"]
    params = {"data_objects": data_objects}

    xml = client.get(f"/sessions/{sid}/bpmn", params=params).text
    res = client.get(f"/sessions/{sid}/bpmn/mapping", params=params)

    assert res.status_code == 200, res.text
    assert res.headers["Cache-Control"] == "no-store"
    mapping = res.json()["mapping"]
    assert mapping
    ids = set(re.findall(r' id="([^"]+)"', xml))
    assert set(mapping) <= ids
    # Paths into the draft, whose steps are in its own order.
    assert mapping["Activity_extract"] == {
        "kind": "automated_task",
        "blueprint_path": "workflow.steps[1]",
        "performed_by": "",
    }
    assert mapping["Lane_clerk"]["participant_id"] == "clerk"
    assert any(info["kind"] == "manual_step" for info in mapping.values())
    assert all("blueprint_path" in info for info in mapping.values())
    assert any(info["kind"] == "data_object" for info in mapping.values()) == bool(data_objects)


@requires_postgres
def test_the_mapping_says_whether_the_agent_has_written_its_draft(client, db_session) -> None:
    with_draft = _create(client, db_session)
    without = client.post("/sessions", json={"user_id": "patch-user", "title": "No draft"}).json()

    assert client.get(f"/sessions/{with_draft['id']}/bpmn/mapping").json()["has_draft"] is True
    res = client.get(f"/sessions/{without['id']}/bpmn/mapping")
    assert res.status_code == 200, res.text
    assert res.json()["has_draft"] is False


@requires_postgres
def test_the_mapping_is_served_to_the_owner_only(client, db_session) -> None:
    from wizard_api.ownership import USER_HEADER

    alice = {USER_HEADER: "alice@example.com"}
    created = client.post(
        "/sessions", json={"user_id": "alice@example.com", "title": "Map"}, headers=alice
    ).json()

    res = client.get(
        f"/sessions/{created['id']}/bpmn/mapping", headers={USER_HEADER: "bob@example.com"}
    )

    assert res.status_code == 404


@requires_postgres
def test_the_mapping_refuses_other_option_values(client, db_session) -> None:
    created = _create(client, db_session)
    res = client.get(f"/sessions/{created['id']}/bpmn/mapping", params={"data_objects": 2})
    assert res.status_code == 422


# ---------------------------------------------------------------- PATCH /blueprint


@requires_postgres
def test_a_patch_with_a_draft_changes_the_draft(client, db_session, not_busy) -> None:
    created = _create(client, db_session)
    sid = created["id"]
    content = copy.deepcopy(created["blueprint"])
    content["steps"][1]["name"] = "Read the invoice"
    content["steps"].insert(3, {"id": "new-1", "name": "Check totals", "type": "io"})

    res = client.patch(f"/sessions/{sid}/blueprint", json={"content": content, "note": "Form"})

    assert res.status_code == 200, res.text
    body = res.json()
    on_disk = _read_draft(created["output_dir"])
    steps = on_disk["workflow"]["steps"]
    assert [s["id"] for s in steps] == ["upload", "extract", "review", "check_totals", "deliver"]
    assert steps[1]["name"] == "Read the invoice"
    # The rest of the draft is the agent's still.
    assert on_disk["business_process"]["participants"][0]["name"] == "Clerk"
    assert on_disk["artifacts"]["fields"]["label"] == "Invoice fields"
    assert body["active_version"] == created["active_version"] + 1
    assert [s["name"] for s in body["blueprint"]["steps"]][1] == "Read the invoice"
    newest = _versions(db_session, sid)[-1]
    assert newest.draft == on_disk
    assert newest.note == "Form"
    # Told to the agent with its next turn, as an edit in the diagram is.
    assert body["metadata"]["pending_user_edits"] == [
        'Added user task "Check totals" after "Review"',
        'Renamed step "Extract" to "Read the invoice"',
    ]


@requires_postgres
def test_a_patch_that_changes_nothing_adds_no_version(client, db_session, not_busy) -> None:
    created = _create(client, db_session)
    before = _read_draft(created["output_dir"])

    res = client.patch(
        f"/sessions/{created['id']}/blueprint", json={"content": created["blueprint"]}
    )

    assert res.status_code == 200, res.text
    assert res.json()["active_version"] == created["active_version"]
    assert _read_draft(created["output_dir"]) == before


@requires_postgres
def test_a_stale_patch_answers_409(client, db_session, not_busy) -> None:
    created = _create(client, db_session)
    sid = created["id"]
    base = created["active_version"]
    content = copy.deepcopy(created["blueprint"])
    content["steps"][0]["name"] = "Send the invoice"
    first = client.patch(
        f"/sessions/{sid}/blueprint", json={"content": content, "base_version": base}
    )
    assert first.status_code == 200, first.text
    after_first = _read_draft(created["output_dir"])

    # A second tab still on the first version.
    content["steps"][0]["name"] = "Something else"
    res = client.patch(
        f"/sessions/{sid}/blueprint", json={"content": content, "base_version": base}
    )

    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "changed_elsewhere"
    assert _read_draft(created["output_dir"]) == after_first
    assert len(_versions(db_session, sid)) == len(created["versions"]) + 1


@requires_postgres
def test_a_stale_patch_without_a_draft_answers_409(client, db_session) -> None:
    created = client.post("/sessions", json={"user_id": "patch-user", "title": "No draft"}).json()
    sid = created["id"]
    content = {"name": "X", "steps": [{"id": "a", "name": "A", "type": "io"}]}
    assert client.patch(f"/sessions/{sid}/blueprint", json={"content": content}).status_code == 200

    res = client.patch(
        f"/sessions/{sid}/blueprint",
        json={"content": content, "base_version": created["active_version"]},
    )

    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "changed_elsewhere"


@requires_postgres
def test_a_patch_without_a_draft_stores_the_content_as_before(client, db_session) -> None:
    created = client.post("/sessions", json={"user_id": "patch-user", "title": "No draft"}).json()
    content = {"name": "X", "goal": "G", "steps": [{"id": "a", "name": "A", "type": "io"}]}

    res = client.patch(
        f"/sessions/{created['id']}/blueprint",
        json={"content": content, "base_version": created["active_version"]},
    )

    assert res.status_code == 200, res.text
    assert res.json()["blueprint"]["goal"] == "G"
    assert not os.path.exists(_draft_path(created["output_dir"]))


@requires_postgres
def test_a_patch_while_the_agent_replies_answers_409(client, db_session, monkeypatch) -> None:
    created = _create(client, db_session)
    monkeypatch.setattr(agent_service, "is_busy", lambda session_id: True)
    content = copy.deepcopy(created["blueprint"])
    content["steps"][0]["name"] = "Send the invoice"

    res = client.patch(f"/sessions/{created['id']}/blueprint", json={"content": content})

    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "agent_busy"


@requires_postgres
def test_every_field_of_the_form_round_trips_through_the_draft(
    client, db_session, not_busy
) -> None:
    created = _create(client, db_session)
    sid = created["id"]
    content = copy.deepcopy(created["blueprint"])
    content["name"] = "Supplier invoices"
    content["description"] = "Reads supplier invoices"
    content["goal"] = "Book invoices without typing"
    content["integration_targets"] = ["Accounting system"]
    content["steps"][1]["component"] = "extractor"
    content["steps"][1]["settings"] = {"language": "fi"}

    res = client.patch(f"/sessions/{sid}/blueprint", json={"content": content})

    assert res.status_code == 200, res.text
    on_disk = _read_draft(created["output_dir"])
    assert on_disk["use_case"]["name"] == "Supplier invoices"
    assert on_disk["use_case"]["description"] == "Reads supplier invoices"
    assert on_disk["business_spec"]["poc_goal"] == "Book invoices without typing"
    assert on_disk["technical_spec"]["integration_targets"] == ["Accounting system"]
    extract = on_disk["workflow"]["steps"][1]
    assert (extract["component"], extract["parameters"]) == ("extractor", {"language": "fi"})
    # Back in the reduced view the form reads, as the form sent it.
    body = res.json()
    for key in ("name", "description", "goal", "integration_targets"):
        assert body["blueprint"][key] == content[key]
    shown = body["blueprint"]["steps"][1]
    assert (shown["component"], shown["settings"]) == ("extractor", {"language": "fi"})
    assert _versions(db_session, sid)[-1].draft == on_disk
    # Told to the agent as the operations are.
    assert body["metadata"]["pending_user_edits"] == [
        'Renamed the use case to "Supplier invoices"',
        "Changed the use case's description",
        "Changed the goal of the proof of concept",
        'Changed the integration targets to "Accounting system"',
        'Set the component of step "Extract" to "extractor"',
        'Changed the settings of step "Extract"',
    ]
    # Saved again as it came back: nothing changes.
    again = client.patch(f"/sessions/{sid}/blueprint", json={"content": body["blueprint"]})
    assert again.json()["active_version"] == body["active_version"]


@requires_postgres
def test_a_save_of_step_edits_and_the_goal_applies_both(client, db_session, not_busy) -> None:
    created = _create(client, db_session)
    content = copy.deepcopy(created["blueprint"])
    content["goal"] = "Something new"
    content["steps"][0]["name"] = "Send the invoice"

    res = client.patch(f"/sessions/{created['id']}/blueprint", json={"content": content})

    assert res.status_code == 200, res.text
    on_disk = _read_draft(created["output_dir"])
    assert on_disk["business_spec"]["poc_goal"] == "Something new"
    assert on_disk["workflow"]["steps"][0]["name"] == "Send the invoice"


@requires_postgres
def test_a_step_made_ai_without_a_component_stays_ai(client, db_session, not_busy) -> None:
    created = _create(client, db_session)
    sid = created["id"]
    content = copy.deepcopy(created["blueprint"])
    content["steps"][0]["type"] = "ai"
    content["steps"].append({"id": "tmp", "name": "Classify", "type": "ai"})

    res = client.patch(f"/sessions/{sid}/blueprint", json={"content": content})

    assert res.status_code == 200, res.text
    on_disk = {s["id"]: s for s in _read_draft(created["output_dir"])["workflow"]["steps"]}
    for step_id in ("upload", "classify"):
        assert on_disk[step_id]["type"] == "automated_task"
        assert not on_disk[step_id].get("component")
    body = res.json()
    types = {s["id"]: s["type"] for s in body["blueprint"]["steps"]}
    assert (types["upload"], types["classify"]) == ("ai", "ai")
    assert body["metadata"][artifact_sync.AI_STEPS_KEY] == ["classify", "upload"]
    # The next chat turn, the agent's draft untouched, keeps what the user sees.
    session = session_service.get_session(db_session, uuid.UUID(sid))
    db_session.refresh(session)
    assert artifact_sync.sync_blueprint_from_draft(db_session, session) is False
    # Made io again, the step is a user task and no longer remembered as AI.
    content = copy.deepcopy(body["blueprint"])
    content["steps"][0]["type"] = "io"
    res = client.patch(f"/sessions/{sid}/blueprint", json={"content": content})
    assert res.status_code == 200, res.text
    assert res.json()["blueprint"]["steps"][0]["type"] == "io"
    assert res.json()["metadata"][artifact_sync.AI_STEPS_KEY] == ["classify"]


@requires_postgres
def test_a_key_the_draft_has_no_place_for_is_refused(client, db_session, not_busy) -> None:
    created = _create(client, db_session)
    before = _read_draft(created["output_dir"])
    content = copy.deepcopy(created["blueprint"])
    content["custom"] = "typed in the JSON editor"
    content["steps"][0]["name"] = "Send the invoice"

    res = client.patch(f"/sessions/{created['id']}/blueprint", json={"content": content})

    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["error"] == "unsupported_edit"
    assert detail["fields"] == ["custom"]
    # Nothing of the save is applied, the step's new name neither.
    assert _read_draft(created["output_dir"]) == before
    assert len(_versions(db_session, created["id"])) == len(created["versions"])


def _legacy_version(db_session, sid: str, content: dict) -> None:
    """A version the form saved before the saves went into the draft."""
    session = session_service.get_session(db_session, uuid.UUID(sid))
    blueprint_service.add_version(db_session, session, note="Blueprint päivitetty", content=content)
    db_session.commit()


@requires_postgres
def test_an_earlier_form_edit_is_carried_into_the_draft(client, db_session, not_busy) -> None:
    created = _create(client, db_session)
    sid = created["id"]
    legacy = copy.deepcopy(created["blueprint"])
    legacy["goal"] = "Goal from an earlier save"
    legacy["steps"][1]["component"] = "extractor"
    _legacy_version(db_session, sid, legacy)
    shown = client.get(f"/sessions/{sid}").json()["blueprint"]
    content = copy.deepcopy(shown)
    content["steps"][0]["name"] = "Send the invoice"

    res = client.patch(f"/sessions/{sid}/blueprint", json={"content": content})

    assert res.status_code == 200, res.text
    on_disk = _read_draft(created["output_dir"])
    assert on_disk["business_spec"]["poc_goal"] == "Goal from an earlier save"
    assert on_disk["workflow"]["steps"][1]["component"] == "extractor"
    body = res.json()["blueprint"]
    assert body["goal"] == "Goal from an earlier save"
    assert body["steps"][1]["component"] == "extractor"


@requires_postgres
def test_an_old_label_for_no_artifact_of_the_draft(client, db_session, not_busy) -> None:
    created = _create(client, db_session)
    sid = created["id"]
    legacy = copy.deepcopy(created["blueprint"])
    legacy["data_objects"] = {"out_1": "Old label", "fields": "Extracted fields"}
    _legacy_version(db_session, sid, legacy)
    shown = client.get(f"/sessions/{sid}").json()["blueprint"]

    # Kept as it was, it has nowhere to go and is left; the label of an
    # artifact the draft has is carried into it.
    content = copy.deepcopy(shown)
    content["steps"][0]["name"] = "Send the invoice"
    res = client.patch(f"/sessions/{sid}/blueprint", json={"content": content})
    assert res.status_code == 200, res.text
    assert _read_draft(created["output_dir"])["artifacts"]["fields"]["label"] == "Extracted fields"

    # Changed in this save, it is refused.
    shown = res.json()["blueprint"]
    content = {**copy.deepcopy(shown), "data_objects": {"out_1": "New label"}}
    res = client.patch(f"/sessions/{sid}/blueprint", json={"content": content})
    assert res.status_code == 422
    assert res.json()["detail"]["fields"] == ["data_objects[out_1]"]


@requires_postgres
def test_a_patch_the_draft_cannot_take_answers_422(client, db_session, not_busy) -> None:
    created = _create(client, db_session)
    content = copy.deepcopy(created["blueprint"])
    content["steps"][0]["name"] = "   "

    res = client.patch(f"/sessions/{created['id']}/blueprint", json={"content": content})

    assert res.status_code == 422
    assert res.json()["detail"]["error"] == "invalid_operation"


# ---------------------------------------------------------------- /bpmn/sync


def _rename_task(xml: str, step_id: str, name: str) -> str:
    edited, count = re.subn(rf'(id="Activity_{step_id}" name=")[^"]*(")', rf"\g<1>{name}\g<2>", xml)
    assert count == 1
    return edited


@requires_postgres
@pytest.mark.parametrize("data_objects", [0, 1])
def test_a_canvas_save_with_a_draft_changes_the_draft(
    client, db_session, not_busy, data_objects
) -> None:
    created = _create(client, db_session)
    sid = created["id"]
    xml = client.get(f"/sessions/{sid}/bpmn", params={"data_objects": data_objects}).text

    res = client.post(
        f"/sessions/{sid}/bpmn/sync",
        params={"data_objects": data_objects},
        json={"xml": _rename_task(xml, "extract", "Read the invoice")},
    )

    assert res.status_code == 200, res.text
    on_disk = _read_draft(created["output_dir"])
    names = {s["id"]: s["name"] for s in on_disk["workflow"]["steps"]}
    assert names["extract"] == "Read the invoice"
    # Only the rename: the steps and everything else the canvas shows are as they were.
    expected = _labelled_draft()
    expected["workflow"]["steps"][1]["name"] = "Read the invoice"
    assert on_disk == expected
    body = res.json()
    assert body["active_version"] == created["active_version"] + 1
    assert body["metadata"]["pending_user_edits"] == [
        'Renamed step "Extract" to "Read the invoice"'
    ]
    assert _versions(db_session, sid)[-1].note == "BPMN canvas sync"


@requires_postgres
def test_an_unchanged_canvas_with_a_draft_adds_no_version(client, db_session, not_busy) -> None:
    created = _create(client, db_session)
    sid = created["id"]
    before = _read_draft(created["output_dir"])
    xml = client.get(f"/sessions/{sid}/bpmn").text

    res = client.post(f"/sessions/{sid}/bpmn/sync", json={"xml": xml})

    assert res.status_code == 200, res.text
    assert res.json()["active_version"] == created["active_version"]
    assert _read_draft(created["output_dir"]) == before


@requires_postgres
def test_a_renamed_data_object_on_the_canvas_becomes_its_label(
    client, db_session, not_busy
) -> None:
    created = _create(client, db_session)
    sid = created["id"]
    xml = client.get(f"/sessions/{sid}/bpmn").text
    edited = xml.replace('name="Invoice fields"', 'name="All the fields"')
    assert edited != xml

    res = client.post(
        f"/sessions/{sid}/bpmn/sync", json={"xml": _rename_task(edited, "extract", "Read it")}
    )

    assert res.status_code == 200, res.text
    on_disk = _read_draft(created["output_dir"])
    assert on_disk["artifacts"]["fields"]["label"] == "All the fields"
    assert on_disk["workflow"]["steps"][1]["name"] == "Read it"
    assert 'name="All the fields"' in client.get(f"/sessions/{sid}/bpmn").text


@requires_postgres
def test_a_renamed_gateway_on_the_canvas_is_ignored(client, db_session, not_busy) -> None:
    created = _create(client, db_session)
    sid = created["id"]
    xml = client.get(f"/sessions/{sid}/bpmn").text
    edited = xml.replace('name="Readable?"', 'name="Can it be read?"')
    assert edited != xml

    res = client.post(
        f"/sessions/{sid}/bpmn/sync", json={"xml": _rename_task(edited, "extract", "Read it")}
    )

    assert res.status_code == 200, res.text
    expected = _labelled_draft()
    expected["workflow"]["steps"][1]["name"] = "Read it"
    assert _read_draft(created["output_dir"]) == expected


@requires_postgres
def test_a_canvas_save_while_the_agent_replies_answers_409(client, db_session, monkeypatch) -> None:
    created = _create(client, db_session)
    sid = created["id"]
    xml = client.get(f"/sessions/{sid}/bpmn").text
    monkeypatch.setattr(agent_service, "is_busy", lambda session_id: True)

    res = client.post(
        f"/sessions/{sid}/bpmn/sync", json={"xml": _rename_task(xml, "extract", "Other")}
    )

    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "agent_busy"


@requires_postgres
def test_an_ai_step_whose_component_is_cleared_in_the_form_stays_ai(
    client, db_session, not_busy
) -> None:
    created = _create(client, db_session)
    content = copy.deepcopy(created["blueprint"])
    assert content["steps"][1]["type"] == "ai"
    del content["steps"][1]["component"]

    res = client.patch(f"/sessions/{created['id']}/blueprint", json={"content": content})

    assert res.status_code == 200, res.text
    extract = _read_draft(created["output_dir"])["workflow"]["steps"][1]
    assert (extract["type"], extract.get("component")) == ("automated_task", None)
    body = res.json()
    assert body["blueprint"]["steps"][1]["type"] == "ai"
    assert body["metadata"][artifact_sync.AI_STEPS_KEY] == ["extract"]
    assert 'Removed the component of step "Extract"' in body["metadata"]["pending_user_edits"]


@requires_postgres
def test_an_emptied_label_in_the_form_clears_the_artifacts_label(
    client, db_session, not_busy
) -> None:
    created = _create(client, db_session)
    content = {**copy.deepcopy(created["blueprint"]), "data_objects": {"fields": ""}}

    res = client.patch(f"/sessions/{created['id']}/blueprint", json={"content": content})

    assert res.status_code == 200, res.text
    assert "label" not in _read_draft(created["output_dir"])["artifacts"]["fields"]
    assert res.json()["metadata"]["pending_user_edits"] == [
        'Cleared the name of data object "fields"'
    ]


@requires_postgres
def test_an_emptied_label_on_the_canvas_clears_the_artifacts_label(
    client, db_session, not_busy
) -> None:
    created = _create(client, db_session)
    sid = created["id"]
    xml = client.get(f"/sessions/{sid}/bpmn").text
    edited = xml.replace('name="Invoice fields"', 'name=""')
    assert edited != xml

    res = client.post(f"/sessions/{sid}/bpmn/sync", json={"xml": edited})

    assert res.status_code == 200, res.text
    assert "label" not in _read_draft(created["output_dir"])["artifacts"]["fields"]
    assert res.json()["metadata"]["pending_user_edits"] == [
        'Cleared the name of data object "fields"'
    ]
    # The diagram names the data object itself again.
    assert 'name="Invoice fields"' not in client.get(f"/sessions/{sid}/bpmn").text
