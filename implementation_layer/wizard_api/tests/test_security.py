import pytest
from helpers import requires_postgres
from pydantic import ValidationError
from wizard_api.schemas.session import SessionCreate


def test_session_create_rejects_path_traversal_user_id() -> None:
    with pytest.raises(ValidationError):
        SessionCreate(user_id="../etc/passwd")


@requires_postgres
def test_list_sessions_isolated_by_user(client) -> None:
    """User A cannot see user B sessions via list endpoint."""
    create_a = client.post("/sessions", json={"user_id": "user-a", "title": "A"})
    create_b = client.post("/sessions", json={"user_id": "user-b", "title": "B"})
    assert create_a.status_code == 201
    assert create_b.status_code == 201

    list_a = client.get("/sessions", params={"user_id": "user-a"})
    ids = [s["id"] for s in list_a.json()["sessions"]]
    assert create_a.json()["id"] in ids
    assert create_b.json()["id"] not in ids


def test_test_hooks_disabled_by_default(client) -> None:
    assert client.post("/test/shutdown").status_code == 404


# --- Service-token auth (#132) ----------------------------------------------
#
# These deliberately use `api_client` (no Postgres): the middleware runs before
# routing, so a 401 never reaches the DB. The "valid token" case asserts only
# that the request got PAST the middleware — it lands on FastAPI's own 422 for
# the missing `user_id` query param, which is proof enough and keeps the test
# free of a database.

TOKEN = "test-service-token-123"
HEADER = "X-Wizard-Service-Token"


def test_no_token_rejected_when_auth_configured(api_client, monkeypatch) -> None:
    monkeypatch.setenv("WIZARD_API_TOKEN", TOKEN)
    res = api_client.get("/sessions")
    assert res.status_code == 401
    assert "service token" in res.json()["detail"].lower()


def test_wrong_token_rejected(api_client, monkeypatch) -> None:
    monkeypatch.setenv("WIZARD_API_TOKEN", TOKEN)
    res = api_client.get("/sessions", headers={HEADER: "not-the-token"})
    assert res.status_code == 401


def test_correct_token_passes_middleware(api_client, monkeypatch) -> None:
    monkeypatch.setenv("WIZARD_API_TOKEN", TOKEN)
    res = api_client.get("/sessions", headers={HEADER: TOKEN})
    assert res.status_code != 401
    assert res.status_code == 422  # missing user_id -> got past auth


def test_health_reachable_without_token(api_client, monkeypatch) -> None:
    """Liveness/readiness probes hold no secret and must not be locked out."""
    monkeypatch.setenv("WIZARD_API_TOKEN", TOKEN)
    res = api_client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_auth_disabled_when_token_unset(api_client, monkeypatch) -> None:
    """Unconfigured = open, so local dev and the docker stack keep working."""
    monkeypatch.delenv("WIZARD_API_TOKEN", raising=False)
    res = api_client.get("/sessions")
    assert res.status_code != 401


def test_empty_token_env_var_counts_as_unset(api_client, monkeypatch) -> None:
    """Whitespace must not silently enable auth with an empty secret."""
    monkeypatch.setenv("WIZARD_API_TOKEN", "   ")
    res = api_client.get("/sessions")
    assert res.status_code != 401
