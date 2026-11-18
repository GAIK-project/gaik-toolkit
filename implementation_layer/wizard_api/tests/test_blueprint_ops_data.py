"""Data objects as operations: rename one, link it to a step and unlink it.

A data object is an ``artifacts`` entry, drawn as ``DataObjectRef_<id>`` and
named by its ``label`` (or a name the generator makes from its id and type).
A step uses it as an input (``inputs``) or makes it as an output
(``outputs``); a generated artifact names the step that makes it in
``produced_by``. The generator draws each link as a data association.
"""

import xml.etree.ElementTree as ET

import pytest
from helpers import requires_postgres
from pydantic import TypeAdapter, ValidationError
from test_blueprint_ops import _draft, _steps
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
_BPMN = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"


def ops(*items):
    return _OPS.validate_python(list(items))


def _rename(artifact_id="fields", label="Invoice fields") -> dict:
    return {"op": "rename_data_object", "artifact_id": artifact_id, "label": label}


def _link(artifact_id, step_id, role, op="link_data") -> dict:
    return {"op": op, "artifact_id": artifact_id, "step_id": step_id, "role": role}


def _unlink(artifact_id, step_id, role) -> dict:
    return _link(artifact_id, step_id, role, op="unlink_data")


def _refused(draft: dict, *items) -> OperationError:
    with pytest.raises(OperationError) as exc:
        apply_operations(draft, ops(*items))
    return exc.value


def _drawn(blueprint: dict) -> ET.Element:
    return ET.fromstring(generate_bpmn(Blueprint.model_validate(blueprint)))


def _data_object_name(blueprint: dict, artifact_id: str) -> str:
    ref = next(
        e
        for e in _drawn(blueprint).iter(f"{_BPMN}dataObjectReference")
        if e.get("id") == f"DataObjectRef_{artifact_id}"
    )
    return ref.get("name") or ""


def _associations(blueprint: dict) -> set[tuple[str, str, str]]:
    """(task, data object, "input" | "output") of every data association drawn."""
    out = set()
    for task in _drawn(blueprint).iter():
        for assoc in task.findall(f"{_BPMN}dataInputAssociation"):
            out.add((task.get("id"), assoc.find(f"{_BPMN}sourceRef").text, "input"))
        for assoc in task.findall(f"{_BPMN}dataOutputAssociation"):
            out.add((task.get("id"), assoc.find(f"{_BPMN}targetRef").text, "output"))
    return out


def _no_new_refusing_errors(draft: dict, blueprint: dict) -> None:
    def keys(bp):
        result = validator.validate(Blueprint.model_validate(bp))
        return {(i.rule, i.message) for i in result.errors if i.rule in {1, 2, 7, 8, 16}}

    assert keys(blueprint) <= keys(draft)


# ---------------------------------------------------------------- rename


def test_a_renamed_data_object_keeps_its_label_after_a_redraw() -> None:
    result = apply_operations(_draft(), ops(_rename(label="  Invoice fields  ")))
    assert result.blueprint["artifacts"]["fields"]["label"] == "Invoice fields"
    assert result.summaries == ['Renamed data object "fields" to "Invoice fields"']
    assert result.bpmn_changed
    assert _data_object_name(result.blueprint, "fields") == "Invoice fields"
    # Another edit, and the diagram drawn again: the name stays.
    later = apply_operations(
        result.blueprint, ops({"op": "rename_step", "step_id": "extract", "name": "Read it"})
    )
    assert _data_object_name(later.blueprint, "fields") == "Invoice fields"

    # An empty name clears the label: the generator names the data object again.
    cleared = apply_operations(later.blueprint, ops(_rename(label="  ")))
    assert "label" not in cleared.blueprint["artifacts"]["fields"]
    assert cleared.summaries == ['Cleared the name of data object "fields"']
    assert _data_object_name(cleared.blueprint, "fields") == _data_object_name(_draft(), "fields")


def test_a_rename_of_an_unknown_data_object_is_refused() -> None:
    err = _refused(_draft(), _rename(artifact_id="gone"))
    assert (err.code, err.field) == ("not_found", "artifact_id")


# ---------------------------------------------------------------- link


def test_linking_an_output_sets_the_producer() -> None:
    draft = _draft()
    # An agent's generated artifact whose producer does not make it.
    draft["artifacts"]["notes"] = {
        "type": "text",
        "source": "generated",
        "optional": True,
        "produced_by": "review",
    }
    result = apply_operations(draft, ops(_link("notes", "extract", "output")))
    assert result.blueprint["artifacts"]["notes"]["produced_by"] == "extract"
    assert _steps(result.blueprint)["extract"]["outputs"] == ["fields", "notes"]
    assert result.summaries == ['Step "Extract" now makes data object "notes"']
    assert ("Activity_extract", "DataObjectRef_notes", "output") in _associations(result.blueprint)
    _no_new_refusing_errors(draft, result.blueprint)
    # The agent's rule 7 error is gone too.
    assert validator.validate(Blueprint.model_validate(result.blueprint)).ok

    # A user's upload is captured by a step, not produced: no produced_by.
    draft = _draft()
    draft["artifacts"]["photo"] = {"type": "image", "source": "user_upload", "optional": True}
    result = apply_operations(draft, ops(_link("photo", "upload", "output")))
    assert _steps(result.blueprint)["upload"]["outputs"] == ["invoice", "photo"]
    assert "produced_by" not in result.blueprint["artifacts"]["photo"]


def test_linking_an_input_adds_it_and_a_later_artifact_is_refused() -> None:
    result = apply_operations(_draft(), ops(_link("invoice", "review", "input")))
    assert _steps(result.blueprint)["review"]["inputs"] == ["fields", "invoice"]
    assert result.summaries == ['Step "Review" now uses data object "invoice"']
    assert ("Activity_review", "DataObjectRef_invoice", "input") in _associations(result.blueprint)
    # The report is made after extract: extract cannot use it (rule 7 refuses).
    err = _refused(_draft(), _link("report", "extract", "input"))
    assert err.code == "invalid"


def test_a_second_producer_is_refused() -> None:
    err = _refused(_draft(), _link("fields", "review", "output"))
    assert (err.code, err.field) == ("second_producer", "artifact_id")
    # A user's upload has one step that captures it, too.
    err = _refused(_draft(), _link("invoice", "extract", "output"))
    assert err.code == "second_producer"


def test_a_link_the_step_already_has_is_refused() -> None:
    err = _refused(_draft(), _link("invoice", "extract", "input"))
    assert (err.code, err.field) == ("already_linked", "artifact_id")
    err = _refused(_draft(), _link("fields", "extract", "output"))
    assert err.code == "already_linked"


def test_an_unknown_data_object_step_or_role_is_refused() -> None:
    err = _refused(_draft(), _link("gone", "extract", "input"))
    assert (err.code, err.field) == ("not_found", "artifact_id")
    err = _refused(_draft(), _link("invoice", "gone", "input"))
    assert (err.code, err.field) == ("not_found", "step_id")
    err = _refused(_draft(), _unlink("invoice", "gone", "input"))
    assert (err.code, err.field) == ("not_found", "step_id")
    with pytest.raises(ValidationError):
        ops(_link("invoice", "extract", "both"))


def test_a_decision_step_has_no_data() -> None:
    # The generator draws a decision step as a gateway, which holds no data association.
    draft = _draft()
    draft["workflow"]["steps"].insert(
        2,
        {
            "id": "check",
            "name": "Check",
            "type": "decision",
            "inputs": [],
            "outputs": [],
            "depends_on": ["extract"],
        },
    )
    _steps(draft)["review"]["depends_on"] = ["check"]
    err = _refused(draft, _link("invoice", "check", "input"))
    assert (err.code, err.field) == ("invalid", "step_id")


# ---------------------------------------------------------------- unlink


def test_the_only_producer_of_a_used_artifact_cannot_be_unlinked() -> None:
    err = _refused(_draft(), _unlink("fields", "extract", "output"))
    assert (err.code, err.field) == ("still_used", "artifact_id")
    # A manual step that consumes it uses it too.
    draft = _draft()
    draft["business_process"]["manual_steps"][0]["consumes"] = ["report"]
    err = _refused(draft, _unlink("report", "deliver", "output"))
    assert err.code == "still_used"
    # Once nothing uses it, it still needs the step that makes it (see the next test).
    err = _refused(
        _draft(), _unlink("fields", "review", "input"), _unlink("fields", "extract", "output")
    )
    assert (err.code, err.index) == ("only_producer", 1)


def test_the_only_producer_of_a_generated_artifact_cannot_be_unlinked() -> None:
    # The deliverable: generated, final, used by no step. Removing the line
    # would leave it no step that makes it, and a data object is never deleted.
    err = _refused(_draft(), _unlink("report", "deliver", "output"))
    assert (err.code, err.field) == ("only_producer", "artifact_id")

    # A user's upload stays declared: nothing has to make it.
    draft = _draft()
    draft["workflow"]["steps"][1]["inputs"] = []
    result = apply_operations(draft, ops(_unlink("invoice", "upload", "output")))
    assert "invoice" in result.blueprint["artifacts"]
    assert _steps(result.blueprint)["upload"]["outputs"] == []
    assert result.warnings == []


def test_unlinking_one_of_two_producers_moves_produced_by() -> None:
    draft = _draft()
    draft["artifacts"]["fields"]["overwrite"] = True
    _steps(draft)["review"]["outputs"].append("fields")
    _steps(draft)["deliver"]["inputs"].append("fields")
    result = apply_operations(draft, ops(_unlink("fields", "extract", "output")))
    assert result.blueprint["artifacts"]["fields"]["produced_by"] == "review"
    assert _steps(result.blueprint)["extract"]["outputs"] == []
    assert result.summaries == ['Step "Extract" no longer makes data object "fields"']


def test_unlinking_an_input_removes_it_and_a_missing_link_is_refused() -> None:
    result = apply_operations(_draft(), ops(_unlink("invoice", "extract", "input")))
    assert _steps(result.blueprint)["extract"]["inputs"] == []
    assert result.summaries == ['Step "Extract" no longer uses data object "invoice"']
    assert ("Activity_extract", "DataObjectRef_invoice", "input") not in _associations(
        result.blueprint
    )
    err = _refused(_draft(), _unlink("invoice", "review", "input"))
    assert (err.code, err.field) == ("not_found", "artifact_id")
    err = _refused(_draft(), _unlink("fields", "review", "output"))
    assert err.code == "not_found"


def test_the_schemas_bound_the_label_and_forbid_other_fields() -> None:
    ops(_rename(label="x" * 200))
    with pytest.raises(ValidationError):
        ops(_rename(label="x" * 201))
    with pytest.raises(ValidationError):
        ops({**_rename(), "extra": 1})
    with pytest.raises(ValidationError):
        ops({**_link("invoice", "extract", "input"), "extra": 1})


# ---------------------------------------------------------------- mapping


def test_the_mapping_names_each_data_object() -> None:
    from wizard_api.services.bpmn_service import named_mapping

    drawn = _draft()
    drawn["artifacts"]["fields"]["label"] = "Invoice fields"
    blueprint = Blueprint.model_validate(drawn)
    generate_bpmn(blueprint)
    mapping = named_mapping(dict(blueprint.visualizations["bpmn_mapping"]), drawn)
    assert mapping["DataObjectRef_fields"]["data_object"] == {
        "id": "fields",
        "label": "Invoice fields",
    }
    assert mapping["DataObjectRef_invoice"]["data_object"] == {"id": "invoice", "label": ""}
    assert "data_object" not in mapping["Activity_extract"]


@requires_postgres
def test_data_objects_through_the_api(client, db_session, monkeypatch) -> None:
    from test_patch_blueprint_writes_draft import _create, _read_draft
    from wizard_api.services import agent_service

    monkeypatch.setattr(agent_service, "is_busy", lambda session_id: False)
    created = _create(client, db_session, draft=_draft())
    sid = created["id"]

    res = client.post(
        f"/sessions/{sid}/blueprint/operations",
        json={
            "base_version": created["active_version"],
            "operations": [_rename(), _link("invoice", "review", "input")],
        },
    )
    assert res.status_code == 200, res.text
    draft = _read_draft(created["output_dir"])
    assert draft["artifacts"]["fields"]["label"] == "Invoice fields"
    assert "invoice" in _steps(draft)["review"]["inputs"]
    mapping = client.get(f"/sessions/{sid}/bpmn/mapping").json()["mapping"]
    assert mapping["DataObjectRef_fields"]["data_object"]["label"] == "Invoice fields"

    refused = client.post(
        f"/sessions/{sid}/blueprint/operations",
        json={
            "base_version": res.json()["session"]["active_version"],
            "operations": [_unlink("fields", "extract", "output")],
        },
    )
    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "still_used"
    assert refused.json()["detail"]["field"] == "artifact_id"
