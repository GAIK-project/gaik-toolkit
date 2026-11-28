"""A step whose id starts like a generated task is kept as a step.

The generator draws a step as ``Activity_<step id>`` and adds tasks of its own:
"Submit to <target>" (``Activity_submit_<target>``) and "Generate PDF report"
(``Activity_generate_pdf``). The sync back from the canvas took every task with
one of those prefixes for a generated one, so an agent's step named
``submit_to_erp`` or ``generate_pdf_final`` was dropped from the blueprint by an
unchanged save. And a step ``submit_erp`` beside a target ``erp`` had the same
id as the generated sender, which overwrote it in the diagram.
"""

import xml.etree.ElementTree as ET

from solution_wizard.blueprint import Blueprint
from solution_wizard.bpmn_generator import _BpmnBuilder, generate_bpmn
from solution_wizard.bpmn_sync import sync_v2_blueprint_from_bpmn_xml
from solution_wizard.v2_adapter import v2_to_v1_dict

NS = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL"}


def _v2(*step_ids, targets=()):
    return {
        "name": "Invoices",
        "description": "d",
        "goal": "",
        "steps": [
            {
                "id": sid,
                "name": sid.replace("_", " ").capitalize(),
                "type": "ai",
                "component": "custom",
            }
            for sid in step_ids
        ],
        "integration_targets": list(targets),
    }


def _draw(v2):
    bp = Blueprint.model_validate(v2_to_v1_dict(v2, session_id="s"))
    builder = _BpmnBuilder(bp)
    xml = builder.build()
    assert xml == generate_bpmn(bp)
    return xml, builder.mapping


def _process(xml):
    return ET.fromstring(xml).find("bpmn:process", NS)


def test_an_unchanged_save_keeps_steps_named_like_generated_tasks():
    v2 = _v2("extract", "submit_to_erp", "generate_pdf_final")
    xml, _ = _draw(v2)

    out = sync_v2_blueprint_from_bpmn_xml(v2, xml)

    assert [s["id"] for s in out["steps"]] == ["extract", "submit_to_erp", "generate_pdf_final"]


def test_an_unchanged_save_does_not_import_a_generated_sender_as_a_step():
    v2 = _v2("extract", "approve", targets=["erp"])
    xml, mapping = _draw(v2)
    assert mapping["Activity_submit_erp"]["kind"] == "send_task"

    out = sync_v2_blueprint_from_bpmn_xml(v2, xml)

    assert [s["id"] for s in out["steps"]] == ["extract", "approve"]


def test_a_step_and_the_generated_sender_with_the_same_id_both_stay():
    """Step submit_erp and target erp: both would be Activity_submit_erp. The
    step keeps its id, the generated sender takes a free one and still writes
    the target's data store, and a save keeps the step and imports no sender."""
    v2 = _v2("extract", "submit_erp", targets=["erp"])
    xml, mapping = _draw(v2)
    proc = _process(xml)
    tasks = {e.get("id"): e for e in proc if e.tag.endswith("Task") or e.tag.endswith("}task")}

    assert mapping["Activity_submit_erp"]["kind"] != "send_task"
    # The step's own task, with its name (after the component code).
    assert tasks["Activity_submit_erp"].get("name").endswith("Submit erp")
    senders = [i for i, m in mapping.items() if m["kind"] == "send_task"]
    assert len(senders) == 1 and senders[0] != "Activity_submit_erp"
    (sender,) = senders
    assert sender in tasks
    writes = [
        a.findtext("bpmn:targetRef", namespaces=NS)
        for a in tasks[sender].findall("bpmn:dataOutputAssociation", NS)
    ]
    assert writes == ["DataStore_erp"]
    ids = [e.get("id") for e in ET.fromstring(xml).iter() if e.get("id")]
    assert len(ids) == len(set(ids))

    out = sync_v2_blueprint_from_bpmn_xml(v2, xml)

    assert [s["id"] for s in out["steps"]] == ["extract", "submit_erp"]


def test_the_data_store_is_placed_by_the_sender_that_writes_it():
    """The store sits under the generated sender, also when it took a free id."""
    v2 = _v2("extract", "submit_erp", targets=["erp"])
    xml, mapping = _draw(v2)
    (sender,) = [i for i, m in mapping.items() if m["kind"] == "send_task"]
    shapes = {
        s.get("bpmnElement"): s.find("{http://www.omg.org/spec/DD/20100524/DC}Bounds")
        for s in ET.fromstring(xml).iter("{http://www.omg.org/spec/BPMN/20100524/DI}BPMNShape")
    }
    task, store = shapes[sender], shapes["DataStore_erp"]
    task_cx = float(task.get("x")) + float(task.get("width")) / 2
    store_cx = float(store.get("x")) + float(store.get("width")) / 2

    assert abs(task_cx - store_cx) < float(task.get("width"))


def test_a_step_id_the_diagram_draws_cleaned_is_kept_as_it_was():
    """submit-to-erp is drawn as Activity_submit_to_erp: an unchanged save
    finds the step by the id it is drawn under, and keeps its id, component
    and description (not a new step "Added from BPMN canvas")."""
    v2 = _v2("extract", "submit-to-erp")
    v2["steps"][1]["description"] = "Send the approved invoice to the ERP"
    xml, _ = _draw(v2)
    assert 'id="Activity_submit_to_erp"' in xml

    out = sync_v2_blueprint_from_bpmn_xml(v2, xml)

    assert [s["id"] for s in out["steps"]] == ["extract", "submit-to-erp"]
    kept = out["steps"][1]
    assert kept["component"] == "custom"
    assert kept["description"] == "Send the approved invoice to the ERP"


def test_an_unchanged_save_keeps_each_step_record():
    v2 = _v2("extract", "submit_to_erp", "generate_pdf_final")
    for s in v2["steps"]:
        s["description"] = f"What {s['id']} does"
    xml, _ = _draw(v2)

    out = sync_v2_blueprint_from_bpmn_xml(v2, xml)

    for before, after in zip(v2["steps"], out["steps"]):
        assert (after["id"], after["component"], after["description"]) == (
            before["id"],
            before["component"],
            before["description"],
        )
