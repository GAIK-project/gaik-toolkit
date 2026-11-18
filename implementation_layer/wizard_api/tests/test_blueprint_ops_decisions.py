"""Business decisions as operations: add, change and remove a decision point.

A decision is a ``business_process.decision_points`` entry: the step it comes
``after`` and its branches, each a condition and the step it leads to (or
``"end"``). The generator draws it as ``Gateway_decision_<id>`` after its step,
with one flow per branch named by the condition.
"""

import re
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
_NS = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL"}


def ops(*items):
    return _OPS.validate_python(list(items))


def _plain_draft() -> dict:
    """The operations fixture without its decision points."""
    draft = _draft()
    draft["business_process"]["decision_points"] = []
    return draft


def _add(name="Confident enough?", after="extract", branches=None) -> dict:
    return {
        "op": "add_decision",
        "after": after,
        "name": name,
        "branches": branches
        if branches is not None
        else [
            {"condition": "Sure", "target": "review"},
            {"condition": "Unsure", "target": "end"},
        ],
    }


def _to(*targets: str) -> list[dict]:
    return [{"condition": f"to {t}", "target": t} for t in targets]


def _decisions(blueprint: dict) -> list[dict]:
    return blueprint["business_process"]["decision_points"]


def _flows(blueprint: dict) -> list[tuple[str, str, str]]:
    """(source, target, name) of every sequence flow drawn."""
    root = ET.fromstring(generate_bpmn(Blueprint.model_validate(blueprint)))
    return [
        (f.get("sourceRef"), f.get("targetRef"), f.get("name") or "")
        for f in root.iter(f"{{{_NS['bpmn']}}}sequenceFlow")
    ]


# ---------------------------------------------------------------- add


def test_a_decision_is_drawn_after_its_step_with_its_branches() -> None:
    result = apply_operations(_plain_draft(), ops(_add(after="upload")))

    assert _decisions(result.blueprint) == [
        {
            "id": "confident_enough",
            "name": "Confident enough?",
            "after": "upload",
            "branches": [
                {"condition": "Sure", "target": "review"},
                {"condition": "Unsure", "target": "end"},
            ],
        }
    ]
    assert result.summaries == ['Added decision "Confident enough?" after step "Upload"']
    assert result.bpmn_changed
    flows = _flows(result.blueprint)
    gateway = "Gateway_decision_confident_enough"
    assert ("Activity_upload", gateway, "") in flows
    assert (gateway, "Activity_review", "Sure") in flows
    assert (gateway, "EndEvent_success", "Unsure") in flows
    model = Blueprint.model_validate(result.blueprint)
    generate_bpmn(model)
    assert model.visualizations["bpmn_mapping"][gateway] == {
        "kind": "decision_point",
        "blueprint_path": "business_process.decision_points[0]",
    }
    assert validator.validate(model).ok


def test_a_decision_to_an_unknown_step_is_refused() -> None:
    draft = _plain_draft()
    for op, field in (
        (_add(after="nope"), "after"),
        (
            _add(
                branches=[{"condition": "a", "target": "review"}, {"condition": "b", "target": "x"}]
            ),
            "target",
        ),
    ):
        with pytest.raises(OperationError) as refused:
            apply_operations(draft, ops(op))
        assert refused.value.code == "unknown_step"
        assert refused.value.field == field
    assert draft == _plain_draft()


def test_one_branch_is_not_a_decision() -> None:
    branch = {"condition": "yes", "target": "review"}
    for branches in ([branch], [branch] * 6, []):
        with pytest.raises(ValidationError):
            ops(_add(branches=branches))
    for condition in ("", "x" * 201):
        with pytest.raises(ValidationError):
            ops(_add(branches=[branch, {"condition": condition, "target": "end"}]))
    with pytest.raises(ValidationError):
        ops(_add(name="x" * 201))
    # Five branches are a decision; two are the least.
    targets = ["upload", "extract", "review", "deliver", "end"]
    five = [{"condition": f"c{i}", "target": t} for i, t in enumerate(targets)]
    assert len(ops(_add(after="deliver", branches=five))[0].branches) == 5


def test_blank_names_and_conditions_are_refused() -> None:
    with pytest.raises(OperationError) as refused:
        apply_operations(_plain_draft(), ops(_add(name="   ")))
    assert (refused.value.code, refused.value.field) == ("invalid", "name")
    blank = [{"condition": " ", "target": "review"}, {"condition": "b", "target": "end"}]
    with pytest.raises(OperationError) as refused:
        apply_operations(_plain_draft(), ops(_add(branches=blank)))
    assert (refused.value.code, refused.value.field) == ("invalid", "condition")


def test_end_and_a_manual_step_are_targets() -> None:
    branches = [{"condition": "file", "target": "archive"}, {"condition": "done", "target": "end"}]
    result = apply_operations(_plain_draft(), ops(_add(after="deliver", branches=branches)))
    flows = _flows(result.blueprint)
    gateway = "Gateway_decision_confident_enough"
    assert (gateway, "Activity_archive", "file") in flows
    assert (gateway, "EndEvent_success", "done") in flows


def test_decision_ids_use_the_slug_rule() -> None:
    draft = _plain_draft()
    # A step drawn as Gateway_decision_ok would share the gateway's element id.
    draft["workflow"]["steps"][3]["id"] = "decision_ok"
    draft["workflow"]["steps"][3]["type"] = "decision"
    draft["workflow"]["steps"][3].pop("component")
    draft["artifacts"]["report"]["produced_by"] = "decision_ok"
    draft["business_process"]["message_flows"] = []
    result = apply_operations(
        draft,
        ops(
            _add(name="Same name"),
            _add(name="Same name", after="upload"),
            _add(name="Ok", after="review", branches=_to("decision_ok", "end")),
            _add(name="?!", after="decision_ok", branches=_to("archive", "end")),
        ),
    )
    assert [d["id"] for d in _decisions(result.blueprint)] == [
        "same_name",
        "same_name_2",
        "ok_2",
        "decision",
    ]


def test_all_branches_to_one_step_decide_nothing_and_are_refused() -> None:
    same = [{"condition": "a", "target": "review"}, {"condition": "b", "target": "review"}]
    with pytest.raises(OperationError) as refused:
        apply_operations(_plain_draft(), ops(_add(branches=same)))
    assert (refused.value.code, refused.value.field) == ("invalid", "branches")
    # Two of three to one step still decide something.
    three = same + [{"condition": "c", "target": "end"}]
    assert apply_operations(_plain_draft(), ops(_add(branches=three))).blueprint


def test_a_branch_back_to_an_earlier_step_is_refused_as_a_cycle() -> None:
    # The validator checks cycles in depends_on only (rule 8); a branch back
    # is a loop in the drawn flow that the layout cannot rank.
    for target in ("upload", "extract"):
        back = [{"condition": "again", "target": target}, {"condition": "ok", "target": "review"}]
        with pytest.raises(OperationError) as refused:
            apply_operations(_plain_draft(), ops(_add(branches=back)))
        assert refused.value.code == "cycle"
        assert 'the decision after "Extract" would lead back' in refused.value.message


def test_a_loop_through_another_decision_is_refused() -> None:
    # Deliver follows review only through a decision's branch: a branch from
    # deliver back to review closes a loop through that decision.
    draft = _plain_draft()
    draft["workflow"]["steps"][3]["depends_on"] = []
    forward = [{"condition": "a", "target": "deliver"}, {"condition": "b", "target": "end"}]
    first = apply_operations(draft, ops(_add(name="Ship", after="review", branches=forward)))
    back = [{"condition": "x", "target": "review"}, {"condition": "y", "target": "end"}]
    with pytest.raises(OperationError) as refused:
        apply_operations(first.blueprint, ops(_add(name="Loop", after="deliver", branches=back)))
    assert refused.value.code == "cycle"
    assert 'loop through steps "Review", "Deliver"' in refused.value.message


def _agent_loop_draft() -> dict:
    """An agent's decision after review with a branch back to upload: the
    validator accepts it, and the diagram draws the loop."""
    draft = _plain_draft()
    draft["business_process"]["decision_points"] = [
        {
            "id": "redo",
            "name": "Redo?",
            "after": "review",
            "branches": [
                {"condition": "ok", "target": "deliver"},
                {"condition": "again", "target": "upload"},
            ],
        }
    ]
    assert validator.validate(Blueprint.model_validate(draft)).ok
    return draft


def test_an_agents_decision_with_a_branch_back_can_be_renamed_and_its_branches_changed() -> None:
    draft = _agent_loop_draft()
    renamed = apply_operations(
        draft, ops({"op": "update_decision", "decision_id": "redo", "name": "Again?"})
    ).blueprint
    assert _decisions(renamed)[0]["name"] == "Again?"
    assert _decisions(renamed)[0]["branches"] == _decisions(draft)[0]["branches"]
    # The back branch kept, a condition changed: no new loop.
    kept = [
        {"condition": "fine", "target": "deliver"},
        {"condition": "again", "target": "upload"},
    ]
    op = {"op": "update_decision", "decision_id": "redo", "branches": kept}
    assert _decisions(apply_operations(draft, ops(op)).blueprint)[0]["branches"] == kept
    # A new branch back from outside the agent's loop makes a new one: refused, named by its steps.
    back = [{"condition": "a", "target": "upload"}, {"condition": "b", "target": "end"}]
    with pytest.raises(OperationError) as refused:
        apply_operations(draft, ops(_add(name="Back", after="deliver", branches=back)))
    assert refused.value.code == "cycle"
    assert '"Upload", "Extract", "Review", "Deliver"' in refused.value.message
    assert 'the decision after "Deliver" would lead back to "Upload"' in refused.value.message


def test_a_forward_decision_on_a_step_inside_an_existing_loop_is_made() -> None:
    result = apply_operations(_agent_loop_draft(), ops(_add(after="extract")))
    assert [d["id"] for d in _decisions(result.blueprint)] == ["redo", "confident_enough"]


def test_a_step_added_or_moved_inside_an_agents_loop_is_made() -> None:
    added = apply_operations(
        _agent_loop_draft(),
        ops({"op": "add_step", "name": "Check", "type": "user_task", "after": "extract"}),
    ).blueprint
    assert [s["id"] for s in added["workflow"]["steps"]] == [
        "upload",
        "extract",
        "check",
        "review",
        "deliver",
    ]
    moved = apply_operations(added, ops({"op": "move_step", "step_id": "check", "after": "upload"}))
    assert [s["id"] for s in moved.blueprint["workflow"]["steps"]][:3] == [
        "upload",
        "check",
        "extract",
    ]


def test_a_new_branch_back_inside_an_agents_loop_is_refused() -> None:
    draft = _agent_loop_draft()
    back = [{"condition": "again", "target": "upload"}, {"condition": "ok", "target": "review"}]
    with pytest.raises(OperationError) as refused:
        apply_operations(draft, ops(_add(after="extract", branches=back)))
    assert refused.value.code == "cycle"
    assert 'the decision after "Extract" would lead back to "Upload"' in refused.value.message
    # The agent's own back branch moved to another earlier step is a new one too.
    moved = [
        {"condition": "ok", "target": "deliver"},
        {"condition": "again", "target": "extract"},
    ]
    with pytest.raises(OperationError) as refused:
        apply_operations(
            draft, ops({"op": "update_decision", "decision_id": "redo", "branches": moved})
        )
    assert refused.value.code == "cycle"


def test_a_move_that_makes_a_loop_through_a_decision_is_refused() -> None:
    draft = _plain_draft()
    made = apply_operations(
        draft,
        ops(
            {"op": "add_step", "name": "Alpha", "type": "user_task", "after": "deliver"},
            {"op": "add_step", "name": "Beta", "type": "user_task", "after": "alpha"},
            _add(name="Go", after="alpha", branches=_to("beta", "end")),
        ),
    ).blueprint
    with pytest.raises(OperationError) as refused:
        apply_operations(made, ops({"op": "move_step", "step_id": "beta", "after": "deliver"}))
    assert refused.value.code == "cycle"
    # No branch was added: the move closed the loop, and the message says so.
    assert '"Beta", "Alpha"' in refused.value.message
    assert "in a circle" in refused.value.message


def test_a_second_decision_after_one_step_is_refused() -> None:
    first = apply_operations(_plain_draft(), ops(_add())).blueprint
    with pytest.raises(OperationError) as refused:
        apply_operations(first, ops(_add(name="Again")))
    assert (refused.value.code, refused.value.field) == ("invalid", "after")


# ---------------------------------------------------------------- update and remove


def test_a_decision_is_renamed_and_its_branches_replaced() -> None:
    draft = apply_operations(_plain_draft(), ops(_add())).blueprint
    renamed = apply_operations(
        draft,
        ops({"op": "update_decision", "decision_id": "confident_enough", "name": "Sure?"}),
    ).blueprint
    assert _decisions(renamed)[0]["name"] == "Sure?"
    assert _decisions(renamed)[0]["branches"] == _decisions(draft)[0]["branches"]
    assert _decisions(renamed)[0]["id"] == "confident_enough"

    branches = [
        {"condition": "High", "target": "deliver"},
        {"condition": "Medium", "target": "review"},
        {"condition": "Low", "target": "end"},
    ]
    result = apply_operations(
        renamed,
        ops({"op": "update_decision", "decision_id": "confident_enough", "branches": branches}),
    )
    assert _decisions(result.blueprint)[0] == {
        "id": "confident_enough",
        "name": "Sure?",
        "after": "extract",
        "branches": branches,
    }
    assert result.summaries == ['Changed decision "Sure?"']
    assert ("Gateway_decision_confident_enough", "Activity_deliver", "High") in _flows(
        result.blueprint
    )


def test_an_update_is_checked_as_an_add_is() -> None:
    draft = apply_operations(_plain_draft(), ops(_add())).blueprint
    cases = (
        (
            [{"condition": "a", "target": "gone"}, {"condition": "b", "target": "end"}],
            "unknown_step",
        ),
        ([{"condition": "a", "target": "upload"}, {"condition": "b", "target": "end"}], "cycle"),
        ([{"condition": "a", "target": "end"}, {"condition": "b", "target": "end"}], "invalid"),
    )
    for branches, code in cases:
        op = {"op": "update_decision", "decision_id": "confident_enough", "branches": branches}
        with pytest.raises(OperationError) as refused:
            apply_operations(draft, ops(op))
        assert refused.value.code == code
    with pytest.raises(OperationError) as refused:
        apply_operations(draft, ops({"op": "update_decision", "decision_id": "x", "name": "Y"}))
    assert (refused.value.code, refused.value.field) == ("not_found", "decision_id")
    with pytest.raises(ValidationError):
        ops({"op": "update_decision", "decision_id": "confident_enough", "branches": []})


def test_a_decision_is_removed() -> None:
    draft = apply_operations(_plain_draft(), ops(_add())).blueprint
    result = apply_operations(
        draft, ops({"op": "remove_decision", "decision_id": "confident_enough"})
    )
    assert _decisions(result.blueprint) == []
    assert result.summaries == ['Removed decision "Confident enough?"']
    assert not any(src.startswith("Gateway_decision") for src, _, _ in _flows(result.blueprint))
    with pytest.raises(OperationError) as refused:
        apply_operations(draft, ops({"op": "remove_decision", "decision_id": "nope"}))
    assert (refused.value.code, refused.value.field) == ("not_found", "decision_id")


def test_an_agents_decision_keeps_what_the_edit_does_not_name() -> None:
    # The fixture's "confident" has one branch, as an agent may write it.
    result = apply_operations(
        _draft(), ops({"op": "update_decision", "decision_id": "confident", "name": "Sure?"})
    )
    confident = _decisions(result.blueprint)[0]
    assert confident == {
        "id": "confident",
        "name": "Sure?",
        "after": "extract",
        "branches": [{"condition": "yes", "target": "review"}],
    }


# ---------------------------------------------------------------- through the API


@requires_postgres
def test_decisions_through_the_api_and_the_mapping_names_them(
    client, db_session, monkeypatch
) -> None:
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
    assert _decisions(_read_draft(created["output_dir"]))[0]["id"] == "confident_enough"

    mapping = client.get(f"/sessions/{sid}/bpmn/mapping").json()["mapping"]
    entry = mapping["Gateway_decision_confident_enough"]
    assert entry["kind"] == "decision_point"
    assert entry["decision"] == {
        "id": "confident_enough",
        "name": "Confident enough?",
        "after": "extract",
        "branches": [
            {"condition": "Sure", "target": "review"},
            {"condition": "Unsure", "target": "end"},
        ],
    }
    xml = client.get(f"/sessions/{sid}/bpmn").text
    assert re.search(r'<bpmn:exclusiveGateway id="Gateway_decision_confident_enough"', xml)

    refused = client.post(
        f"/sessions/{sid}/blueprint/operations",
        json={
            "base_version": res.json()["session"]["active_version"],
            "operations": [
                {
                    "op": "update_decision",
                    "decision_id": "confident_enough",
                    "branches": [
                        {"condition": "a", "target": "gone"},
                        {"condition": "b", "target": "end"},
                    ],
                }
            ],
        },
    )
    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "unknown_step"
    assert refused.json()["detail"]["field"] == "target"

    removed = client.post(
        f"/sessions/{sid}/blueprint/operations",
        json={
            "base_version": res.json()["session"]["active_version"],
            "operations": [{"op": "remove_decision", "decision_id": "confident_enough"}],
        },
    )
    assert removed.status_code == 200, removed.text
    mapping = client.get(f"/sessions/{sid}/bpmn/mapping").json()["mapping"]
    assert not any(k.startswith("Gateway_decision") for k in mapping)


def test_the_mapping_names_an_empty_target_the_end() -> None:
    from wizard_api.services.bpmn_service import named_mapping

    drawn = _plain_draft()
    drawn["business_process"]["decision_points"] = [
        {
            "id": "ok",
            "name": "OK?",
            "after": "extract",
            "branches": [
                {"condition": "yes", "target": "review"},
                {"condition": "no", "target": ""},
            ],
        }
    ]
    mapping = {
        "Gateway_decision_ok": {
            "kind": "decision_point",
            "blueprint_path": "business_process.decision_points[0]",
        }
    }
    entry = named_mapping(mapping, drawn)["Gateway_decision_ok"]
    assert entry["decision"]["branches"][1] == {"condition": "no", "target": "end"}


def test_a_finnish_decision_name_gives_a_readable_id() -> None:
    result = apply_operations(_plain_draft(), ops(_add(name="Hyväksytäänkö?", after="upload")))

    assert [d["id"] for d in _decisions(result.blueprint)] == ["hyvaksytaanko"]
