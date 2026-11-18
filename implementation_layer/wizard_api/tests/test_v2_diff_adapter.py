"""``operations_from_v2_diff``: the reduced (V2) blueprint's step edits as typed operations.

The old saves (the Blueprint form's PATCH and the diagram's ``/bpmn/sync``) send a
whole reduced blueprint. With the agent's draft canonical, what changed between
the reduced view of the draft and the saved one is applied to the draft as
operations, so every write goes through ``apply_operations``.
"""

import pytest
from test_blueprint_ops import _draft
from wizard_api.schemas.blueprint_ops import (
    AddStep,
    Connect,
    MoveStep,
    RemoveStep,
    RenameStep,
    SetStepDescription,
    SetStepType,
)
from wizard_api.services import artifact_sync, blueprint_ops
from wizard_api.services.blueprint_ops import (
    OperationError,
    apply_operations,
    field_edits_from_v2_diff,
    operations_from_v2_diff,
    v2_step_ids,
)

pytestmark = pytest.mark.skipif(
    not blueprint_ops.solution_wizard_available(),
    reason="solution_wizard package not installed",
)


def _view(draft: dict) -> dict:
    return artifact_sync.blueprint_from_draft(draft).model_dump()


def _steps(view: dict) -> list[tuple[str, str, str]]:
    return [(s["id"], s["name"], s["type"]) for s in view["steps"]]


def test_the_diff_finds_rename_add_remove_move_and_type() -> None:
    draft = _draft()
    # Without the fixture's decisions: "confident" (after extract, to review,
    # which goes to deliver) would lead back once deliver moves before extract,
    # a loop the operations refuse (test_a_reorder_that_turns_a_branch_back_is_refused).
    draft["business_process"]["decision_points"] = []
    old = _view(draft)
    by_id = {s["id"]: dict(s) for s in old["steps"]}
    # upload -> extract -> review -> deliver becomes upload -> deliver (now a user
    # task) -> extract (renamed) -> check (new); review, whose output deliver read, is gone.
    new = {
        **old,
        "steps": [
            by_id["upload"],
            {**by_id["deliver"], "type": "io"},
            {**by_id["extract"], "name": "Read the invoice", "description": "Reads every field"},
            {"id": "check", "name": "Check", "type": "human_review"},
        ],
    }

    ops = operations_from_v2_diff(old, new)

    kinds = [type(op) for op in ops]
    # Removes first, then adds, then moves, then renames, descriptions and types.
    assert kinds == [RemoveStep, AddStep, MoveStep, RenameStep, SetStepDescription, SetStepType]
    assert ops[0].step_id == "review"
    assert (ops[1].name, ops[1].type, ops[1].after) == ("Check", "human_review", "extract")
    assert (ops[2].step_id, ops[2].after) == ("deliver", "upload")
    assert (ops[3].step_id, ops[3].name) == ("extract", "Read the invoice")
    assert (ops[4].step_id, ops[4].description) == ("extract", "Reads every field")
    assert (ops[5].step_id, ops[5].type) == ("deliver", "user_task")

    result = apply_operations(draft, ops)

    assert _steps(_view(result.blueprint)) == _steps(new)
    applied = {s["id"]: s for s in result.blueprint["workflow"]["steps"]}
    assert applied["extract"]["description"] == "Reads every field"


def test_no_change_is_no_operation() -> None:
    old = _view(_draft())
    assert operations_from_v2_diff(old, {**old, "steps": [dict(s) for s in old["steps"]]}) == []


def test_an_added_step_after_another_added_step_follows_its_new_id() -> None:
    draft = _draft()
    old = _view(draft)
    # Ids the client made up; the draft names a new step after its name.
    new = {
        **old,
        "steps": [
            *old["steps"],
            {"id": "tmp-1", "name": "Notify", "type": "io"},
            {"id": "tmp-2", "name": "Archive copy", "type": "io"},
        ],
    }

    ops = operations_from_v2_diff(old, new)

    assert [(op.name, op.after) for op in ops] == [
        ("Notify", "deliver"),
        ("Archive copy", "notify"),
    ]
    result = apply_operations(draft, ops)
    assert [s["id"] for s in result.blueprint["workflow"]["steps"]][-2:] == [
        "notify",
        "archive_copy",
    ]


def test_a_reserved_id_is_not_predicted_for_a_new_step() -> None:
    draft = _draft()
    old = _view(draft)
    new = {
        **old,
        "steps": [
            *old["steps"],
            {"id": "a", "name": "Archive", "type": "io"},
            {"id": "b", "name": "After", "type": "io"},
        ],
    }

    # "archive" is the draft's manual step, so the new step becomes archive_2.
    ops = operations_from_v2_diff(old, new, reserved_ids={"archive"})

    assert ops[1].after == "archive_2"
    result = apply_operations(draft, ops)
    assert [s["id"] for s in result.blueprint["workflow"]["steps"]][-2:] == ["archive_2", "after"]


def test_a_description_is_compared_only_when_the_new_step_has_one() -> None:
    draft = _draft()
    old = _view(draft)
    old["steps"][1]["description"] = "Reads the invoice"
    new = {
        **old,
        "steps": [{k: v for k, v in s.items() if k != "description"} for s in old["steps"]],
    }

    assert operations_from_v2_diff(old, new) == []


def test_an_unknown_step_type_is_refused() -> None:
    old = _view(_draft())
    new = {**old, "steps": [{**old["steps"][0], "type": "robot"}, *old["steps"][1:]]}

    with pytest.raises(OperationError) as exc:
        operations_from_v2_diff(old, new)

    assert exc.value.code == "invalid"


def test_a_name_over_the_limit_is_refused_as_an_operation_error() -> None:
    old = _view(_draft())
    new = {**old, "steps": [{**old["steps"][0], "name": "x" * 201}, *old["steps"][1:]]}

    with pytest.raises(OperationError):
        operations_from_v2_diff(old, new)


def test_a_step_added_in_place_of_a_removed_one_is_a_new_step() -> None:
    draft = _draft()
    old = _view(draft)
    by_id = {s["id"]: s for s in old["steps"]}
    # The removed step's id is free again, so the new step gets it.
    new = {
        **old,
        "steps": [
            by_id["upload"],
            by_id["extract"],
            {"id": "tmp", "name": "Review", "type": "io", "description": "By hand"},
            by_id["deliver"],
        ],
    }

    ops = operations_from_v2_diff(old, new)

    assert [type(op) for op in ops] == [RemoveStep, AddStep, SetStepDescription]
    result = apply_operations(draft, ops)
    review = {s["id"]: s for s in result.blueprint["workflow"]["steps"]}["review"]
    assert (review["type"], review["description"]) == ("user_task", "By hand")


def test_two_steps_with_one_id_are_refused() -> None:
    old = _view(_draft())
    new = {**old, "steps": [*old["steps"], dict(old["steps"][0])]}

    with pytest.raises(OperationError):
        operations_from_v2_diff(old, new)


def _deps(blueprint: dict) -> dict[str, list[str]]:
    return {s["id"]: s["depends_on"] for s in blueprint["workflow"]["steps"]}


def test_a_step_added_at_the_start_comes_before_the_old_first_step() -> None:
    draft = _draft()
    old = _view(draft)
    new = {**old, "steps": [{"id": "tmp", "name": "Receive", "type": "io"}, *old["steps"]]}

    ops = operations_from_v2_diff(old, new)

    assert (ops[0].after, ops[0].before) == (None, "upload")
    deps = _deps(apply_operations(draft, ops).blueprint)
    assert deps["receive"] == []
    assert deps["upload"] == ["receive"]


def test_a_step_moved_to_the_start_stays_in_the_flow() -> None:
    draft = _draft()
    # Deliver reads nothing, so it may come first.
    draft["workflow"]["steps"][3]["inputs"] = []
    old = _view(draft)
    by_id = {s["id"]: s for s in old["steps"]}
    new = {**old, "steps": [by_id[i] for i in ("deliver", "upload", "extract", "review")]}

    ops = operations_from_v2_diff(old, new)

    assert [(type(op), getattr(op, "after", None)) for op in ops] == [
        (MoveStep, None),
        (Connect, None),
    ]
    assert (ops[1].source, ops[1].target) == ("deliver", "upload")
    result = apply_operations(draft, ops).blueprint
    assert [s["id"] for s in result["workflow"]["steps"]] == [
        "deliver",
        "upload",
        "extract",
        "review",
    ]
    deps = _deps(result)
    assert deps["deliver"] == []
    assert deps["upload"] == ["deliver"]
    assert deps["extract"] == ["upload"]
    assert deps["review"] == ["extract"]


def test_the_fields_outside_the_steps_round_trip_through_the_draft() -> None:
    draft = _draft()
    draft["workflow"]["steps"][1]["parameters"] = {"pages": 3}
    old = _view(draft)
    new = {
        **old,
        "name": "Supplier invoices",
        "description": "Reads them",
        "goal": "No typing",
        "integration_targets": ["ERP"],
        "steps": [
            {**old["steps"][0], "component": "parser"},
            {**old["steps"][1], "settings": {"pages": "3", "language": "fi"}},
            *old["steps"][2:],
        ],
    }

    edits = field_edits_from_v2_diff(old, new, v2_step_ids(old, new))
    result = apply_operations(draft, edits).blueprint

    # A setting shown as it was keeps its value: the number stays a number.
    assert result["workflow"]["steps"][1]["parameters"] == {"pages": 3, "language": "fi"}
    back = _view(result)
    for key in ("name", "description", "goal", "integration_targets"):
        assert back[key] == new[key]
    assert back["steps"][0]["component"] == "parser"
    assert back["steps"][1]["settings"] == {"pages": "3", "language": "fi"}
    assert field_edits_from_v2_diff(back, new, v2_step_ids(back, new)) == []


def test_an_ai_step_without_a_component_needs_one() -> None:
    draft = _draft()
    old = _view(draft)
    new = {**old, "steps": [{**old["steps"][0], "type": "ai"}, *old["steps"][1:]]}

    result = apply_operations(draft, operations_from_v2_diff(old, new))

    assert "upload: needs a component" in result.needs_attention
    # Shown as io without a component, unless remembered as an AI step.
    assert _view(result.blueprint)["steps"][0]["type"] == "io"
    remembered = artifact_sync.blueprint_from_draft(result.blueprint, frozenset({"upload"}))
    assert remembered.steps[0]["type"] == "ai"


def test_an_ai_step_whose_component_is_cleared_stays_ai() -> None:
    from wizard_api.services import blueprint_edit_service

    draft = _draft()
    old = _view(draft)
    assert old["steps"][1]["type"] == "ai"
    new = {
        **old,
        "steps": [
            old["steps"][0],
            {k: v for k, v in old["steps"][1].items() if k != "component"},
            *old["steps"][2:],
        ],
    }

    edit = blueprint_edit_service.v2_edit(draft, old, new)

    assert edit.ai_steps == {"extract"}
    result = apply_operations(draft, edit.operations)
    assert "extract: needs a component" in result.needs_attention
    shown = artifact_sync.blueprint_from_draft(result.blueprint, frozenset(edit.ai_steps))
    assert shown.steps[1]["type"] == "ai"


def test_an_ai_step_kept_with_its_component_is_not_remembered() -> None:
    from wizard_api.services import blueprint_edit_service

    draft = _draft()
    old = _view(draft)
    new = {**old, "steps": [{**old["steps"][0], "name": "Upload it"}, *old["steps"][1:]]}

    assert blueprint_edit_service.v2_edit(draft, old, new).ai_steps == set()


def test_a_reorder_that_turns_a_branch_back_is_refused() -> None:
    # The fixture's decision after extract leads to review; once review is gone
    # it leads to deliver, and deliver moved before extract makes the drawn
    # flow loop: extract -> decision -> deliver -> extract.
    draft = _draft()
    old = _view(draft)
    by_id = {s["id"]: dict(s) for s in old["steps"]}
    new = {**old, "steps": [by_id["upload"], by_id["deliver"], by_id["extract"]]}
    with pytest.raises(OperationError) as refused:
        apply_operations(draft, operations_from_v2_diff(old, new))
    assert refused.value.code == "cycle"
