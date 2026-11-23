"""The diagram the user approves, the agent's own diagram and the cases agree.

Three things are built from one use case: the Workflow tab's diagram (generated
from the session blueprint and the agent's draft), the agent's workflow.bpmn
(generated from its draft), and the process the case screens route by. They
used to show different roles. These drafts mirror the shapes of the five
acceptance use cases (synthetic text): roles and a rework loop, an external
party, roles without participants, a send step without outputs, a PDF output.
"""

import re
import xml.etree.ElementTree as ET

import pytest
from wizard_api.services import artifact_sync, bpmn_service, case_service

pytestmark = pytest.mark.skipif(
    not bpmn_service.solution_wizard_available(),
    reason="solution_wizard package not installed",
)

if bpmn_service.solution_wizard_available():
    from solution_wizard.blueprint import Blueprint
    from solution_wizard.bpmn_generator import generate_bpmn

_BPMN = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"


def _draft(name, steps, *, participants=None, users=(), reviewers=(), process=None, outputs=()):
    """A V1 draft: steps are (id, type, component, inputs, outputs)."""
    artifacts = {}
    for sid, kind, _, _, produced in steps:
        for art in produced:
            if kind == "user_task":
                artifacts[art] = {"type": "file", "source": "user_upload", "optional": False}
            else:
                artifacts[art] = {
                    "type": "json",
                    "source": "generated",
                    "optional": False,
                    "produced_by": sid,
                }
    return {
        "use_case": {"id": name, "name": name.replace("_", " "), "description": "d", "domain": "d"},
        "business_spec": {"intended_users": list(users), "reviewers": list(reviewers)},
        "technical_spec": {"output_types": ["structured_json", *outputs]},
        "artifacts": artifacts,
        "workflow": {
            "steps": [
                {
                    "id": sid,
                    "name": sid.replace("_", " ").capitalize(),
                    "type": kind,
                    **({"component": comp} if comp else {}),
                    "inputs": list(ins),
                    "outputs": list(outs),
                    "depends_on": [steps[i - 1][0]] if i else [],
                }
                for i, (sid, kind, comp, ins, outs) in enumerate(steps)
            ]
        },
        "business_process": {"participants": participants or [], **(process or {})},
    }


def _roles(user, reviewer, system="AI system"):
    return [
        {"id": "user", "name": user, "default_lane_for": ["user_task"]},
        {"id": "reviewer", "name": reviewer, "default_lane_for": ["human_review"]},
        {"id": "system", "name": system, "kind": "system"},
    ]


DRAFTS = {
    "voice_ticket": _draft(
        "voice_ticket",
        [
            ("record", "user_task", None, [], ["voice_note"]),
            ("extract", "automated_task", "AudioToStructuredData", ["voice_note"], ["ticket"]),
            ("check", "automated_task", "LLMJudge", ["ticket"], ["check_report"]),
            ("send", "automated_task", None, ["ticket", "check_report"], ["review_package"]),
            ("review", "human_review", None, ["review_package"], ["approved_ticket"]),
        ],
        participants=_roles("Field worker", "Supervisor"),
        process={
            "exceptions": [
                {
                    "id": "back",
                    "name": "Returned",
                    "attached_to": "review",
                    "outcome": "loop_to:record",
                }
            ]
        },
        outputs=["pdf"],
    ),
    "order_record": _draft(
        "order_record",
        [
            ("upload", "user_task", None, [], ["order_pdf"]),
            ("extract", "automated_task", "VisionExtractor", ["order_pdf"], ["order_record"]),
            ("review", "human_review", None, ["order_record"], ["approved_record"]),
        ],
        participants=_roles("Order clerk", "Order reviewer"),
        process={
            "external_parties": [
                {"id": "customer", "name": "Customer", "sends": ["order_pdf"], "to_step": "upload"}
            ]
        },
    ),
    "document_answers": _draft(
        "document_answers",
        [
            ("provide", "user_task", None, [], ["documents", "questions"]),
            ("answer", "automated_task", "RAGWorkflow", ["documents", "questions"], ["answers"]),
        ],
        users=["employee", "manager"],
    ),
    "supplier_report": _draft(
        "supplier_report",
        [
            ("collect", "user_task", None, [], ["sources"]),
            ("curate", "automated_task", "KnowledgeCurator", ["sources"], ["facts"]),
            ("write", "automated_task", "ReportWriter", ["facts"], ["report_draft"]),
            ("send", "automated_task", None, ["report_draft"], []),
            ("review", "human_review", None, ["report_draft"], ["approved_report"]),
        ],
        participants=_roles("Analyst", "Manager"),
    ),
    "meeting_record": _draft(
        "meeting_record",
        [
            ("upload", "user_task", None, [], ["recording", "agenda"]),
            ("transcribe", "automated_task", "Transcriber", ["recording"], ["transcript"]),
            ("extract", "automated_task", "DataExtractor", ["transcript", "agenda"], ["record"]),
            ("judge", "automated_task", "LLMJudge", ["record", "transcript"], ["judgement"]),
            ("send", "automated_task", None, ["record", "judgement"], []),
            ("review", "human_review", None, ["record", "judgement"], ["approved_record"]),
        ],
        participants=_roles("Coordinator", "Project manager"),
        process={
            "exceptions": [
                {
                    "id": "back",
                    "name": "Returned",
                    "attached_to": "review",
                    "outcome": "loop_to:extract",
                }
            ]
        },
    ),
}


def _shown(draft):
    """The Workflow tab's diagram: from the session blueprint and the draft."""
    v2 = artifact_sync.blueprint_from_draft(draft).model_dump()
    return bpmn_service.generate_bpmn_xml(v2, session_id="s", agent_draft=draft)


def _agents(draft):
    """The agent's workflow.bpmn: the same generator, run on its draft."""
    return generate_bpmn(Blueprint.model_validate(draft))


def _signature(process):
    lanes = {lane["id"]: lane["name"] for lane in process["lanes"]}
    return sorted(
        (n["kind"], n["name"], tuple(n["inputs"]), tuple(n["outputs"]), lanes.get(n["lane"]))
        for n in process["nodes"]
        if n["kind"].endswith("Task")
    )


@pytest.mark.parametrize("name", DRAFTS)
def test_the_shown_diagram_has_the_agents_roles_tasks_and_data(name) -> None:
    shown = case_service.process_from_bpmn(_shown(DRAFTS[name]))
    agents = case_service.process_from_bpmn(_agents(DRAFTS[name]))

    assert _signature(shown) == _signature(agents)
    assert [lane["name"] for lane in shown["lanes"] if lane["human"]] == [
        lane["name"] for lane in agents["lanes"] if lane["human"]
    ]
    assert case_service.reviewer_task(shown) == case_service.reviewer_task(agents)
    assert case_service.process_problem(shown) is None


def _data_objects(xml):
    return sorted(el.get("name") for el in ET.fromstring(xml).iter(f"{_BPMN}dataObjectReference"))


@pytest.mark.parametrize("name", DRAFTS)
def test_the_shown_diagram_has_the_agents_data_objects_and_no_others(name) -> None:
    # Unlinked data objects do not show in the tasks' inputs and outputs.
    assert _data_objects(_shown(DRAFTS[name])) == _data_objects(_agents(DRAFTS[name]))


@pytest.mark.parametrize("name", DRAFTS)
def test_the_shown_diagram_is_well_formed(name) -> None:
    proc = ET.fromstring(_shown(DRAFTS[name])).find(f"{_BPMN}process")
    nodes = {
        el.get("id")
        for kind in (
            "startEvent",
            "endEvent",
            "userTask",
            "serviceTask",
            "sendTask",
            "manualTask",
            "exclusiveGateway",
            "parallelGateway",
            "intermediateCatchEvent",
        )
        for el in proc.iter(f"{_BPMN}{kind}")
    }
    assert len(list(proc.iter(f"{_BPMN}startEvent"))) == 1
    for flow in proc.iter(f"{_BPMN}sequenceFlow"):
        assert flow.get("sourceRef") in nodes and flow.get("targetRef") in nodes
    in_lanes = [
        ref.text for lane in proc.iter(f"{_BPMN}lane") for ref in lane.iter(f"{_BPMN}flowNodeRef")
    ]
    tasks = {
        el.get("id")
        for kind in ("userTask", "serviceTask", "sendTask", "manualTask")
        for el in proc.iter(f"{_BPMN}{kind}")
    }
    for task in tasks:
        assert in_lanes.count(task) == 1, f"{task} is in {in_lanes.count(task)} lanes"


def test_the_human_roles_are_the_drafts_not_stock_ones() -> None:
    for draft in DRAFTS.values():
        lanes = re.findall(r'<bpmn:lane id="[^"]*" name="([^"]*)"', _shown(draft))
        assert "Business User" not in lanes and "Reviewer" not in lanes
