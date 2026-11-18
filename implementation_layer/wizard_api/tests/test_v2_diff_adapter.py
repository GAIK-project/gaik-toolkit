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
    operations_from_v2_diff,
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
