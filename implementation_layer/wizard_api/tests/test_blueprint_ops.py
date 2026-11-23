"""Typed operations on the full blueprint draft (pure: no database, no files)."""

import copy

import pytest
from pydantic import TypeAdapter, ValidationError
from wizard_api.schemas.blueprint_ops import Operation, OperationsRequest
from wizard_api.services import blueprint_ops
from wizard_api.services.blueprint_ops import (
    OperationError,
    apply_operations,
    bpmn_relevant_digest,
    new_step_id,
)

pytestmark = pytest.mark.skipif(
    not blueprint_ops.solution_wizard_available(),
    reason="solution_wizard package not installed",
)

if blueprint_ops.solution_wizard_available():
    from solution_wizard import validator
    from solution_wizard.blueprint import Blueprint

_OPS = TypeAdapter(list[Operation])


def ops(*items):
    return _OPS.validate_python(list(items))


def _step(sid, kind, *, depends_on=(), inputs=(), outputs=(), component=None, **extra):
    step = {
        "id": sid,
        "name": sid.replace("_", " ").capitalize(),
        "type": kind,
        "inputs": list(inputs),
        "outputs": list(outputs),
        "depends_on": list(depends_on),
        **extra,
    }
    if component:
        step["component"] = component
    return step


def _generated(produced_by, *, final=False):
    return {
        "type": "structured_json",
        "source": "generated",
        "optional": False,
        "produced_by": produced_by,
        "final_output": final,
    }


def _draft():
    """upload -> extract -> review -> deliver, with every kind of reference to extract."""
    return {
        "use_case": {"id": "invoices", "name": "Invoices", "description": "d", "domain": "d"},
        "business_spec": {
            "intended_users": ["Clerk"],
            "reviewers": ["Controller"],
            "current_process": "by hand",
        },
        "technical_spec": {"input_types": ["pdf"], "output_types": ["structured_json"]},
        "artifacts": {
            "invoice": {"type": "pdf", "source": "user_upload", "optional": False},
            "fields": _generated("extract"),
            "reviewed": _generated("review"),
            "report": _generated("deliver", final=True),
        },
        "workflow": {
            "steps": [
                _step("upload", "user_task", outputs=["invoice"]),
                _step(
                    "extract",
                    "automated_task",
                    component="custom",
                    depends_on=["upload"],
                    inputs=["invoice"],
                    outputs=["fields"],
                    description="Reads the invoice",
                ),
                _step(
                    "review",
                    "human_review",
                    depends_on=["extract"],
                    inputs=["fields"],
                    outputs=["reviewed"],
                ),
                _step(
                    "deliver",
                    "automated_task",
                    component="custom",
                    depends_on=["review"],
                    inputs=["reviewed"],
                    outputs=["report"],
                ),
            ]
        },
        "business_process": {
            "participants": [
                {"id": "clerk", "name": "Clerk", "default_lane_for": ["user_task"]},
                {"id": "system", "name": "AI system", "kind": "system"},
            ],
            "manual_steps": [
                {"id": "archive", "name": "Archive", "depends_on": ["extract", "deliver"]}
            ],
            "external_parties": [
                {"id": "supplier", "name": "Supplier", "sends": ["invoice"], "to_step": "extract"}
            ],
            "message_flows": [
                {"from": "supplier", "to": "extract", "name": "invoice"},
                {"from": "deliver", "to": "supplier", "name": "report"},
            ],
            "exceptions": [
                {"id": "unreadable", "name": "Unreadable", "attached_to": "extract"},
                {
                    "id": "rejected",
                    "name": "Rejected",
                    "attached_to": "review",
                    "outcome": "loop_to:extract",
                },
            ],
            "decision_points": [
                {
                    "id": "confident",
                    "name": "Confident?",
                    "after": "extract",
                    "branches": [{"condition": "yes", "target": "review"}],
                },
                {
                    "id": "readable",
                    "name": "Readable?",
                    "after": "upload",
                    "branches": [
                        {"condition": "yes", "target": "extract"},
                        {"condition": "no", "target": "end"},
                    ],
                },
            ],
        },
        "governance": {"data_handling": {"contains_personal_data": "no"}},
    }


def _steps(blueprint):
    return {s["id"]: s for s in blueprint["workflow"]["steps"]}


def _order(blueprint):
    return [s["id"] for s in blueprint["workflow"]["steps"]]


def _valid(blueprint):
    return validator.validate(Blueprint.model_validate(blueprint))


def test_the_fixture_is_a_valid_blueprint():
    result = _valid(_draft())
    assert result.ok, result.summary()


# ---------------------------------------------------------------- new_step_id


def test_new_step_id_is_a_lower_case_slug_numbered_when_taken():
    assert new_step_id("Extract Invoice-Fields!", set()) == "extract_invoice_fields"
    assert new_step_id("  Check  ", {"check"}) == "check_2"
    assert new_step_id("Check", {"check", "check_2"}) == "check_3"
    assert new_step_id("???", set()) == "step"
    assert new_step_id("???", {"step"}) == "step_2"


def test_new_step_id_drops_the_marks_of_finnish_letters():
    assert new_step_id("Käsittele lasku", set()) == "kasittele_lasku"
    assert new_step_id("Tarkista ostotilaus ja hyväksyntä", set()) == (
        "tarkista_ostotilaus_ja_hyvaksynta"
    )
    assert new_step_id("Åland-öljy", set()) == "aland_oljy"
    assert new_step_id("Öö", {"oo"}) == "oo_2"


# ---------------------------------------------------------------- schemas


def test_operations_request_reads_the_union_by_op_and_limits_the_list():
    request = OperationsRequest.model_validate(
        {"base_version": 3, "operations": [{"op": "remove_step", "step_id": "a"}]}
    )
    assert type(request.operations[0]).__name__ == "RemoveStep"
    with pytest.raises(ValidationError):
        OperationsRequest.model_validate({"base_version": 3, "operations": []})
    many = [{"op": "remove_step", "step_id": "a"}] * 51
    with pytest.raises(ValidationError):
        OperationsRequest.model_validate({"base_version": 3, "operations": many})
    with pytest.raises(ValidationError):
        OperationsRequest.model_validate(
            {"base_version": 3, "operations": [{"op": "drop_table", "step_id": "a"}]}
        )


# ---------------------------------------------------------------- rename / description


def test_rename_step_writes_a_plain_summary():
    result = apply_operations(
        _draft(), ops({"op": "rename_step", "step_id": "extract", "name": "Extract invoice fields"})
    )
    assert _steps(result.blueprint)["extract"]["name"] == "Extract invoice fields"
    assert result.summaries == ['Renamed step "Extract" to "Extract invoice fields"']


def test_a_blank_name_is_refused():
    with pytest.raises(OperationError) as err:
        apply_operations(_draft(), ops({"op": "rename_step", "step_id": "extract", "name": "  "}))
    assert (err.value.code, err.value.field) == ("invalid", "name")
    with pytest.raises(OperationError) as err:
        apply_operations(_draft(), ops({"op": "add_step", "name": "", "type": "user_task"}))
    assert (err.value.code, err.value.field) == ("invalid", "name")


def test_an_unknown_step_is_not_found():
    for op in (
        {"op": "rename_step", "step_id": "nope", "name": "X"},
        {"op": "set_step_description", "step_id": "nope", "description": "X"},
        {"op": "remove_step", "step_id": "nope"},
        {"op": "move_step", "step_id": "nope", "after": None},
        {"op": "move_step", "step_id": "extract", "after": "nope"},
        {"op": "connect", "source": "nope", "target": "extract"},
        {"op": "disconnect", "source": "upload", "target": "nope"},
        {"op": "set_step_type", "step_id": "nope", "type": "user_task"},
        {"op": "add_step", "name": "X", "type": "user_task", "after": "nope"},
        {"op": "add_step", "name": "X", "type": "user_task", "before": "nope"},
    ):
        with pytest.raises(OperationError) as err:
            apply_operations(_draft(), ops(op))
        assert err.value.code == "not_found", op


def test_a_rename_changes_the_bpmn_relevant_digest():
    draft = _draft()
    result = apply_operations(draft, ops({"op": "rename_step", "step_id": "review", "name": "X"}))
    assert bpmn_relevant_digest(result.blueprint) != bpmn_relevant_digest(draft)
    assert result.bpmn_changed is True


def test_a_field_outside_the_digest_leaves_it_unchanged():
    draft = _draft()
    edited = copy.deepcopy(draft)
    edited["business_spec"]["current_process"] = "with a spreadsheet"
    edited["prompts"] = {"extract": "Read the invoice"}
    assert bpmn_relevant_digest(edited) == bpmn_relevant_digest(draft)
    edited["business_spec"]["reviewers"] = ["Auditor"]
    assert bpmn_relevant_digest(edited) != bpmn_relevant_digest(draft)


def test_set_step_description_only_changes_the_description():
    draft = _draft()
    result = apply_operations(
        draft,
        ops({"op": "set_step_description", "step_id": "review", "description": "Checks totals"}),
    )
    expected = copy.deepcopy(draft)
    _steps(expected)["review"]["description"] = "Checks totals"
    assert result.blueprint == expected
    assert result.bpmn_changed is True
    assert result.summaries == ['Changed the description of step "Review"']


# ---------------------------------------------------------------- add_step


def test_add_step_inserts_between_a_single_successor():
    result = apply_operations(
        _draft(),
        ops({"op": "add_step", "name": "Check totals", "type": "user_task", "after": "review"}),
    )
    steps = _steps(result.blueprint)
    assert steps["check_totals"]["depends_on"] == ["review"]
    assert steps["deliver"]["depends_on"] == ["check_totals"]
    assert _order(result.blueprint) == ["upload", "extract", "review", "check_totals", "deliver"]
    assert steps["check_totals"]["type"] == "user_task"


def test_add_step_before_replaces_after_in_the_before_steps_dependencies():
    draft = _draft()
    _steps(draft)["deliver"]["depends_on"] = ["review", "upload"]
    result = apply_operations(
        draft,
        ops(
            {
                "op": "add_step",
                "name": "Sign",
                "type": "human_review",
                "after": "review",
                "before": "deliver",
            }
        ),
    )
    steps = _steps(result.blueprint)
    assert steps["sign"]["depends_on"] == ["review"]
    assert steps["deliver"]["depends_on"] == ["sign", "upload"]


def test_add_step_after_the_last_step_becomes_the_new_end():
    result = apply_operations(
        _draft(), ops({"op": "add_step", "name": "Notify", "type": "user_task", "after": "deliver"})
    )
    steps = _steps(result.blueprint)
    assert steps["notify"]["depends_on"] == ["deliver"]
    assert _order(result.blueprint)[-1] == "notify"
    assert all("notify" not in s["depends_on"] for s in steps.values())


def test_add_step_after_a_step_with_several_successors_is_a_new_branch():
    draft = _draft()
    draft["workflow"]["steps"].append(_step("audit", "user_task", depends_on=["review"]))
    result = apply_operations(
        draft, ops({"op": "add_step", "name": "Escalate", "type": "user_task", "after": "review"})
    )
    steps = _steps(result.blueprint)
    assert steps["escalate"]["depends_on"] == ["review"]
    assert steps["deliver"]["depends_on"] == ["review"]
    assert steps["audit"]["depends_on"] == ["review"]


def test_an_automated_step_without_a_component_needs_attention():
    result = apply_operations(
        _draft(),
        ops({"op": "add_step", "name": "Classify", "type": "automated_task", "after": "deliver"}),
    )
    assert "classify: needs a component" in result.needs_attention
    assert "component" not in _steps(result.blueprint)["classify"] or (
        _steps(result.blueprint)["classify"]["component"] is None
    )


# ---------------------------------------------------------------- remove_step


def test_removing_a_step_repairs_every_reference_to_it():
    result = apply_operations(_draft(), ops({"op": "remove_step", "step_id": "extract"}))
    bp = result.blueprint
    steps = _steps(bp)
    process = bp["business_process"]

    assert "extract" not in steps
    # The successor takes over the removed step's dependencies.
    assert steps["review"]["depends_on"] == ["upload"]
    # Its artifact goes, and leaves the consumer's inputs, with a warning.
    assert "fields" not in bp["artifacts"]
    assert steps["review"]["inputs"] == []
    assert len(result.warnings) == 1 and '"fields"' in result.warnings[0]
    # The decision point after it goes; a branch to it moves to its first successor.
    assert [d["id"] for d in process["decision_points"]] == ["readable"]
    assert process["decision_points"][0]["branches"][0]["target"] == "review"
    # The exception attached to it goes; a loop back to it ends instead.
    assert [e["id"] for e in process["exceptions"]] == ["rejected"]
    assert process["exceptions"][0]["outcome"] == "end"
    # The external party hands in to its first successor.
    assert process["external_parties"][0]["to_step"] == "review"
    # Manual steps and message flows drop the id.
    assert process["manual_steps"][0]["depends_on"] == ["deliver"]
    assert all("extract" not in (f["from"], f["to"]) for f in process["message_flows"])
    assert result.summaries == ['Removed step "Extract"']

    check = _valid(bp)
    assert check.ok, check.summary()


def test_removing_the_last_step_in_the_chain_ends_references_or_drops_them():
    draft = _draft()
    process = draft["business_process"]
    process["external_parties"][0]["to_step"] = "deliver"
    process["decision_points"][1]["branches"][1]["target"] = "deliver"
    draft["artifacts"]["reviewed"]["final_output"] = True
    result = apply_operations(draft, ops({"op": "remove_step", "step_id": "deliver"}))
    process = result.blueprint["business_process"]
    assert process["external_parties"] == []
    assert process["decision_points"][1]["branches"][1]["target"] == "end"
    assert all("supplier" not in (f["from"], f["to"]) for f in process["message_flows"])


def test_removing_the_only_step_is_refused():
    draft = _draft()
    draft["workflow"]["steps"] = [_step("upload", "user_task", outputs=["invoice"])]
    with pytest.raises(OperationError) as err:
        apply_operations(draft, ops({"op": "remove_step", "step_id": "upload"}))
    assert err.value.code == "last_step"


# ---------------------------------------------------------------- move_step


def test_move_step_bridges_its_old_place_and_keeps_its_data():
    draft = _draft()
    draft["workflow"]["steps"].append(_step("notify", "user_task", depends_on=["deliver"]))
    _steps(draft)["notify"]["description"] = "Tell the clerk"
    _steps(draft)["notify"]["performed_by"] = "clerk"
    result = apply_operations(
        draft, ops({"op": "move_step", "step_id": "notify", "after": "upload"})
    )
    steps = _steps(result.blueprint)
    assert steps["notify"]["depends_on"] == ["upload"]
    assert steps["extract"]["depends_on"] == ["notify"]
    assert steps["notify"]["description"] == "Tell the clerk"
    assert steps["notify"]["performed_by"] == "clerk"
    assert _order(result.blueprint) == ["upload", "notify", "extract", "review", "deliver"]
    assert result.summaries == ['Moved step "Notify" after "Upload"']


def test_move_step_without_after_makes_it_a_start():
    draft = _draft()
    draft["workflow"]["steps"].append(_step("notify", "user_task", depends_on=["deliver"]))
    result = apply_operations(draft, ops({"op": "move_step", "step_id": "notify", "after": None}))
    assert _steps(result.blueprint)["notify"]["depends_on"] == []
    assert _order(result.blueprint)[0] == "notify"
    assert result.summaries == ['Moved step "Notify" to the start']


def test_moving_a_consumer_before_its_producer_is_refused():
    with pytest.raises(OperationError) as err:
        apply_operations(
            _draft(), ops({"op": "move_step", "step_id": "deliver", "after": "upload"})
        )
    assert err.value.code == "invalid"
    assert "Rule 7" in err.value.message


# ---------------------------------------------------------------- connect / disconnect


def test_connect_adds_the_source_to_the_targets_dependencies():
    result = apply_operations(
        _draft(), ops({"op": "connect", "source": "upload", "target": "deliver"})
    )
    assert _steps(result.blueprint)["deliver"]["depends_on"] == ["review", "upload"]
    assert result.summaries == ['Connected "Upload" to "Deliver"']


def test_a_cycle_is_refused():
    with pytest.raises(OperationError) as err:
        apply_operations(_draft(), ops({"op": "connect", "source": "deliver", "target": "upload"}))
    assert err.value.code == "cycle"


def test_disconnect_removes_the_dependency():
    result = apply_operations(
        _draft(), ops({"op": "disconnect", "source": "review", "target": "deliver"})
    )
    assert _steps(result.blueprint)["deliver"]["depends_on"] == []
    assert result.summaries == ['Disconnected "Review" from "Deliver"']


# ---------------------------------------------------------------- set_step_type


def test_set_step_type_to_a_human_type_clears_the_component():
    result = apply_operations(
        _draft(), ops({"op": "set_step_type", "step_id": "extract", "type": "human_review"})
    )
    extract = _steps(result.blueprint)["extract"]
    assert extract["type"] == "human_review"
    assert extract.get("component") is None


def test_set_step_type_to_automated_without_a_component_needs_attention():
    result = apply_operations(
        _draft(), ops({"op": "set_step_type", "step_id": "review", "type": "automated_task"})
    )
    assert _steps(result.blueprint)["review"]["type"] == "automated_task"
    assert "review: needs a component" in result.needs_attention


# ---------------------------------------------------------------- validation policy


def test_an_operation_list_applies_all_or_nothing():
    draft = _draft()
    before = copy.deepcopy(draft)
    with pytest.raises(OperationError) as err:
        apply_operations(
            draft,
            ops(
                {"op": "rename_step", "step_id": "extract", "name": "Read"},
                {"op": "add_step", "name": "Sign", "type": "user_task", "after": "review"},
                {"op": "remove_step", "step_id": "missing"},
            ),
        )
    assert err.value.code == "not_found"
    assert draft == before


def test_errors_already_in_the_draft_do_not_refuse_an_edit():
    draft = _draft()
    _steps(draft)["deliver"]["inputs"].append("undeclared")  # a rule 2 error
    result = apply_operations(
        draft, ops({"op": "rename_step", "step_id": "deliver", "name": "Send"})
    )
    assert _steps(result.blueprint)["deliver"]["name"] == "Send"


def test_a_new_error_of_another_rule_is_returned_as_needs_attention():
    draft = _draft()
    draft["artifacts"]["report"]["final_output"] = False
    draft["artifacts"]["fields"]["final_output"] = True
    # Removing the step that produces the only final output adds a rule 9 error.
    result = apply_operations(draft, ops({"op": "remove_step", "step_id": "extract"}))
    assert any(item.startswith("Rule 9") for item in result.needs_attention)
