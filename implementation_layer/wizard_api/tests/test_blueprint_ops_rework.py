"""Rework and rejection paths as operations: add, change and remove one.

A path is a ``business_process.exceptions`` entry: the step it is
``attached_to``, its condition and its ``outcome``, ``"end"`` (a rejection
path) or ``"loop_to:<step id>"`` (a rework path back to that step, an earlier
one or the same). The generator draws a rework path as a loop flow; on a
human review step the approval gateway's "No" takes the first one, elsewhere
the path gets a gateway of its own (``Gateway_exc_<id>``).
"""

import xml.etree.ElementTree as ET

import pytest
from helpers import requires_postgres
from pydantic import TypeAdapter, ValidationError
from test_blueprint_ops import _draft
from test_blueprint_ops_decisions import _agent_loop_draft
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
    "omgdi": "http://www.omg.org/spec/DD/20100524/DI",
}


def ops(*items):
    return _OPS.validate_python(list(items))


def _plain_draft() -> dict:
    """The operations fixture without its exceptions and decision points."""
    draft = _draft()
    draft["business_process"]["exceptions"] = []
    draft["business_process"]["decision_points"] = []
    return draft


def _add(
    attached_to="review", outcome="loop_to:extract", name="Fields wrong", condition="Wrong"
) -> dict:
    return {
        "op": "add_rework_path",
        "attached_to": attached_to,
        "name": name,
        "condition": condition,
        "outcome": outcome,
    }


def _paths(blueprint: dict) -> list[dict]:
    return blueprint["business_process"]["exceptions"]


def _drawn(blueprint: dict) -> ET.Element:
    return ET.fromstring(generate_bpmn(Blueprint.model_validate(blueprint)))


def _flows(blueprint: dict) -> list[tuple[str, str, str]]:
    """(source, target, name) of every sequence flow drawn."""
    return [
        (f.get("sourceRef"), f.get("targetRef"), f.get("name") or "")
        for f in _drawn(blueprint).iter(f"{{{_NS['bpmn']}}}sequenceFlow")
    ]


def _loop_flow_drawn_below(blueprint: dict, source: str, target: str) -> bool:
    """Whether the flow source → target is drawn as a loop: down, across and up."""
    root = _drawn(blueprint)
    flow = next(
        f
        for f in root.iter(f"{{{_NS['bpmn']}}}sequenceFlow")
        if (f.get("sourceRef"), f.get("targetRef")) == (source, target)
    )
    edge = next(
        e
        for e in root.iter(f"{{{_NS['bpmndi']}}}BPMNEdge")
        if e.get("bpmnElement") == flow.get("id")
    )
    ys = [int(p.get("y")) for p in edge.iter(f"{{{_NS['omgdi']}}}waypoint")]
    return len(ys) == 4 and ys[1] == ys[2] and ys[1] > max(ys[0], ys[3])


# ---------------------------------------------------------------- add


def test_a_rework_path_loops_back_in_the_diagram() -> None:
    result = apply_operations(_plain_draft(), ops(_add()))
    assert _paths(result.blueprint) == [
        {
            "id": "fields_wrong",
            "name": "Fields wrong",
            "attached_to": "review",
            "condition": "Wrong",
            "outcome": "loop_to:extract",
        }
    ]
    assert result.summaries == ['Added rework path "Fields wrong" to step "Review"']
    assert result.bpmn_changed
    # On a review step the approval's "No" loops back, drawn below the lanes.
    assert ("Gateway_approve_review", "Activity_extract", "Wrong") in _flows(result.blueprint)
    assert _loop_flow_drawn_below(result.blueprint, "Gateway_approve_review", "Activity_extract")
    # On another step the path has a gateway of its own; back to the same step too.
    other = apply_operations(
        _plain_draft(),
        ops(_add(attached_to="extract", outcome="loop_to:upload", name="Unreadable")),
    ).blueprint
    assert ("Gateway_exc_unreadable", "Activity_upload", "Wrong") in _flows(other)
    assert _loop_flow_drawn_below(other, "Gateway_exc_unreadable", "Activity_upload")
    same = apply_operations(
        _plain_draft(), ops(_add(attached_to="deliver", outcome="loop_to:deliver", name="Retry"))
    ).blueprint
    assert ("Gateway_exc_retry", "Activity_deliver", "Wrong") in _flows(same)


def test_a_rejection_path_ends_the_process() -> None:
    result = apply_operations(_plain_draft(), ops(_add(outcome="end", name="Rejected")))
    assert _paths(result.blueprint)[0]["outcome"] == "end"
    assert result.summaries == ['Added rejection path "Rejected" to step "Review"']
    assert ("Gateway_approve_review", "EndEvent_rejected", "Wrong") in _flows(result.blueprint)
    other = apply_operations(
        _plain_draft(), ops(_add(attached_to="extract", outcome="end", name="Unreadable"))
    ).blueprint
    flows = _flows(other)
    assert ("Gateway_exc_unreadable", "EndEvent_unreadable", "Wrong") in flows
    ends = {e.get("id"): e.get("name") for e in _drawn(other).iter(f"{{{_NS['bpmn']}}}endEvent")}
    assert ends["EndEvent_unreadable"] == "Unreadable"


def test_a_loop_to_an_unknown_step_is_refused() -> None:
    with pytest.raises(OperationError) as refused:
        apply_operations(_plain_draft(), ops(_add(outcome="loop_to:gone")))
    assert (refused.value.code, refused.value.field) == ("unknown_step", "outcome")
    with pytest.raises(OperationError) as refused:
        apply_operations(_plain_draft(), ops(_add(outcome="loop_to:")))
    assert (refused.value.code, refused.value.field) == ("unknown_step", "outcome")
    with pytest.raises(OperationError) as refused:
        apply_operations(_plain_draft(), ops(_add(attached_to="gone")))
    assert (refused.value.code, refused.value.field) == ("unknown_step", "attached_to")


def test_a_loop_to_a_later_step_or_another_outcome_is_refused() -> None:
    with pytest.raises(OperationError) as refused:
        apply_operations(_plain_draft(), ops(_add(attached_to="extract", outcome="loop_to:review")))
    assert (refused.value.code, refused.value.field) == ("invalid", "outcome")
    for outcome in ("maybe", "", "END", "loop_to extract"):
        with pytest.raises(OperationError) as refused:
            apply_operations(_plain_draft(), ops(_add(outcome=outcome)))
        assert (refused.value.code, refused.value.field) == ("invalid", "outcome")


def test_a_rework_path_to_a_manual_step_follows_the_drawn_order() -> None:
    # Manual steps come after the workflow's steps in the drawn order.
    draft = _plain_draft()
    made = apply_operations(draft, ops(_add(attached_to="archive", outcome="loop_to:review")))
    assert _paths(made.blueprint)[0]["attached_to"] == "archive"
    with pytest.raises(OperationError) as refused:
        apply_operations(draft, ops(_add(attached_to="deliver", outcome="loop_to:archive")))
    assert (refused.value.code, refused.value.field) == ("invalid", "outcome")


def test_a_blank_name_is_refused_and_the_condition_may_be_empty() -> None:
    with pytest.raises(OperationError) as refused:
        apply_operations(_plain_draft(), ops(_add(name="  ")))
    assert (refused.value.code, refused.value.field) == ("invalid", "name")
    op = _add(name=" Redo ")
    del op["condition"]
    path = _paths(apply_operations(_plain_draft(), ops(op)).blueprint)[0]
    assert (path["name"], path["condition"]) == ("Redo", "")


def test_the_schemas_bound_the_text_and_forbid_other_fields() -> None:
    for bad in (
        _add(name="x" * 201),
        _add(condition="x" * 201),
        {**_add(), "extra": 1},
        {"op": "update_rework_path", "exception_id": "a", "name": "x" * 201},
        {"op": "remove_rework_path", "exception_id": "a", "outcome": "end"},
    ):
        with pytest.raises(ValidationError):
            ops(bad)


def test_path_ids_use_the_slug_rule_and_miss_the_drawn_end_events() -> None:
    draft = _plain_draft()
    draft["business_process"]["exceptions"] = [
        {"id": "fields_wrong", "name": "Old", "attached_to": "deliver", "outcome": "end"}
    ]
    result = apply_operations(
        draft,
        ops(
            _add(),
            _add(name="Success", outcome="end", attached_to="extract"),
            # EndEvent_rejected_<review step> is the approval's own rejection.
            _add(name="Rejected review", outcome="end", attached_to="upload"),
            _add(name="?!", attached_to="deliver", outcome="end"),
        ),
    )
    assert [p["id"] for p in _paths(result.blueprint)] == [
        "fields_wrong",
        "fields_wrong_2",
        "success_2",
        "rejected_review_2",
        "path",
    ]


def test_a_rework_path_inside_a_decision_loop_is_made() -> None:
    # Rework paths are drawn as loop flows: the loop check of decisions leaves them.
    draft = _agent_loop_draft()
    made = apply_operations(draft, ops(_add(outcome="loop_to:upload")))
    assert _paths(made.blueprint)[-1]["outcome"] == "loop_to:upload"
    made = apply_operations(
        _plain_draft(), ops(_add(attached_to="deliver", outcome="loop_to:upload"))
    )
    assert _paths(made.blueprint)[0]["attached_to"] == "deliver"
    assert validator.validate(Blueprint.model_validate(made.blueprint)).ok


# ---------------------------------------------------------------- update and remove


def _with_path() -> dict:
    return apply_operations(_plain_draft(), ops(_add())).blueprint


def test_a_path_is_changed_and_keeps_what_the_edit_does_not_name() -> None:
    draft = _with_path()
    renamed = apply_operations(
        draft, ops({"op": "update_rework_path", "exception_id": "fields_wrong", "name": "Redo"})
    )
    assert _paths(renamed.blueprint)[0] == {**_paths(draft)[0], "name": "Redo"}
    assert renamed.summaries == ['Changed rework path "Redo" (was "Fields wrong")']
    ended = apply_operations(
        draft,
        ops(
            {
                "op": "update_rework_path",
                "exception_id": "fields_wrong",
                "condition": " Unfixable ",
                "outcome": "end",
            }
        ),
    )
    assert _paths(ended.blueprint)[0] == {
        **_paths(draft)[0],
        "condition": "Unfixable",
        "outcome": "end",
    }
    assert ended.summaries == ['Changed rejection path "Fields wrong"']
    back = apply_operations(
        draft,
        ops(
            {
                "op": "update_rework_path",
                "exception_id": "fields_wrong",
                "outcome": "loop_to:upload",
            }
        ),
    )
    assert _paths(back.blueprint)[0]["outcome"] == "loop_to:upload"


def test_an_update_is_checked_as_an_add_is() -> None:
    draft = _with_path()
    for change, expected in (
        ({"exception_id": "gone", "name": "x"}, ("not_found", "exception_id")),
        ({"exception_id": "fields_wrong", "name": " "}, ("invalid", "name")),
        ({"exception_id": "fields_wrong", "outcome": "loop_to:gone"}, ("unknown_step", "outcome")),
        ({"exception_id": "fields_wrong", "outcome": "loop_to:deliver"}, ("invalid", "outcome")),
        ({"exception_id": "fields_wrong", "outcome": "sometimes"}, ("invalid", "outcome")),
    ):
        with pytest.raises(OperationError) as refused:
            apply_operations(draft, ops({"op": "update_rework_path", **change}))
        assert (refused.value.code, refused.value.field) == expected, change


def test_an_agents_path_forward_can_still_be_renamed() -> None:
    # The agent may have written a loop_to a later step; a rename leaves it.
    draft = _plain_draft()
    draft["business_process"]["exceptions"] = [
        {"id": "odd", "name": "Odd", "attached_to": "extract", "outcome": "loop_to:deliver"}
    ]
    made = apply_operations(
        draft, ops({"op": "update_rework_path", "exception_id": "odd", "name": "Odd one"})
    )
    assert _paths(made.blueprint)[0]["outcome"] == "loop_to:deliver"


def test_a_path_is_removed() -> None:
    draft = _with_path()
    removed = apply_operations(
        draft, ops({"op": "remove_rework_path", "exception_id": "fields_wrong"})
    )
    assert _paths(removed.blueprint) == []
    assert removed.summaries == ['Removed rework path "Fields wrong"']
    # The approval's "No" goes back to its plain rejection.
    assert ("Gateway_approve_review", "EndEvent_rejected_review", "No") in _flows(removed.blueprint)
    with pytest.raises(OperationError) as refused:
        apply_operations(draft, ops({"op": "remove_rework_path", "exception_id": "gone"}))
    assert (refused.value.code, refused.value.field) == ("not_found", "exception_id")


# ---------------------------------------------------------------- the mapping


def test_the_mapping_names_each_path_on_its_elements() -> None:
    from wizard_api.services.bpmn_service import named_mapping

    drawn = _plain_draft()
    drawn["business_process"]["exceptions"] = [
        {"id": "unreadable", "name": "Unreadable", "attached_to": "extract", "outcome": "end"},
        {
            "id": "redo",
            "name": "Redo",
            "attached_to": "review",
            "condition": "Wrong",
            "outcome": "loop_to:extract",
        },
        {"id": "no_way", "name": "No way", "attached_to": "deliver", "outcome": "end"},
    ]
    blueprint = Blueprint.model_validate(drawn)
    generate_bpmn(blueprint)
    mapping = named_mapping(dict(blueprint.visualizations["bpmn_mapping"]), drawn)

    def path(element_id: str) -> dict:
        return mapping[element_id]["exception"]

    unreadable = {
        "id": "unreadable",
        "name": "Unreadable",
        "attached_to": "extract",
        "condition": "",
        "outcome": "end",
    }
    assert path("Gateway_exc_unreadable") == unreadable
    assert path("EndEvent_unreadable") == unreadable
    assert path("Gateway_exc_no_way")["id"] == "no_way"
    # The approval gateway's "No" is the review step's rework path.
    assert mapping["Gateway_approve_review"]["kind"] == "approval_gateway"
    assert path("Gateway_approve_review") == {
        "id": "redo",
        "name": "Redo",
        "attached_to": "review",
        "condition": "Wrong",
        "outcome": "loop_to:extract",
    }
    assert "exception" not in mapping["Activity_review"]

    # A rejection path on a review step: its end event, mapped by the path's id.
    drawn["business_process"]["exceptions"] = [
        {"id": "dropped", "name": "Dropped", "attached_to": "review", "outcome": "end"}
    ]
    blueprint = Blueprint.model_validate(drawn)
    generate_bpmn(blueprint)
    mapping = named_mapping(dict(blueprint.visualizations["bpmn_mapping"]), drawn)
    assert mapping["EndEvent_dropped"]["exception"]["id"] == "dropped"
    assert "exception" not in mapping["Gateway_approve_review"]


@requires_postgres
def test_paths_through_the_api_and_the_mapping_names_them(client, db_session, monkeypatch) -> None:
    from test_patch_blueprint_writes_draft import _create, _read_draft
    from wizard_api.services import agent_service

    monkeypatch.setattr(agent_service, "is_busy", lambda session_id: False)
    created = _create(client, db_session, draft=_plain_draft())
    sid = created["id"]

    res = client.post(
        f"/sessions/{sid}/blueprint/operations",
        json={"base_version": created["active_version"], "operations": [_add()]},
    )
    assert res.status_code == 200, res.text
    assert _paths(_read_draft(created["output_dir"]))[0]["id"] == "fields_wrong"
    mapping = client.get(f"/sessions/{sid}/bpmn/mapping").json()["mapping"]
    assert mapping["Gateway_approve_review"]["exception"]["outcome"] == "loop_to:extract"

    refused = client.post(
        f"/sessions/{sid}/blueprint/operations",
        json={
            "base_version": res.json()["session"]["active_version"],
            "operations": [
                {
                    "op": "update_rework_path",
                    "exception_id": "fields_wrong",
                    "outcome": "loop_to:gone",
                }
            ],
        },
    )
    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "unknown_step"
    assert refused.json()["detail"]["field"] == "outcome"

    removed = client.post(
        f"/sessions/{sid}/blueprint/operations",
        json={
            "base_version": res.json()["session"]["active_version"],
            "operations": [{"op": "remove_rework_path", "exception_id": "fields_wrong"}],
        },
    )
    assert removed.status_code == 200, removed.text
    mapping = client.get(f"/sessions/{sid}/bpmn/mapping").json()["mapping"]
    assert not any("exception" in entry for entry in mapping.values())


def test_a_finnish_path_name_gives_a_readable_id() -> None:
    result = apply_operations(
        _plain_draft(), ops(_add(name="Kenttä väärin", attached_to="deliver", outcome="end"))
    )

    assert [p["id"] for p in _paths(result.blueprint)][-1] == "kentta_vaarin"
