import pytest
from helpers import requires_postgres
from wizard_api.schemas.blueprint import BlueprintContent
from wizard_api.services import blueprint_service, bpmn_service

requires_solution_wizard = pytest.mark.skipif(
    not bpmn_service.solution_wizard_available(),
    reason="solution_wizard package not installed",
)


def test_the_seed_blueprint_has_no_goal_of_its_own() -> None:
    """The seed's goal reached the Blueprint tab as the solution's goal: "Draft flow
    so BPMN and JSON are editable from the first session." (issues 144 and 146)."""
    seed = blueprint_service.default_blueprint_content("Invoice bot")

    assert seed["goal"] == ""
    assert "Draft flow" not in str(seed)
    # A seed without a goal is still one the API can store and serve, and it is
    # still recognised as the seed (a PoC is not generated from it).
    assert blueprint_service.validate_content(seed) is seed
    assert BlueprintContent.model_validate(seed).goal == ""
    assert blueprint_service.is_placeholder(seed)


@requires_solution_wizard
def test_the_seed_blueprint_without_a_goal_still_gives_a_diagram() -> None:
    seed = blueprint_service.default_blueprint_content("Invoice bot")

    xml = bpmn_service.generate_bpmn_xml(seed, session_id="seed-goal")

    assert "<bpmn:definitions" in xml
    assert "Human review" in xml


@requires_postgres
def test_create_session_seeds_blueprint_version(client) -> None:
    create = client.post(
        "/sessions",
        json={"user_id": "bp-user", "title": "Invoice bot"},
    )
    assert create.status_code == 201
    body = create.json()
    assert body["title"] == "Invoice bot"
    assert body["active_version"] == 1
    assert len(body["versions"]) == 1
    assert body["versions"][0]["version"] == 1
    assert body["blueprint"]["name"] == "Invoice bot"
    assert len(body["blueprint"]["steps"]) >= 3
    assert "placeholder" in body["blueprint"]["description"].lower()
    # Nothing is known of the use case yet, so the session has no goal to show.
    assert body["blueprint"]["goal"] == ""


@requires_postgres
def test_append_version_and_resume(client) -> None:
    create = client.post(
        "/sessions",
        json={"user_id": "bp-user", "title": "Resume test"},
    )
    session_id = create.json()["id"]

    versioned = client.post(
        f"/sessions/{session_id}/versions",
        json={"note": "Vaihe 2"},
    )
    assert versioned.status_code == 200
    body = versioned.json()
    assert body["active_version"] == 2
    assert len(body["versions"]) == 2

    resumed = client.get(f"/sessions/{session_id}")
    assert resumed.status_code == 200
    assert resumed.json()["active_version"] == 2


@requires_postgres
def test_messages_persist_on_session(client) -> None:
    create = client.post("/sessions", json={"user_id": "chat-user", "title": "Chat"})
    session_id = create.json()["id"]

    updated = client.post(
        f"/sessions/{session_id}/messages",
        json={
            "user_content": "Hello",
            "assistant_content": "Mock reply",
        },
    )
    assert updated.status_code == 200
    messages = updated.json()["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["content"] == "Mock reply"

    fetched = client.get(f"/sessions/{session_id}")
    assert len(fetched.json()["messages"]) == 2
