"""Lanes as operations: add, rename and remove a lane, and who does each step.

A lane is a ``business_process.participants`` entry; a step's lane is its
``performed_by``. Without participants the generator derives the lanes, and the
first lane operation makes those derived lanes real participants first, so the
diagram keeps the lanes it had.
"""

import copy
import json
import os
import re
import uuid
import xml.etree.ElementTree as ET

import pytest
from helpers import requires_postgres
from pydantic import TypeAdapter, ValidationError
from test_blueprint_ops import _draft
from wizard_api.schemas.blueprint_ops import Operation
from wizard_api.services import blueprint_ops
from wizard_api.services.blueprint_ops import OperationError, apply_operations

pytestmark = pytest.mark.skipif(
    not blueprint_ops.solution_wizard_available(),
    reason="solution_wizard package not installed",
)

if blueprint_ops.solution_wizard_available():
    from solution_wizard import validator
    from solution_wizard.blueprint import Blueprint
    from solution_wizard.bpmn_generator import generate_bpmn

_OPS = TypeAdapter(list[Operation])
_NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    "dc": "http://www.omg.org/spec/DD/20100524/DC",
}


def ops(*items):
    return _OPS.validate_python(list(items))


def _derived_draft() -> dict:
    """The operations fixture without participants: its lanes are derived."""
    draft = _draft()
    draft["business_process"]["participants"] = []
    return draft


def _draw(blueprint: dict, user_lanes=()) -> ET.Element:
    """The diagram, with ``user_lanes`` drawn as the editor draws the lanes the user added."""
    model = Blueprint.model_validate(blueprint)
    return ET.fromstring(generate_bpmn(model, extra_lane_ids=frozenset(user_lanes)))


def _box(root: ET.Element, element_id: str) -> tuple[float, float, float, float]:
    shape = root.find(f".//bpmndi:BPMNShape[@bpmnElement='{element_id}']", _NS)
    assert shape is not None, element_id
    b = shape.find("dc:Bounds", _NS)
    return tuple(float(b.get(k)) for k in ("x", "y", "width", "height"))


def _lanes(root: ET.Element) -> list[tuple[str, str]]:
    """(lane id, name) of each lane, top to bottom as drawn."""
    lanes = root.findall(".//bpmn:lane", _NS)
    return [
        (lane.get("id"), lane.get("name"))
        for lane in sorted(lanes, key=lambda lane: _box(root, lane.get("id"))[1])
    ]


def _members(root: ET.Element, lane_name: str) -> set[str]:
    lane = next(la for la in root.findall(".//bpmn:lane", _NS) if la.get("name") == lane_name)
    return {ref.text for ref in lane.findall("bpmn:flowNodeRef", _NS)}


def _inside(inner, outer) -> bool:
    x, y, w, h = inner
    ox, oy, ow, oh = outer
    return ox <= x and x + w <= ox + ow and oy <= y and y + h <= oy + oh


def _participants(blueprint: dict) -> list[dict]:
    return blueprint["business_process"]["participants"]


def _refused(draft: dict, *items) -> OperationError:
    with pytest.raises(OperationError) as caught:
        apply_operations(draft, ops(*items))
    return caught.value


# ---------------------------------------------------------------- the schema


def test_the_lane_operations_are_in_the_union():
    parsed = ops(
        {"op": "add_lane", "name": "Legal"},
        {"op": "add_lane", "name": "Bot", "kind": "system"},
        {"op": "rename_lane", "lane_id": "users", "name": "Clerks"},
        {"op": "remove_lane", "lane_id": "legal"},
        {"op": "set_step_lane", "step_id": "review", "lane_id": "legal"},
        {"op": "set_step_lane", "step_id": "review", "lane_id": None},
    )
    assert [type(p).__name__ for p in parsed] == [
        "AddLane",
        "AddLane",
        "RenameLane",
        "RemoveLane",
        "SetStepLane",
        "SetStepLane",
    ]
    assert parsed[0].kind == "human_role"
    with pytest.raises(ValidationError):
        ops({"op": "add_lane", "name": "x", "kind": "robot"})
    with pytest.raises(ValidationError):
        ops({"op": "add_lane", "name": "x" * 201})
    with pytest.raises(ValidationError):
        ops({"op": "rename_lane", "lane_id": "users", "name": "x" * 201})


# ---------------------------------------------------------------- the first lane edit


def test_the_first_lane_edit_keeps_the_derived_lanes():
    draft = _derived_draft()
    before = _lanes(_draw(draft))
    assert [name for _, name in before] == ["Clerk", "GenAI", "Controller"]

    # An edit that changes no lane: the lanes are the same, now as participants.
    result = apply_operations(
        draft, ops({"op": "rename_lane", "lane_id": "users", "name": "Clerk"})
    )

    assert [p["id"] for p in _participants(result.blueprint)] == ["users", "system", "reviewers"]
    after = _lanes(_draw(result.blueprint))
    assert [name for _, name in after] == [name for _, name in before]
    assert validator.validate(Blueprint.model_validate(result.blueprint)).ok
    # Each step is in the lane of the same name as before.
    root_before, root_after = _draw(draft), _draw(result.blueprint)
    for _, name in before:
        assert _members(root_after, name) == _members(root_before, name)


def test_a_lane_added_first_comes_after_the_derived_lanes_it_keeps():
    draft = _derived_draft()

    result = apply_operations(draft, ops({"op": "add_lane", "name": "Legal team"}))

    participants = _participants(result.blueprint)
    assert [p["id"] for p in participants] == ["users", "system", "reviewers", "legal_team"]
    assert participants[-1] == {
        "id": "legal_team",
        "name": "Legal team",
        "kind": "human_role",
        "default_lane_for": [],
    }
    names = [name for _, name in _lanes(_draw(result.blueprint, result.lanes_added))]
    # The new lane is drawn, empty and last, and the derived ones keep their order.
    assert names == ["Clerk", "GenAI", "Controller", "Legal team"]
    # Not one of the user's lanes, a participant no node reaches is not drawn.
    assert "Legal team" not in [name for _, name in _lanes(_draw(result.blueprint))]
    assert result.summaries == ['Added lane "Legal team"']
    assert result.bpmn_changed


def test_a_lane_without_steps_is_drawn():
    draft = _draft()
    result = apply_operations(draft, ops({"op": "add_lane", "name": "Robots", "kind": "system"}))

    root = _draw(result.blueprint, result.lanes_added)
    assert [name for _, name in _lanes(root)][-1] == "Robots"
    assert _members(root, "Robots") == set()


def test_new_lane_ids_are_slugs_unique_among_lanes_and_steps():
    draft = _draft()
    result = apply_operations(
        draft,
        ops(
            {"op": "add_lane", "name": "Clerk"},
            {"op": "add_lane", "name": "Review"},
            {"op": "add_lane", "name": "Users"},
            {"op": "add_lane", "name": "???"},
        ),
    )
    ids = [p["id"] for p in _participants(result.blueprint)]
    # "clerk" is a lane, "review" a step, "users" a derived lane id.
    assert ids[-4:] == ["clerk_2", "review_2", "users_2", "lane"]


# ---------------------------------------------------------------- set_step_lane


def test_set_step_lane_puts_the_step_in_that_lane():
    draft = _derived_draft()
    result = apply_operations(
        draft,
        ops(
            {"op": "add_lane", "name": "Legal"},
            {"op": "set_step_lane", "step_id": "review", "lane_id": "legal"},
        ),
    )

    review = next(s for s in result.blueprint["workflow"]["steps"] if s["id"] == "review")
    assert review["performed_by"] == "legal"
    root = _draw(result.blueprint, ["legal"])
    # The review's approval gateway goes with it.
    assert "Activity_review" in _members(root, "Legal")
    assert _inside(_box(root, "Activity_review"), _box(root, "Lane_legal"))
    # Nothing is left in the reviewers' lane, an agent's lane: it is not drawn.
    assert "Controller" not in [name for _, name in _lanes(root)]
    assert result.summaries[-1] == 'Moved step "Review" to lane "Legal"'

    # None: back to the lane of its type.
    back = apply_operations(
        result.blueprint, ops({"op": "set_step_lane", "step_id": "review", "lane_id": None})
    )
    review = next(s for s in back.blueprint["workflow"]["steps"] if s["id"] == "review")
    assert "performed_by" not in review
    assert "Activity_review" in _members(_draw(back.blueprint, ["legal"]), "Controller")
    assert back.summaries == ['Moved step "Review" back to the lane of its type']


def test_set_step_lane_takes_a_derived_lane_id_before_any_lane_edit():
    draft = _derived_draft()
    result = apply_operations(
        draft, ops({"op": "set_step_lane", "step_id": "upload", "lane_id": "reviewers"})
    )
    root = _draw(result.blueprint)
    assert "Activity_upload" in _members(root, "Controller")
    assert result.summaries == ['Moved step "Upload" to lane "Controller"']


def test_a_derived_lane_drawn_beside_participants_can_be_named():
    # The fixture has participants for users and the system; its review lane is derived.
    draft = _draft()
    assert "reviewers" not in [p["id"] for p in _participants(draft)]

    result = apply_operations(
        draft, ops({"op": "rename_lane", "lane_id": "reviewers", "name": "Controllers"})
    )

    assert _participants(result.blueprint)[-1]["id"] == "reviewers"
    root = _draw(result.blueprint)
    assert "Activity_review" in _members(root, "Controllers")
    assert "Controller" not in [name for _, name in _lanes(root)]


def test_set_step_lane_refuses_an_unknown_lane_or_step():
    draft = _draft()
    error = _refused(draft, {"op": "set_step_lane", "step_id": "review", "lane_id": "nobody"})
    assert (error.code, error.field) == ("not_found", "lane_id")
    error = _refused(draft, {"op": "set_step_lane", "step_id": "nothing", "lane_id": "clerk"})
    assert (error.code, error.field) == ("not_found", "step_id")


# ---------------------------------------------------------------- rename and remove


def test_rename_lane_renames_it():
    draft = _draft()
    result = apply_operations(
        draft, ops({"op": "rename_lane", "lane_id": "clerk", "name": "  Accounts clerk "})
    )
    assert _participants(result.blueprint)[0]["name"] == "Accounts clerk"
    assert result.summaries == ['Renamed lane "Clerk" to "Accounts clerk"']
    assert "Accounts clerk" in [name for _, name in _lanes(_draw(result.blueprint))]
    assert _refused(draft, {"op": "rename_lane", "lane_id": "clerk", "name": "  "}).code == (
        "invalid"
    )
    assert _refused(draft, {"op": "rename_lane", "lane_id": "x", "name": "X"}).code == "not_found"


def test_a_lane_in_use_cannot_be_removed():
    draft = _draft()
    draft["workflow"]["steps"][1]["performed_by"] = "clerk"

    # A step's performed_by names it.
    error = _refused(draft, {"op": "remove_lane", "lane_id": "clerk"})
    assert (error.code, error.field) == ("lane_in_use", "lane_id")

    # A manual step's performed_by names it.
    manual = copy.deepcopy(_draft())
    manual["business_process"]["participants"].append({"id": "legal", "name": "Legal"})
    manual["business_process"]["manual_steps"][0]["performed_by"] = "legal"
    assert _refused(manual, {"op": "remove_lane", "lane_id": "legal"}).code == "lane_in_use"

    # Steps of its type land in it.
    assert _refused(_draft(), {"op": "remove_lane", "lane_id": "system"}).code == "lane_in_use"

    # A lane nobody is in goes.
    result = apply_operations(
        _draft(),
        ops({"op": "add_lane", "name": "Legal"}, {"op": "remove_lane", "lane_id": "legal"}),
    )
    assert [p["id"] for p in _participants(result.blueprint)] == ["clerk", "system"]
    assert result.summaries[-1] == 'Removed lane "Legal"'
    assert _refused(_draft(), {"op": "remove_lane", "lane_id": "x"}).code == "not_found"


def test_a_lane_a_message_flow_names_cannot_be_removed():
    draft = _draft()
    draft["business_process"]["participants"].append({"id": "legal", "name": "Legal"})
    draft["business_process"]["message_flows"].append({"from": "legal", "to": "supplier"})

    assert _refused(draft, {"op": "remove_lane", "lane_id": "legal"}).code == "lane_in_use"


def test_a_lane_moved_away_from_can_then_be_removed():
    result = apply_operations(
        _derived_draft(),
        ops(
            {"op": "add_lane", "name": "Legal"},
            {"op": "set_step_lane", "step_id": "review", "lane_id": "legal"},
            {"op": "set_step_lane", "step_id": "review", "lane_id": None},
            {"op": "remove_lane", "lane_id": "legal"},
        ),
    )
    assert "legal" not in [p["id"] for p in _participants(result.blueprint)]


# ---------------------------------------------------------------- the API


@requires_postgres
def test_lane_operations_through_the_api_and_the_mapping_names_lanes(
    client, db_session, monkeypatch
) -> None:
    from test_patch_blueprint_writes_draft import _create, _read_draft
    from wizard_api.services import agent_service

    monkeypatch.setattr(agent_service, "is_busy", lambda session_id: False)
    created = _create(client, db_session, draft=_derived_draft())
    sid = created["id"]

    res = client.post(
        f"/sessions/{sid}/blueprint/operations",
        json={
            "base_version": created["active_version"],
            "operations": [
                {"op": "add_lane", "name": "Legal"},
                {"op": "set_step_lane", "step_id": "review", "lane_id": "legal"},
            ],
        },
    )
    assert res.status_code == 200, res.text
    assert _read_draft(created["output_dir"])["workflow"]["steps"][2]["performed_by"] == "legal"

    mapping = client.get(f"/sessions/{sid}/bpmn/mapping").json()["mapping"]
    assert mapping["Lane_legal"]["participant_id"] == "legal"
    assert mapping["Lane_users"]["participant_id"] == "users"
    assert mapping["Activity_review"]["performed_by"] == "legal"
    assert mapping["Activity_upload"]["performed_by"] == ""
    xml = client.get(f"/sessions/{sid}/bpmn").text
    assert re.search(r'<bpmn:lane id="Lane_legal" name="Legal">\s*<bpmn:flowNodeRef>', xml)

    refused = client.post(
        f"/sessions/{sid}/blueprint/operations",
        json={
            "base_version": res.json()["session"]["active_version"],
            "operations": [{"op": "remove_lane", "lane_id": "legal"}],
        },
    )
    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "lane_in_use"


@requires_postgres
def test_the_mapping_names_derived_lanes_by_their_participant_id(client, db_session) -> None:
    from test_patch_blueprint_writes_draft import _create

    created = _create(client, db_session, draft=_derived_draft())
    mapping = client.get(f"/sessions/{created['id']}/bpmn/mapping").json()["mapping"]

    lanes = {k: v["participant_id"] for k, v in mapping.items() if v["kind"] == "lane"}
    assert lanes == {"Lane_users": "users", "Lane_gaik_ai": "system", "Lane_reviewers": "reviewers"}


# ---------------------------------------------------------------- the user's lanes (R25)


def test_the_operations_say_which_lanes_they_added_and_removed():
    result = apply_operations(
        _draft(),
        ops(
            {"op": "add_lane", "name": "Legal"},
            {"op": "add_lane", "name": "Audit"},
            {"op": "remove_lane", "lane_id": "legal"},
        ),
    )
    assert result.lanes_added == ["legal", "audit"]
    assert result.lanes_removed == ["legal"]


def _lane_tops(xml: str) -> dict[str, float]:
    root = ET.fromstring(xml)
    return {
        lane.get("name"): _box(root, lane.get("id"))[1]
        for lane in root.findall(".//bpmn:lane", _NS)
    }


def _shape_boxes(xml: str) -> dict[str, tuple]:
    root = ET.fromstring(xml)
    out = {}
    for shape in root.findall(".//bpmndi:BPMNShape", _NS):
        b = shape.find("dc:Bounds", _NS)
        out[shape.get("bpmnElement")] = tuple(
            float(b.get(k)) for k in ("x", "y", "width", "height")
        )
    return out


@requires_postgres
def test_a_lane_the_user_adds_is_drawn_last_and_moves_no_other_lane(
    client, db_session, monkeypatch
) -> None:
    from test_patch_blueprint_writes_draft import _create
    from wizard_api.services import agent_service, artifact_sync, session_service

    monkeypatch.setattr(agent_service, "is_busy", lambda session_id: False)
    created = _create(client, db_session, draft=_derived_draft())
    sid = created["id"]
    before = client.get(f"/sessions/{sid}/bpmn").text

    def run(*operations):
        version = client.get(f"/sessions/{sid}").json()["active_version"]
        res = client.post(
            f"/sessions/{sid}/blueprint/operations",
            json={"base_version": version, "operations": list(operations)},
        )
        assert res.status_code == 200, res.text

    def metadata():
        db_session.expire_all()
        return session_service.get_session(db_session, uuid.UUID(sid)).session_metadata

    # "New lane" sorts before "Users" by id: it is drawn last all the same.
    run({"op": "add_lane", "name": "New lane"})
    assert metadata()[artifact_sync.USER_LANES_KEY] == ["new_lane"]
    after = client.get(f"/sessions/{sid}/bpmn").text
    tops = _lane_tops(after)
    assert max(tops, key=tops.get) == "New lane"
    assert {k: v for k, v in tops.items() if k != "New lane"} == _lane_tops(before)
    old, new = _shape_boxes(before), _shape_boxes(after)
    for element, box in old.items():
        # Lanes are compared by name above (materialised, the system lane's id changes).
        if not element.startswith(("Participant_", "DataStore_", "Lane_")):
            assert new[element] == box, element
    # workflow.bpmn, which the agent reads, draws it too.
    with open(os.path.join(created["output_dir"], "workflow.bpmn"), encoding="utf-8") as fh:
        assert 'name="New lane"' in fh.read()

    # Removed, it is no user lane any more. An undo brings the participant back,
    # as a lane of the blueprint like any other (R26): drawn only when a step is in it.
    run({"op": "remove_lane", "lane_id": "new_lane"})
    assert artifact_sync.USER_LANES_KEY not in metadata()
    assert 'name="New lane"' not in client.get(f"/sessions/{sid}/bpmn").text
    _undo(client, sid)
    assert artifact_sync.USER_LANES_KEY not in metadata()
    assert 'name="New lane"' not in client.get(f"/sessions/{sid}/bpmn").text


@requires_postgres
def test_a_participant_the_agent_declared_and_no_step_uses_is_not_drawn(client, db_session) -> None:
    from test_patch_blueprint_writes_draft import _create

    draft = _draft()
    draft["business_process"]["participants"].append({"id": "erp", "name": "ERP", "kind": "system"})
    created = _create(client, db_session, draft=draft)

    assert 'name="ERP"' not in client.get(f"/sessions/{created['id']}/bpmn").text


@requires_postgres
def test_the_user_lanes_are_server_owned(client) -> None:
    from wizard_api.services import artifact_sync

    sid = client.post("/sessions", json={"user_id": "forge", "title": "Forge"}).json()["id"]
    res = client.patch(
        f"/sessions/{sid}", json={"metadata": {artifact_sync.USER_LANES_KEY: ["clerk"]}}
    )
    assert res.status_code == 422
    assert res.json()["detail"]["error"] == "server_owned_metadata"


# ---------------------------------------------------------------- R26: lanes only from add_lane


def _undo(client, sid: str) -> None:
    version = client.get(f"/sessions/{sid}").json()["active_version"]
    res = client.post(f"/sessions/{sid}/blueprint/undo", json={"base_version": version})
    assert res.status_code == 200, res.text


def _agent_turn(db_session, created: dict, draft: dict) -> None:
    """The agent writes ``draft`` and the chat turn's sync reads it."""
    from test_patch_blueprint_writes_draft import _draft_path
    from wizard_api.services import artifact_sync, session_service

    with open(_draft_path(created["output_dir"]), "w", encoding="utf-8") as fh:
        json.dump(draft, fh)
    db_session.expire_all()
    session = session_service.get_session(db_session, uuid.UUID(created["id"]))
    artifact_sync.sync_blueprint_from_draft(db_session, session)


def _user_lanes(db_session, sid: str):
    from wizard_api.services import artifact_sync, session_service

    db_session.expire_all()
    metadata = session_service.get_session(db_session, uuid.UUID(sid)).session_metadata
    return metadata.get(artifact_sync.USER_LANES_KEY)


def _with_erp(draft: dict) -> dict:
    draft["business_process"]["participants"].append({"id": "erp", "name": "ERP", "kind": "system"})
    return draft


@requires_postgres
def test_a_participant_an_undo_brings_back_after_the_agent_dropped_it_is_no_user_lane(
    client, db_session, monkeypatch
) -> None:
    from test_patch_blueprint_writes_draft import _create
    from wizard_api.services import agent_service

    monkeypatch.setattr(agent_service, "is_busy", lambda session_id: False)
    created = _create(client, db_session, draft=_with_erp(_draft()))
    sid = created["id"]
    # The agent drops ERP in a turn (a new version); the user clicks Undo, which goes back over it.
    dropped = _draft()
    dropped["use_case"]["description"] = "d2"
    _agent_turn(db_session, created, dropped)
    _undo(client, sid)

    assert "erp" in [p["id"] for p in _read(created)["business_process"]["participants"]]
    assert _user_lanes(db_session, sid) is None
    assert 'name="ERP"' not in client.get(f"/sessions/{sid}/bpmn").text


@requires_postgres
def test_a_user_lane_the_agent_drops_and_declares_again_is_no_user_lane(
    client, db_session, monkeypatch
) -> None:
    from test_patch_blueprint_writes_draft import _create
    from wizard_api.services import agent_service

    monkeypatch.setattr(agent_service, "is_busy", lambda session_id: False)
    created = _create(client, db_session, draft=_draft())
    sid = created["id"]
    version = client.get(f"/sessions/{sid}").json()["active_version"]
    res = client.post(
        f"/sessions/{sid}/blueprint/operations",
        json={"base_version": version, "operations": [{"op": "add_lane", "name": "Legal"}]},
    )
    assert res.status_code == 200, res.text
    assert _user_lanes(db_session, sid) == ["legal"]

    # The agent's next draft has no Legal: it is no user lane any more.
    _agent_turn(db_session, created, _draft())
    assert _user_lanes(db_session, sid) is None
    # A later draft declares "legal" again: the agent's participant, not drawn while empty.
    again = _draft()
    again["business_process"]["participants"].append({"id": "legal", "name": "Legal"})
    again["use_case"]["description"] = "d2"
    _agent_turn(db_session, created, again)
    assert _user_lanes(db_session, sid) is None
    assert 'name="Legal"' not in client.get(f"/sessions/{sid}/bpmn").text


@requires_postgres
def test_an_undone_add_lane_is_gone_from_the_user_lanes(client, db_session, monkeypatch) -> None:
    from test_patch_blueprint_writes_draft import _create
    from wizard_api.services import agent_service

    monkeypatch.setattr(agent_service, "is_busy", lambda session_id: False)
    created = _create(client, db_session, draft=_draft())
    sid = created["id"]
    version = client.get(f"/sessions/{sid}").json()["active_version"]
    res = client.post(
        f"/sessions/{sid}/blueprint/operations",
        json={"base_version": version, "operations": [{"op": "add_lane", "name": "Legal"}]},
    )
    assert res.status_code == 200, res.text
    assert _user_lanes(db_session, sid) == ["legal"]

    _undo(client, sid)

    assert _user_lanes(db_session, sid) is None
    assert 'name="Legal"' not in client.get(f"/sessions/{sid}/bpmn").text


def _read(created: dict) -> dict:
    from test_patch_blueprint_writes_draft import _read_draft

    return _read_draft(created["output_dir"])


def test_a_finnish_lane_name_gives_a_readable_id():
    result = apply_operations(
        _draft(), ops({"op": "add_lane", "name": "Käyttäjä"}, {"op": "add_lane", "name": "Öö"})
    )

    assert [p["id"] for p in _participants(result.blueprint)][-2:] == ["kayttaja", "oo"]
