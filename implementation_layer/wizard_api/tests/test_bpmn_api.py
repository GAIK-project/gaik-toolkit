"""BPMN API routes — generate, blueprint patch, canvas sync."""

from helpers import requires_postgres
from wizard_api.services import bpmn_service

requires_solution_wizard = __import__("pytest").mark.skipif(
    not bpmn_service.solution_wizard_available(),
    reason="solution_wizard package not installed",
)

SAMPLE_BLUEPRINT = {
    "name": "Chatbot",
    "description": "Test",
    "goal": "Automate Q&A",
    "steps": [
        {"id": "input", "name": "User question", "type": "io"},
        {"id": "rag", "name": "RAG search", "type": "ai", "component": "pgvector"},
        {"id": "review", "name": "Human review", "type": "human_review"},
    ],
}


@requires_postgres
@requires_solution_wizard
def test_get_session_bpmn_returns_xml(client) -> None:
    create = client.post(
        "/sessions",
        json={"user_id": "bpmn-user", "title": "BPMN test"},
    )
    assert create.status_code == 201
    session_id = create.json()["id"]

    patched = client.patch(
        f"/sessions/{session_id}/blueprint",
        json={"content": SAMPLE_BLUEPRINT, "note": "Seed for BPMN"},
    )
    assert patched.status_code == 200

    bpmn = client.get(f"/sessions/{session_id}/bpmn")
    assert bpmn.status_code == 200
    assert "application/xml" in bpmn.headers.get("content-type", "")
    assert "<bpmn:definitions" in bpmn.text
    assert "RAG search" in bpmn.text
    # The diagram says a model made it, in a line a person sees first.
    assert bpmn.text.splitlines()[1].startswith("<!-- ai_generated: true;")
    assert bpmn.headers["X-AI-Generated"] == "true"


@requires_postgres
@requires_solution_wizard
def test_patch_blueprint_creates_new_version(client) -> None:
    create = client.post("/sessions", json={"user_id": "bp-user", "title": "Patch test"})
    session_id = create.json()["id"]
    assert create.json()["active_version"] == 1

    patched = client.patch(
        f"/sessions/{session_id}/blueprint",
        json={"content": SAMPLE_BLUEPRINT},
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["active_version"] == 2
    assert body["blueprint"]["steps"][1]["name"] == "RAG search"


@requires_postgres
@requires_solution_wizard
def test_bpmn_sync_updates_blueprint_from_canvas(client) -> None:
    create = client.post("/sessions", json={"user_id": "sync-user", "title": "Sync test"})
    session_id = create.json()["id"]
    client.patch(
        f"/sessions/{session_id}/blueprint",
        json={"content": SAMPLE_BLUEPRINT},
    )

    bpmn = client.get(f"/sessions/{session_id}/bpmn")
    assert bpmn.status_code == 200
    edited = bpmn.text.replace("RAG search", "Vector retrieval")

    synced = client.post(
        f"/sessions/{session_id}/bpmn/sync",
        json={"xml": edited},
    )
    assert synced.status_code == 200
    steps = synced.json()["blueprint"]["steps"]
    names = [s["name"] for s in steps]
    assert "Vector retrieval" in names


@requires_postgres
@requires_solution_wizard
def test_bpmn_sync_of_an_unchanged_diagram_writes_no_version(client) -> None:
    create = client.post("/sessions", json={"user_id": "sync-user", "title": "Sync twice"})
    session_id = create.json()["id"]
    client.patch(f"/sessions/{session_id}/blueprint", json={"content": SAMPLE_BLUEPRINT})

    def sync(xml: str) -> dict:
        res = client.post(f"/sessions/{session_id}/bpmn/sync", json={"xml": xml})
        assert res.status_code == 200
        return res.json()

    # The first save records what the diagram adds to the form's blueprint (its
    # data objects and gateways); the same diagram saved again changes nothing.
    xml = client.get(f"/sessions/{session_id}/bpmn").text
    first = sync(xml)
    same = sync(xml)
    assert same["active_version"] == first["active_version"]
    assert len(same["versions"]) == len(first["versions"])
    assert same["blueprint"] == first["blueprint"]

    # A real edit writes one version, and saving that diagram again none.
    edited = xml.replace("RAG search", "Vector retrieval")
    changed = sync(edited)
    assert changed["active_version"] == first["active_version"] + 1
    again = sync(edited)
    assert again["active_version"] == changed["active_version"]
    assert len(again["versions"]) == len(changed["versions"])
    assert "Vector retrieval" in [s["name"] for s in again["blueprint"]["steps"]]


def test_bpmn_sync_request_refuses_xml_over_the_size_limit() -> None:
    import pytest
    from pydantic import ValidationError
    from wizard_api.routers.sessions import MAX_BPMN_XML_CHARS, BpmnSyncRequest

    BpmnSyncRequest(xml="x" * MAX_BPMN_XML_CHARS)
    with pytest.raises(ValidationError):
        BpmnSyncRequest(xml="x" * (MAX_BPMN_XML_CHARS + 1))


@requires_solution_wizard
def test_api_and_sync_share_the_bpmn_size_limit() -> None:
    from solution_wizard.bpmn_sync import MAX_BPMN_XML_CHARS as SYNC_LIMIT
    from wizard_api.routers.sessions import MAX_BPMN_XML_CHARS

    assert MAX_BPMN_XML_CHARS == SYNC_LIMIT
