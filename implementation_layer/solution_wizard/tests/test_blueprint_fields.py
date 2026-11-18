"""Blueprint fields the BPMN diagram carries back into the JSON: a step's
description and lane (``performed_by``) and a data object's label, plus
``derived_participants`` and validator rule 16."""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint, Participant
from solution_wizard.bpmn_generator import derived_participants, generate_bpmn
from solution_wizard.validator import validate

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
EXAMPLES = sorted(p.name for p in EXAMPLES_DIR.glob("*_blueprint.json"))

NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    "omgdc": "http://www.omg.org/spec/DD/20100524/DC",
}


def _example(name: str = "document_extraction_blueprint.json") -> Blueprint:
    return Blueprint.from_file(EXAMPLES_DIR / name)


def _step(bp: Blueprint, step_id: str):
    return next(s for s in bp.workflow.steps if s.id == step_id)


def _bounds(root, element_id: str) -> tuple:
    shape = root.find(f".//bpmndi:BPMNShape[@bpmnElement='{element_id}']", NS)
    b = shape.find("omgdc:Bounds", NS)
    return tuple(float(b.get(k)) for k in ("x", "y", "width", "height"))


def _lane_names(xml: str) -> list:
    root = ET.fromstring(xml)
    return [lane.get("name") for lane in root.findall(".//bpmn:lane", NS)]


def test_new_fields_default_to_empty():
    bp = _example()
    step = bp.workflow.steps[0]
    assert step.description == "" and step.performed_by == ""
    assert next(iter(bp.artifacts.values())).label == ""


@pytest.mark.parametrize("include_data_objects", [True, False])
def test_a_step_with_performed_by_is_drawn_in_that_lane(include_data_objects):
    bp = _example()
    bp.business_process.participants = [
        Participant(id="clerk", name="Clerk", default_lane_for=["user_task"]),
        Participant(id="ops", name="Operations", kind="human_role"),
    ]
    _step(bp, "extract_po_fields").performed_by = "ops"
    root = ET.fromstring(generate_bpmn(bp, include_data_objects=include_data_objects))

    lane = root.find(".//bpmn:lane[@name='Operations']", NS)
    assert lane is not None
    refs = [r.text for r in lane.findall("bpmn:flowNodeRef", NS)]
    assert "Activity_extract_po_fields" in refs
    lx, ly, lw, lh = _bounds(root, lane.get("id"))
    x, y, w, h = _bounds(root, "Activity_extract_po_fields")
    assert lx <= x and x + w <= lx + lw
    assert ly <= y and y + h <= ly + lh


def test_an_unknown_performer_falls_back_to_the_category_lane():
    bp = _example()
    _step(bp, "extract_po_fields").performed_by = "nobody"
    root = ET.fromstring(generate_bpmn(bp))
    lane = root.find(".//bpmn:lane[@name='GenAI']", NS)
    assert "Activity_extract_po_fields" in [r.text for r in lane.findall("bpmn:flowNodeRef", NS)]


def test_a_derived_lane_id_places_the_step_when_participants_are_empty():
    bp = _example()
    _step(bp, "upload_po").performed_by = "system"
    root = ET.fromstring(generate_bpmn(bp))
    lane = root.find(".//bpmn:lane[@name='GenAI']", NS)
    assert "Activity_upload_po" in [r.text for r in lane.findall("bpmn:flowNodeRef", NS)]


def test_an_artifact_label_names_its_data_object():
    bp = _example()
    bp.artifacts["source_pdf"].label = "Signed contract"
    root = ET.fromstring(generate_bpmn(bp))
    ref = root.find(".//bpmn:dataObjectReference[@id='DataObjectRef_source_pdf']", NS)
    assert ref.get("name") == "Signed contract"


@pytest.mark.parametrize("include_data_objects", [True, False])
def test_a_step_description_becomes_documentation(include_data_objects):
    bp = _example()
    _step(bp, "extract_po_fields").description = "Reads the PO & fills <fields>."
    root = ET.fromstring(generate_bpmn(bp, include_data_objects=include_data_objects))
    task = root.find(".//bpmn:serviceTask[@id='Activity_extract_po_fields']", NS)
    doc = task.find("bpmn:documentation", NS)
    assert doc is not None and doc.text == "Reads the PO & fills <fields>."
    other = root.find(".//bpmn:userTask[@id='Activity_upload_po']", NS)
    assert other.find("bpmn:documentation", NS) is None


def _with_review(bp: Blueprint) -> Blueprint:
    data = bp.model_dump(mode="json")
    data["workflow"]["steps"].append(
        {
            "id": "review_po",
            "name": "Review PO",
            "type": "human_review",
            "inputs": ["purchase_order_json"],
            "depends_on": ["extract_po_fields"],
        }
    )
    return Blueprint.model_validate(data)


@pytest.mark.parametrize("name", EXAMPLES + ["with_review"])
def test_derived_participants_redraw_the_same_lanes(name):
    bp = _with_review(_example()) if name == "with_review" else _example(name)
    before = _lane_names(generate_bpmn(bp))
    derived = derived_participants(bp)
    assert [p.name for p in derived] == before

    bp.business_process.participants = derived
    assert _lane_names(generate_bpmn(bp)) == before


def test_derived_participants_ids_and_lane_roles():
    bp = _with_review(_example())
    by_id = {p.id: p for p in derived_participants(bp)}
    assert set(by_id) == {"users", "system", "reviewers"}
    assert by_id["system"].kind == "system" and by_id["system"].name == "GenAI"
    assert by_id["system"].default_lane_for == ["automated_task"]
    assert by_id["reviewers"].default_lane_for == ["human_review"]
    assert by_id["reviewers"].name == "Procurement Manager"
    assert by_id["users"].default_lane_for == ["user_task"]
    assert by_id["users"].name == "Procurement Staff"
    # Only lanes the generator draws: this example has no review step.
    assert "reviewers" not in {p.id for p in derived_participants(_example())}


def test_rule_16_refuses_an_unknown_performer():
    bp = _example()
    bp.business_process.participants = [Participant(id="ops", name="Operations")]
    _step(bp, "extract_po_fields").performed_by = "nobody"
    result = validate(bp)
    assert not result.ok
    assert [e.step_id for e in result.errors if e.rule == 16] == ["extract_po_fields"]

    _step(bp, "extract_po_fields").performed_by = "ops"
    assert not [e for e in validate(bp).errors if e.rule == 16]


def test_rule_16_accepts_a_derived_lane_id_only_without_participants():
    bp = _example()
    _step(bp, "extract_po_fields").performed_by = "system"
    assert not [e for e in validate(bp).errors if e.rule == 16]
    _step(bp, "extract_po_fields").performed_by = "nobody"
    assert [e.rule for e in validate(bp).errors] == [16]


@pytest.mark.parametrize("name", EXAMPLES)
def test_existing_examples_still_validate(name):
    result = validate(_example(name))
    assert result.ok, result.summary()
