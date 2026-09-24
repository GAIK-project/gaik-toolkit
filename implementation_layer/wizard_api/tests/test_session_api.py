from helpers import requires_postgres


@requires_postgres
def test_create_get_patch_session(client) -> None:
    create = client.post(
        "/sessions",
        json={
            "user_id": "user-demo",
            "metadata": {"use_case": "PO PDF extraction"},
        },
    )
    assert create.status_code == 201
    body = create.json()
    session_id = body["id"]
    assert body["step"] == 1
    assert body["gate_statuses"]["gate_1"] == "pending"
    assert body["metadata"]["use_case"] == "PO PDF extraction"
    assert body["output_dir"].endswith(session_id)

    fetched = client.get(f"/sessions/{session_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == session_id

    patched = client.patch(
        f"/sessions/{session_id}",
        json={"step": 3, "gate_statuses": {"gate_1": "approved"}},
    )
    assert patched.status_code == 200
    updated = patched.json()
    assert updated["step"] == 3
    assert updated["gate_statuses"]["gate_1"] == "approved"
    assert updated["gate_statuses"]["gate_2"] == "pending"


@requires_postgres
def test_list_sessions_for_user(client) -> None:
    client.post("/sessions", json={"user_id": "lister"})
    client.post("/sessions", json={"user_id": "lister"})

    listed = client.get("/sessions", params={"user_id": "lister"})
    assert listed.status_code == 200
    assert len(listed.json()["sessions"]) == 2


@requires_postgres
def test_get_missing_session_returns_404(client) -> None:
    missing = client.get("/sessions/00000000-0000-0000-0000-000000000099")
    assert missing.status_code == 404


def test_patch_invalid_step_returns_422(api_client) -> None:
    """Validation runs before DB — works without Postgres."""
    response = api_client.patch(
        "/sessions/00000000-0000-0000-0000-000000000001",
        json={"step": 0},
    )
    assert response.status_code == 422
