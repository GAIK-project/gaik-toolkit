"""The agent sees the diagram the user sees, so it can explain a node or lane.

Customer feedback (October 2026): asked why a node or lane was chosen, the wizard
did not find it in the BPMN. The Workflow tab renders BPMN generated from the
session blueprint, and the agent only knew its own workflow.bpmn.
"""

import asyncio
import json
import os
import uuid

import pytest
from helpers import requires_postgres
from wizard_api.schemas.session import SessionUpdate
from wizard_api.services import agent_service, artifact_sync, bpmn_service, session_service

requires_solution_wizard = pytest.mark.skipif(
    not bpmn_service.solution_wizard_available(),
    reason="solution_wizard package not installed",
)

BLUEPRINT = {
    "name": "Invoices",
    "description": "Test",
    "goal": "Classify invoices",
    "steps": [
        {"id": "input", "name": "Invoice intake", "type": "io"},
        {"id": "extract", "name": "Data extraction", "type": "ai", "component": "extractor"},
        {"id": "review", "name": "Approval", "type": "human_review"},
    ],
}


@requires_solution_wizard
def test_the_view_maps_every_lane_to_where_it_came_from() -> None:
    xml, mapping, v1 = bpmn_service.generate_bpmn_view(BLUEPRINT, session_id="s-1")
    assert xml == bpmn_service.generate_bpmn_xml(BLUEPRINT, session_id="s-1")
    lanes = {k: v for k, v in mapping.items() if v["kind"] == "lane"}
    assert lanes
    participants = v1["business_process"]["participants"]
    for lane_id, entry in lanes.items():
        assert f'id="{lane_id}"' in xml
        # The path resolves in the blueprint written beside the diagram.
        index = int(entry["blueprint_path"].split("[")[1].rstrip("]"))
        assert f'name="{participants[index]["name"]}"' in xml


def test_the_view_is_written_next_to_the_agents_files(tmp_path) -> None:
    ok = artifact_sync.write_ui_view(
        str(tmp_path), "<bpmn/>", {"Lane_a": {"kind": "lane"}}, {"n": 1}
    )
    assert ok
    assert (tmp_path / artifact_sync.UI_VIEW_BPMN_FILE).read_text() == "<bpmn/>"
    mapping = json.loads((tmp_path / artifact_sync.UI_VIEW_MAPPING_FILE).read_text())
    assert mapping == {"Lane_a": {"kind": "lane"}}
    # Not where the agent's own BPMN lives, which moves the step on (#169).
    assert not (tmp_path / artifact_sync.WORKFLOW_BPMN_FILE).exists()


def test_writing_the_view_without_an_output_dir_does_nothing() -> None:
    assert artifact_sync.write_ui_view("", "<bpmn/>", {}, {}) is False


def _fake_agent(monkeypatch, seen: list[str]) -> None:
    async def fake_get_or_create_session(session_id, output_dir, locale=None, **kwargs):
        return {"lock": asyncio.Lock()}

    async def fake_stream_turn_for(agent, message, parts):
        seen.append(message)
        parts.append("Selitän kaavion.")
        yield agent_service.sse({"text": "Selitän kaavion."})

    monkeypatch.setattr(agent_service, "get_or_create_session", fake_get_or_create_session)
    monkeypatch.setattr(agent_service, "stream_turn_for", fake_stream_turn_for)


def _session(client, db_session, step: int) -> dict:
    created = client.post("/sessions", json={"user_id": "view", "title": "View"}).json()
    client.patch(f"/sessions/{created['id']}/blueprint", json={"content": BLUEPRINT})
    session = session_service.get_session(db_session, uuid.UUID(created["id"]))
    session_service.update_session(
        db_session, session, SessionUpdate(step=step, gate_statuses={"gate_1": "approved"})
    )
    return created


@requires_postgres
@requires_solution_wizard
def test_from_the_bpmn_step_each_message_names_the_users_diagram(
    client, db_session, monkeypatch
) -> None:
    seen: list[str] = []
    _fake_agent(monkeypatch, seen)
    created = _session(client, db_session, artifact_sync.STEP_BPMN)

    client.post(f"/sessions/{created['id']}/chat", json={"message": "Miksi tämä kaista?"})

    state, note, rest = seen[-1].split("\n", 2)
    assert state.startswith("[Session state:")
    assert note.startswith(
        "[The diagram the user sees in the Workflow tab is ui_view/workflow.bpmn"
    )
    assert rest == "\nMiksi tämä kaista?"
    shown = client.get(f"/sessions/{created['id']}/bpmn").text
    with open(os.path.join(created["output_dir"], artifact_sync.UI_VIEW_BPMN_FILE)) as fh:
        assert fh.read() == shown


@requires_postgres
@requires_solution_wizard
def test_before_the_bpmn_step_there_is_no_diagram_to_name(client, db_session, monkeypatch) -> None:
    seen: list[str] = []
    _fake_agent(monkeypatch, seen)
    created = _session(client, db_session, artifact_sync.STEP_BPMN - 1)

    client.post(f"/sessions/{created['id']}/chat", json={"message": "Hei"})

    assert "ui_view" not in seen[-1]
    assert not os.path.exists(os.path.join(created["output_dir"], artifact_sync.UI_VIEW_DIR))


@requires_postgres
def test_a_diagram_that_cannot_be_generated_does_not_break_the_chat(
    client, db_session, monkeypatch
) -> None:
    seen: list[str] = []
    _fake_agent(monkeypatch, seen)

    def boom(*args, **kwargs):
        raise bpmn_service.BpmnGenerationError("no generator")

    monkeypatch.setattr(bpmn_service, "generate_bpmn_view", boom)
    created = _session(client, db_session, artifact_sync.STEP_BPMN)

    res = client.post(f"/sessions/{created['id']}/chat", json={"message": "Hei"})

    assert res.status_code == 200
    assert "ui_view" not in seen[-1]
