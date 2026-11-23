"""The diagram shows the roles the user agreed with the agent, not stock lanes.

Customer feedback (October 2026): the BPMN's lanes were not the use case's roles.
The V2 blueprint keeps the steps but not who does them, so the V2 → V1 adapter
filled in "Business User", "Reviewer" and "GenAI" for every session.
"""

import json
import os
import re

import pytest
from helpers import requires_postgres
from wizard_api.services import artifact_sync, bpmn_service

pytestmark = pytest.mark.skipif(
    not bpmn_service.solution_wizard_available(),
    reason="solution_wizard package not installed",
)

V2 = {
    "name": "Invoices",
    "description": "Test",
    "goal": "Book invoices",
    "steps": [
        {"id": "upload", "name": "Upload invoice", "type": "io"},
        {"id": "extract", "name": "Extract fields", "type": "ai", "component": "extractor"},
        {"id": "forward", "name": "Forward to approver", "type": "io"},
        {"id": "approve", "name": "Approve invoice", "type": "human_review"},
    ],
}

DRAFT = {
    "business_spec": {"intended_users": ["clerk"], "reviewers": ["controller"]},
    "workflow": {
        "steps": [
            {"id": "upload", "type": "user_task"},
            {"id": "extract", "type": "automated_task", "component": "extractor"},
            {"id": "forward", "type": "automated_task"},
            {"id": "approve", "type": "human_review"},
        ]
    },
    "business_process": {
        "participants": [
            {"id": "clerk", "name": "Accounts clerk", "default_lane_for": ["user_task"]},
            {"id": "controller", "name": "Controller", "default_lane_for": ["human_review"]},
            {"id": "system", "name": "Booking system", "kind": "system"},
        ],
        "exceptions": [
            {
                "id": "returned",
                "name": "Invoice returned",
                "attached_to": "approve",
                "outcome": "loop_to:upload",
            }
        ],
    },
}


def _lanes(xml: str) -> list[str]:
    return re.findall(r'<bpmn:lane id="[^"]*" name="([^"]*)"', xml)


def _lane_of(xml: str, task_name: str) -> str:
    task_id = re.search(rf'id="([^"]+)" name="[^"]*{task_name}', xml).group(1)
    for lane in re.findall(r"<bpmn:lane .*?</bpmn:lane>", xml, re.S):
        if f">{task_id}<" in lane:
            return re.search(r'name="([^"]*)"', lane).group(1)
    raise AssertionError(f"{task_name} is in no lane")


def test_without_the_agents_draft_the_lanes_are_the_stock_ones() -> None:
    xml = bpmn_service.generate_bpmn_xml(V2, session_id="s")
    assert set(_lanes(xml)) == {"Business User", "Reviewer", "GenAI"}


def test_the_lanes_are_the_roles_in_the_agents_draft() -> None:
    xml = bpmn_service.generate_bpmn_xml(V2, session_id="s", agent_draft=DRAFT)
    assert set(_lanes(xml)) == {"Accounts clerk", "Controller", "Booking system"}
    assert _lane_of(xml, "Approve invoice") == "Controller"
    assert _lane_of(xml, "Upload invoice") == "Accounts clerk"


def test_an_automated_step_without_a_component_stays_in_the_system_lane() -> None:
    # V2 has no such type, so the step came back as a user task in the user's lane.
    xml = bpmn_service.generate_bpmn_xml(V2, session_id="s", agent_draft=DRAFT)
    assert _lane_of(xml, "Forward to approver") == "Booking system"


def test_a_step_type_changed_in_the_ui_is_kept() -> None:
    edited = {
        **V2,
        "steps": [*V2["steps"][:2], {**V2["steps"][2], "type": "human_review"}, V2["steps"][3]],
    }
    xml = bpmn_service.generate_bpmn_xml(edited, session_id="s", agent_draft=DRAFT)
    assert _lane_of(xml, "Forward to approver") == "Controller"


def test_the_rework_loop_is_drawn_and_an_orphaned_one_is_dropped() -> None:
    xml = bpmn_service.generate_bpmn_xml(V2, session_id="s", agent_draft=DRAFT)
    assert 'name="No (rework)"' in xml
    assert "EndEvent_rejected_approve" not in xml

    gone = {**V2, "steps": V2["steps"][1:]}
    xml, _, v1 = bpmn_service.generate_bpmn_view(gone, session_id="s", agent_draft=DRAFT)
    assert v1["business_process"]["exceptions"] == []
    assert "No (rework)" not in xml
    assert "EndEvent_rejected_approve" in xml


def test_an_external_service_the_scaffolder_refuses_leaves_the_diagram_as_it_is() -> None:
    """The diagram takes only the input and output types from the draft's
    technical_spec, so an external service entry the blueprint model refuses changes
    neither the roles nor the diagram."""
    bad = {"name": "Web search", "python_package": "-e .", "env_vars": ["HTTPS_PROXY"]}
    draft = {**DRAFT, "technical_spec": {"input_types": ["pdf"], "external_services": [bad]}}

    xml, _, v1 = bpmn_service.generate_bpmn_view(V2, session_id="s", agent_draft=draft)

    assert "external_services" not in v1["technical_spec"]
    assert set(_lanes(xml)) == {"Accounts clerk", "Controller", "Booking system"}


def test_a_draft_that_does_not_fit_falls_back_to_the_stock_lanes() -> None:
    broken = {**DRAFT, "business_process": {"participants": [{"name": "no id"}]}}
    xml = bpmn_service.generate_bpmn_xml(V2, session_id="s", agent_draft=broken)
    assert set(_lanes(xml)) == {"Business User", "Reviewer", "GenAI"}


@requires_postgres
def test_the_session_diagram_uses_the_draft_in_the_output_dir(client) -> None:
    created = client.post("/sessions", json={"user_id": "roles", "title": "Roles"}).json()
    sid = created["id"]
    client.patch(f"/sessions/{sid}/blueprint", json={"content": V2})
    with open(os.path.join(created["output_dir"], artifact_sync.DRAFT_BLUEPRINT_FILE), "w") as fh:
        json.dump(DRAFT, fh)

    xml = client.get(f"/sessions/{sid}/bpmn").text

    assert "Accounts clerk" in _lanes(xml)
