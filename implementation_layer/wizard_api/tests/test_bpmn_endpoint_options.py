"""``GET /sessions/{id}/bpmn?data_objects=0`` draws the diagram without data objects."""

import pytest
from helpers import requires_postgres
from wizard_api.services import bpmn_service

pytestmark = pytest.mark.skipif(
    not bpmn_service.solution_wizard_available(),
    reason="solution_wizard package not installed",
)

BLUEPRINT = {
    "name": "Invoices",
    "description": "Test",
    "goal": "Book invoices",
    "steps": [
        {"id": "upload", "name": "Upload invoice", "type": "io"},
        {"id": "extract", "name": "Extract fields", "type": "ai", "component": "extractor"},
        {"id": "approve", "name": "Approve invoice", "type": "human_review"},
    ],
}

DRAFT = {"business_spec": {"intended_users": ["Accountant"]}}


@pytest.mark.parametrize("agent_draft", [None, DRAFT], ids=["blueprint", "agent-draft"])
def test_the_view_passes_the_data_objects_option(monkeypatch, agent_draft) -> None:
    seen: list[bool] = []
    lanes: list[frozenset] = []
    real = bpmn_service.generate_bpmn

    def spy(blueprint, *, include_data_objects=True, extra_lane_ids=frozenset()):
        seen.append(include_data_objects)
        lanes.append(extra_lane_ids)
        return real(
            blueprint, include_data_objects=include_data_objects, extra_lane_ids=extra_lane_ids
        )

    monkeypatch.setattr(bpmn_service, "generate_bpmn", spy)
    if agent_draft is not None:
        # The draft path must be the one that renders, not the fallback.
        monkeypatch.setattr(
            bpmn_service,
            "with_agent_process",
            lambda v1, v2, draft: {**v1, "business_spec": v1.get("business_spec") or {}},
        )

    xml, mapping, _ = bpmn_service.generate_bpmn_view(
        BLUEPRINT, session_id="s1", agent_draft=agent_draft, include_data_objects=False
    )
    assert seen == [False]
    assert "dataObjectReference" not in xml
    assert all(info["kind"] != "data_object" for info in mapping.values())

    xml = bpmn_service.generate_bpmn_xml(
        BLUEPRINT, session_id="s1", agent_draft=agent_draft, extra_lane_ids=frozenset({"legal"})
    )
    assert seen == [False, True]
    assert "dataObjectReference" in xml
    # The user's lanes reach the generator too.
    assert lanes == [frozenset(), frozenset({"legal"})]


def _seeded_session(client) -> str:
    create = client.post("/sessions", json={"user_id": "bpmn-options", "title": "Options"})
    assert create.status_code == 201
    session_id = create.json()["id"]
    patched = client.patch(f"/sessions/{session_id}/blueprint", json={"content": BLUEPRINT})
    assert patched.status_code == 200
    return session_id


@requires_postgres
def test_the_bpmn_route_passes_the_data_objects_option(client) -> None:
    session_id = _seeded_session(client)

    compact = client.get(f"/sessions/{session_id}/bpmn", params={"data_objects": 0})
    assert compact.status_code == 200
    assert "<bpmn:definitions" in compact.text
    assert "dataObjectReference" not in compact.text
    assert compact.headers["X-AI-Generated"] == "true"

    for params in ({}, {"data_objects": 1}):
        full = client.get(f"/sessions/{session_id}/bpmn", params=params)
        assert full.status_code == 200
        assert "dataObjectReference" in full.text


@requires_postgres
@pytest.mark.parametrize("value", ["2", "-1", "yes"])
def test_the_bpmn_route_refuses_other_values(client, value) -> None:
    session_id = _seeded_session(client)
    response = client.get(f"/sessions/{session_id}/bpmn", params={"data_objects": value})
    assert response.status_code == 422
