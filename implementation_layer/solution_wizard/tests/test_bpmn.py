"""Tests for the BPMN 2.0 visual-blueprint generator (V2 enhancement).

Verifies: well-formed XML, correct BPMN element types, full DI completeness
(a shape for every flow node, an edge for every flow -- guards against
blank-canvas renders), stable ids + bpmn_mapping coverage, the enrichment
conventions (parallel fork/join, approval gateway + rework loop, integration
data store + send task, governance annotations), and backward-compatibility
with the existing example blueprints (no business_process section).
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint
from solution_wizard.bpmn_generator import generate_bpmn, write_bpmn

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"

NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    "omgdc": "http://www.omg.org/spec/DD/20100524/DC",
    "omgdi": "http://www.omg.org/spec/DD/20100524/DI",
}

FLOW_NODE_TAGS = {
    "startEvent",
    "endEvent",
    "task",
    "userTask",
    "serviceTask",
    "sendTask",
    "manualTask",
    "exclusiveGateway",
    "parallelGateway",
}


def _local(elem) -> str:
    return elem.tag.split("}")[-1]


def _hospital_blueprint() -> Blueprint:
    """audio || pdf -> merge -> extract -> validate(judge) -> human_review,
    with an integration target and a business_process section (lanes + an
    external party that hands the referral in via a message flow)."""
    data = {
        "blueprint_version": "1.0",
        "use_case": {
            "id": "hosp",
            "name": "Hospital Admissions",
            "description": "x",
            "domain": "healthcare",
        },
        "business_spec": {
            "intended_users": ["doctor", "administrative_staff"],
            "reviewers": ["supervisor"],
        },
        "technical_spec": {
            "input_types": ["audio", "pdf"],
            "output_types": ["structured_json"],
            "language": "en",
            "human_review_required": True,
            "integration_targets": ["patient_management_system"],
        },
        "target_output_spec": {
            "schema_name": "Rec",
            "fields": ["full_name", "allergies"],
            "required_fields": [],
        },
        "components": {
            "selected_modules": [],
            "selected_building_blocks": [
                "Transcriber",
                "PyMuPDFParser",
                "DataExtractor",
                "LLMJudge",
            ],
            "custom_components": [],
        },
        "artifacts": {
            "voice_note_audio": {"type": "audio", "source": "user_upload", "optional": False},
            "referral_pdf": {"type": "pdf", "source": "user_upload", "optional": True},
            "raw_transcript": {
                "type": "transcript",
                "source": "generated",
                "optional": False,
                "produced_by": "transcribe_audio",
            },
            "parsed_referral_text": {
                "type": "parsed_text",
                "source": "generated",
                "optional": True,
                "produced_by": "parse_referral_pdf",
            },
            "combined_clinical_text": {
                "type": "text",
                "source": "generated",
                "optional": False,
                "produced_by": "merge_sources",
            },
            "patient_record_json": {
                "type": "structured_json",
                "source": "generated",
                "optional": False,
                "final_output": True,
                "produced_by": "extract_clinical_fields",
                "schema_ref": "schemas/output_schema.py",
            },
            "validation_report": {
                "type": "validation_report",
                "source": "generated",
                "optional": False,
                "produced_by": "validate_record",
            },
            "approved_patient_record": {
                "type": "structured_json",
                "source": "generated",
                "optional": False,
                "final_output": True,
                "produced_by": "human_review",
            },
        },
        "workflow": {
            "steps": [
                {
                    "id": "upload_inputs",
                    "name": "Upload inputs",
                    "type": "user_task",
                    "inputs": [],
                    "outputs": ["voice_note_audio", "referral_pdf"],
                },
                {
                    "id": "transcribe_audio",
                    "name": "Transcribe",
                    "type": "automated_task",
                    "component": "Transcriber",
                    "inputs": ["voice_note_audio"],
                    "outputs": ["raw_transcript"],
                    "depends_on": ["upload_inputs"],
                },
                {
                    "id": "parse_referral_pdf",
                    "name": "Parse referral",
                    "type": "automated_task",
                    "component": "PyMuPDFParser",
                    "inputs": ["referral_pdf"],
                    "outputs": ["parsed_referral_text"],
                    "depends_on": ["upload_inputs"],
                },
                {
                    "id": "merge_sources",
                    "name": "Merge",
                    "type": "automated_task",
                    "component": "custom",
                    "inputs": ["raw_transcript", "parsed_referral_text"],
                    "outputs": ["combined_clinical_text"],
                    "depends_on": ["transcribe_audio", "parse_referral_pdf"],
                },
                {
                    "id": "extract_clinical_fields",
                    "name": "Extract",
                    "type": "automated_task",
                    "component": "DataExtractor",
                    "inputs": ["combined_clinical_text"],
                    "outputs": ["patient_record_json"],
                    "depends_on": ["merge_sources"],
                },
                {
                    "id": "validate_record",
                    "name": "Validate",
                    "type": "automated_task",
                    "component": "LLMJudge",
                    "inputs": ["patient_record_json", "combined_clinical_text"],
                    "outputs": ["validation_report"],
                    "depends_on": ["extract_clinical_fields"],
                },
                {
                    "id": "human_review",
                    "name": "Supervisor review",
                    "type": "human_review",
                    "inputs": ["patient_record_json", "validation_report"],
                    "outputs": ["approved_patient_record"],
                    "depends_on": ["validate_record"],
                },
            ]
        },
        "governance": {
            "data_handling": {
                "contains_personal_data": "yes",
                "output_sensitivity": "high",
                "audit_log_required": True,
            }
        },
        "business_process": {
            "participants": [
                {
                    "id": "doctor",
                    "name": "Doctor",
                    "kind": "human_role",
                    "default_lane_for": ["user_task"],
                },
                {
                    "id": "supervisor",
                    "name": "Supervisor",
                    "kind": "human_role",
                    "default_lane_for": ["human_review"],
                },
            ],
            "external_parties": [
                {
                    "id": "external_clinic",
                    "name": "External Clinic",
                    "sends": ["referral_pdf"],
                    "to_step": "upload_inputs",
                },
            ],
        },
    }
    return Blueprint.model_validate(data)


def _simple_blueprint() -> Blueprint:
    """Single automated step, no human review, no integration -- to assert the
    absence of approval gateway / rework loop."""
    data = {
        "blueprint_version": "1.0",
        "use_case": {"id": "simp", "name": "Simple", "description": "x", "domain": "test"},
        "technical_spec": {
            "input_types": ["pdf"],
            "output_types": ["structured_json"],
            "language": "en",
        },
        "target_output_spec": {"required_fields": ["a"]},
        "components": {
            "selected_modules": [],
            "selected_building_blocks": ["DataExtractor"],
            "custom_components": [],
        },
        "artifacts": {
            "src": {"type": "pdf", "source": "user_upload", "optional": False},
            "out": {
                "type": "structured_json",
                "source": "generated",
                "optional": False,
                "final_output": True,
                "produced_by": "extract",
            },
        },
        "workflow": {
            "steps": [
                {
                    "id": "upload",
                    "name": "Upload",
                    "type": "user_task",
                    "inputs": [],
                    "outputs": ["src"],
                },
                {
                    "id": "extract",
                    "name": "Extract",
                    "type": "automated_task",
                    "component": "DataExtractor",
                    "inputs": ["src"],
                    "outputs": ["out"],
                    "depends_on": ["upload"],
                },
            ]
        },
    }
    return Blueprint.model_validate(data)


def _parse(blueprint: Blueprint):
    xml = generate_bpmn(blueprint)
    return xml, ET.fromstring(xml)


# ---------------------------------------------------------------------------
# Well-formedness
# ---------------------------------------------------------------------------


def test_bpmn_is_well_formed():
    xml, root = _parse(_hospital_blueprint())
    assert _local(root) == "definitions"


def test_empty_workflow_still_well_formed():
    bp = _hospital_blueprint()
    bp.workflow.steps = []
    xml = generate_bpmn(bp)
    ET.fromstring(xml)  # must not raise


# ---------------------------------------------------------------------------
# Element types present
# ---------------------------------------------------------------------------


def test_contains_expected_element_types():
    xml, root = _parse(_hospital_blueprint())
    proc = root.find("bpmn:process", NS)
    present = {_local(e) for e in proc}
    for expected in {
        "laneSet",
        "startEvent",
        "endEvent",
        "userTask",
        "serviceTask",
        "sendTask",
        "parallelGateway",
        "exclusiveGateway",
        "dataObjectReference",
        "dataStoreReference",
        "textAnnotation",
        "sequenceFlow",
    }:
        assert expected in present, f"missing {expected}"
    # message flow lives in the collaboration
    collab = root.find("bpmn:collaboration", NS)
    assert collab.find("bpmn:messageFlow", NS) is not None


def test_two_parallel_gateways_fork_and_join():
    xml, root = _parse(_hospital_blueprint())
    proc = root.find("bpmn:process", NS)
    pgs = [e for e in proc if _local(e) == "parallelGateway"]
    assert len(pgs) == 2  # one fork (after upload), one join (before merge)


def test_external_party_pool_and_message_flow():
    xml, root = _parse(_hospital_blueprint())
    collab = root.find("bpmn:collaboration", NS)
    participants = [p.get("name") for p in collab.findall("bpmn:participant", NS)]
    assert "External Clinic" in participants
    mfs = collab.findall("bpmn:messageFlow", NS)
    assert len(mfs) >= 1


def test_lanes_use_business_process_participants():
    xml, root = _parse(_hospital_blueprint())
    proc = root.find("bpmn:process", NS)
    lanes = {l.get("name") for l in proc.findall(".//bpmn:lane", NS)}
    assert "Doctor" in lanes
    assert "Supervisor" in lanes
    assert "GAIK AI System" in lanes


# ---------------------------------------------------------------------------
# DI completeness (guards against blank-canvas renders)
# ---------------------------------------------------------------------------


def test_every_flow_node_has_a_shape_with_nonzero_bounds():
    xml, root = _parse(_hospital_blueprint())
    proc = root.find("bpmn:process", NS)
    flow_nodes = [e.get("id") for e in proc if _local(e) in FLOW_NODE_TAGS]
    plane = root.find(".//bpmndi:BPMNPlane", NS)
    shapes = {s.get("bpmnElement"): s for s in plane.findall("bpmndi:BPMNShape", NS)}
    for nid in flow_nodes:
        assert nid in shapes, f"no shape for {nid}"
        bounds = shapes[nid].find("omgdc:Bounds", NS)
        assert bounds is not None
        assert int(bounds.get("width")) > 0 and int(bounds.get("height")) > 0


def test_every_sequence_flow_has_an_edge():
    xml, root = _parse(_hospital_blueprint())
    proc = root.find("bpmn:process", NS)
    flows = [e.get("id") for e in proc.findall("bpmn:sequenceFlow", NS)]
    plane = root.find(".//bpmndi:BPMNPlane", NS)
    edges = {e.get("bpmnElement") for e in plane.findall("bpmndi:BPMNEdge", NS)}
    for fid in flows:
        assert fid in edges, f"no edge for {fid}"


def test_data_objects_and_store_have_shapes():
    xml, root = _parse(_hospital_blueprint())
    proc = root.find("bpmn:process", NS)
    plane = root.find(".//bpmndi:BPMNPlane", NS)
    shapes = {s.get("bpmnElement") for s in plane.findall("bpmndi:BPMNShape", NS)}
    for e in proc:
        if _local(e) in ("dataObjectReference", "dataStoreReference"):
            assert e.get("id") in shapes


# ---------------------------------------------------------------------------
# Stable ids + mapping
# ---------------------------------------------------------------------------


def test_activity_ids_trace_to_steps():
    bp = _hospital_blueprint()
    xml, root = _parse(bp)
    step_ids = {s.id for s in bp.workflow.steps}
    proc = root.find("bpmn:process", NS)
    for e in proc:
        nid = e.get("id") or ""
        if nid.startswith("Activity_") and not nid.startswith("Activity_submit_"):
            assert nid[len("Activity_") :] in step_ids


def test_bpmn_mapping_written_and_covers_flow_nodes():
    bp = _hospital_blueprint()
    xml, root = _parse(bp)
    mapping = bp.visualizations["bpmn_mapping"]
    assert mapping  # non-empty
    proc = root.find("bpmn:process", NS)
    flow_nodes = [e.get("id") for e in proc if _local(e) in FLOW_NODE_TAGS]
    for nid in flow_nodes:
        assert nid in mapping, f"{nid} missing from bpmn_mapping"
    # each mapping entry resolves to a kind + blueprint_path
    for eid, info in mapping.items():
        assert "kind" in info and "blueprint_path" in info


# ---------------------------------------------------------------------------
# Enrichment conventions
# ---------------------------------------------------------------------------


def test_approval_gateway_present_with_human_review():
    """The 'Approved?' gateway is generated from the human_review step.
    By default (no exception defined), the 'No' path goes to a 'Rejected' end
    event — NOT a rework loop to an AI step, which would be semantically wrong."""
    xml, root = _parse(_hospital_blueprint())
    proc = root.find("bpmn:process", NS)
    gateways = [e for e in proc if _local(e) == "exclusiveGateway"]
    assert any(g.get("name") == "Approved?" for g in gateways)
    # Default rejection: a 'Rejected' end event connected from the approval gateway.
    end_events = {e.get("id") for e in proc if _local(e) == "endEvent"}
    no_flows = [
        f
        for f in proc.findall("bpmn:sequenceFlow", NS)
        if f.get("sourceRef", "").startswith("Gateway_approve_")
        and f.get("name", "").lower().startswith("no")
    ]
    assert no_flows, "expected a 'No' path from the approval gateway"
    assert no_flows[0].get("targetRef") in end_events, (
        "default rejection should go to an end event, not a rework loop to an AI step"
    )
    # Confirm the 'No' target is NOT one of the AI automated tasks.
    ai_tasks = {e.get("id") for e in proc if _local(e) in ("serviceTask", "sendTask")}
    assert no_flows[0].get("targetRef") not in ai_tasks, (
        "rejection must NOT loop back to an AI extraction step by default"
    )


def test_integration_target_makes_send_task_and_data_store():
    xml, root = _parse(_hospital_blueprint())
    proc = root.find("bpmn:process", NS)
    send_tasks = [e for e in proc if _local(e) == "sendTask"]
    stores = [e for e in proc if _local(e) == "dataStoreReference"]
    assert send_tasks and stores
    # send task is on the approved path to the end event
    end_in = [
        f.get("sourceRef")
        for f in proc.findall("bpmn:sequenceFlow", NS)
        if f.get("targetRef") == "EndEvent_success"
    ]
    assert any(s.startswith("Activity_submit_") for s in end_in)


def test_no_approval_gateway_without_human_review():
    xml, root = _parse(_simple_blueprint())
    proc = root.find("bpmn:process", NS)
    gateways = [e for e in proc if _local(e) == "exclusiveGateway"]
    assert not any(g.get("name") == "Approved?" for g in gateways)


def test_governance_annotations_present():
    xml, root = _parse(_hospital_blueprint())
    proc = root.find("bpmn:process", NS)
    texts = [e.find("bpmn:text", NS).text for e in proc if _local(e) == "textAnnotation"]
    joined = " ".join(t or "" for t in texts)
    assert "personal data" in joined.lower()
    assert "audit log" in joined.lower()


# ---------------------------------------------------------------------------
# Backward compatibility with existing example blueprints
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "incident_reporting_blueprint.json",
        "purchase_order_blueprint.json",
        "rag_workflow_blueprint.json",
        "document_extraction_blueprint.json",
    ],
)
def test_example_blueprints_generate_valid_bpmn(name):
    path = EXAMPLES_DIR / name
    if not path.exists():
        pytest.skip(f"{name} not present")
    bp = Blueprint.from_file(path)
    xml = generate_bpmn(bp)
    root = ET.fromstring(xml)  # well-formed
    # DI completeness still holds (enrichment-only, no business_process)
    proc = root.find("bpmn:process", NS)
    plane = root.find(".//bpmndi:BPMNPlane", NS)
    flow_nodes = [e.get("id") for e in proc if _local(e) in FLOW_NODE_TAGS]
    shapes = {s.get("bpmnElement") for s in plane.findall("bpmndi:BPMNShape", NS)}
    for nid in flow_nodes:
        assert nid in shapes


def _pdf_blueprint(has_pdf: bool) -> Blueprint:
    """Hospital blueprint with/without pdf in output_types."""
    data = {
        "blueprint_version": "1.0",
        "use_case": {"id": "pdf_uc", "name": "PDF Use Case", "description": "x", "domain": "test"},
        "technical_spec": {
            "input_types": ["audio"],
            "language": "en",
            "output_types": ["structured_json", "pdf"] if has_pdf else ["structured_json"],
        },
        "target_output_spec": {"required_fields": ["a"]},
        "components": {
            "selected_modules": [],
            "selected_building_blocks": ["Transcriber", "DataExtractor"],
            "custom_components": [],
        },
        "artifacts": {
            "src": {"type": "audio", "source": "user_upload", "optional": False},
            "out": {
                "type": "structured_json",
                "source": "generated",
                "optional": False,
                "final_output": True,
                "produced_by": "extract",
            },
        },
        "workflow": {
            "steps": [
                {
                    "id": "transcribe",
                    "name": "Transcribe",
                    "type": "automated_task",
                    "component": "Transcriber",
                    "inputs": ["src"],
                    "outputs": [],
                    "depends_on": [],
                },
                {
                    "id": "extract",
                    "name": "Extract",
                    "type": "automated_task",
                    "component": "DataExtractor",
                    "inputs": [],
                    "outputs": ["out"],
                    "depends_on": ["transcribe"],
                },
                {
                    "id": "review",
                    "name": "Review",
                    "type": "human_review",
                    "inputs": ["out"],
                    "outputs": [],
                    "depends_on": ["extract"],
                },
            ]
        },
    }
    return Blueprint.model_validate(data)


def test_pdf_generation_task_injected_when_output_types_includes_pdf():
    """Fix A: when output_types includes 'pdf', a 'Generate PDF report' service
    task must appear in the AI lane on the *approved path* — after the approval
    gateway (the reviewer approves the content before the report is rendered)."""
    bp = _pdf_blueprint(has_pdf=True)
    xml, root = _parse(bp)
    proc = root.find("bpmn:process", NS)
    service_tasks = [e for e in proc if _local(e) == "serviceTask"]
    pdf_task = next((t for t in service_tasks if "pdf" in (t.get("name") or "").lower()), None)
    assert pdf_task is not None, (
        "expected a 'Generate PDF report' service task when output_types includes 'pdf'"
    )
    # Full edge list (a gateway has several outgoing flows — do not collapse).
    edges = [
        (f.get("sourceRef"), f.get("targetRef")) for f in proc.findall("bpmn:sequenceFlow", NS)
    ]
    pdf_id = pdf_task.get("id")
    # The PDF task is reached FROM the approval gateway's approved path.
    feeders = [s for s, t in edges if t == pdf_id]
    assert feeders, "PDF task must have an incoming flow"
    assert any(s.startswith("Gateway_approve_") for s in feeders), (
        "PDF generation should be reached from the approval gateway's approved path"
    )
    # And the PDF task leads onward to the end event (it is on the success path).
    assert any(s == pdf_id and t == "EndEvent_success" for s, t in edges), (
        "PDF generation should lead to the success end event"
    )


def test_pdf_generation_precedes_integration_send_task():
    """Fix A ordering: when a use case has BOTH pdf output and an integration
    target, the report must be generated BEFORE it is submitted, i.e. the PDF
    service task flows into the Send Task, not the other way around."""
    data = {
        "blueprint_version": "1.0",
        "use_case": {"id": "uc", "name": "U", "description": "x", "domain": "t"},
        "technical_spec": {
            "input_types": ["audio"],
            "output_types": ["structured_json", "pdf"],
            "language": "en",
            "integration_targets": ["erp_system"],
        },
        "target_output_spec": {"required_fields": ["a"]},
        "components": {
            "selected_modules": [],
            "selected_building_blocks": ["Extractor"],
            "custom_components": [],
        },
        "artifacts": {
            "src": {"type": "audio", "source": "user_upload", "optional": False},
            "out": {
                "type": "structured_json",
                "source": "generated",
                "optional": False,
                "final_output": True,
                "produced_by": "extract",
            },
        },
        "workflow": {
            "steps": [
                {
                    "id": "extract",
                    "name": "Extract",
                    "type": "automated_task",
                    "component": "Extractor",
                    "inputs": ["src"],
                    "outputs": ["out"],
                    "depends_on": [],
                },
            ]
        },
    }
    bp = Blueprint.model_validate(data)
    xml, root = _parse(bp)
    proc = root.find("bpmn:process", NS)
    flows = {f.get("sourceRef"): f.get("targetRef") for f in proc.findall("bpmn:sequenceFlow", NS)}
    pdf_id = next(
        e.get("id")
        for e in proc
        if _local(e) == "serviceTask" and "pdf" in (e.get("name") or "").lower()
    )
    send_id = next(e.get("id") for e in proc if _local(e) == "sendTask")
    assert flows.get(pdf_id) == send_id, (
        "PDF generation must flow into the Send Task (generate, then submit)"
    )


def test_pdf_generation_task_not_injected_without_pdf_in_output_types():
    """Fix A: no PDF generation task when output_types does not include 'pdf'."""
    bp = _pdf_blueprint(has_pdf=False)
    xml, root = _parse(bp)
    proc = root.find("bpmn:process", NS)
    service_tasks = [e for e in proc if _local(e) == "serviceTask"]
    pdf_task = next((t for t in service_tasks if "pdf" in (t.get("name") or "").lower()), None)
    assert pdf_task is None, "no PDF task should appear when output_types does not include 'pdf'"


def _blueprint_with_loop_to_exception() -> Blueprint:
    """Blueprint where rejection loops back to the employee (user_task) step."""
    data = {
        "blueprint_version": "1.0",
        "use_case": {"id": "rework_uc", "name": "Rework UC", "description": "x", "domain": "test"},
        "technical_spec": {
            "input_types": ["audio"],
            "output_types": ["structured_json"],
            "language": "en",
        },
        "target_output_spec": {"required_fields": ["a"]},
        "components": {
            "selected_modules": [],
            "selected_building_blocks": ["Transcriber"],
            "custom_components": [],
        },
        "artifacts": {
            "src": {"type": "audio", "source": "user_upload", "optional": False},
            "out": {
                "type": "structured_json",
                "source": "generated",
                "optional": False,
                "final_output": True,
                "produced_by": "extract",
            },
        },
        "workflow": {
            "steps": [
                {
                    "id": "upload",
                    "name": "Upload",
                    "type": "user_task",
                    "inputs": [],
                    "outputs": ["src"],
                },
                {
                    "id": "extract",
                    "name": "Extract",
                    "type": "automated_task",
                    "component": "Transcriber",
                    "inputs": ["src"],
                    "outputs": ["out"],
                    "depends_on": ["upload"],
                },
                {
                    "id": "review",
                    "name": "Review",
                    "type": "human_review",
                    "inputs": ["out"],
                    "outputs": [],
                    "depends_on": ["extract"],
                },
            ]
        },
        "business_process": {
            "exceptions": [
                {
                    "id": "rejection_rework",
                    "name": "Employee corrects and resubmits",
                    "attached_to": "review",
                    "condition": "No (rework)",
                    "outcome": "loop_to:upload",
                },
            ],
        },
    }
    return Blueprint.model_validate(data)


def test_explicit_loop_to_exception_routes_to_named_step():
    """Fix B: when an exception with outcome='loop_to:<step>' is defined, the
    'No' path loops to that specific step (e.g. the employee upload step)."""
    bp = _blueprint_with_loop_to_exception()
    xml, root = _parse(bp)
    proc = root.find("bpmn:process", NS)
    no_flows = [
        f
        for f in proc.findall("bpmn:sequenceFlow", NS)
        if f.get("sourceRef", "").startswith("Gateway_approve_")
        and "rework" in (f.get("name") or "").lower()
    ]
    assert no_flows, "expected a rework flow from the approval gateway"
    assert no_flows[0].get("targetRef") == "Activity_upload", (
        "rework loop should go to the 'upload' user_task, not the AI extractor"
    )


def test_write_bpmn_creates_file(tmp_path):
    bp = _hospital_blueprint()
    path = write_bpmn(bp, tmp_path)
    assert path.name == "workflow.bpmn"
    assert path.exists()
    ET.fromstring(path.read_text(encoding="utf-8"))
