"""The stack E2E's draft hook: mounted and answering only with WIZARD_TEST_HOOKS=1."""

import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from helpers import requires_postgres
from test_blueprint_ops import _draft
from wizard_api.db import get_db
from wizard_api.routers import test_hooks
from wizard_api.services import artifact_sync, blueprint_ops

pytestmark = pytest.mark.skipif(
    not blueprint_ops.solution_wizard_available(),
    reason="solution_wizard package not installed",
)


def test_the_draft_hook_is_absent_without_the_env_var(client, monkeypatch) -> None:
    # The app under test is built without WIZARD_TEST_HOOKS: the router is not
    # mounted at all (not only answering 404, which _require_hooks would also do).
    from wizard_api.main import app

    assert os.getenv("WIZARD_TEST_HOOKS") != "1"
    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/test/sessions/{session_id}/draft" not in paths
    assert "/test/shutdown" not in paths
    sid = "00000000-0000-0000-0000-000000000000"
    assert client.post(f"/test/sessions/{sid}/draft", json={}).status_code == 404
    assert client.get(f"/test/sessions/{sid}/draft").status_code == 404


@pytest.fixture
def hooks_client(db_session, monkeypatch):
    """An app with only the hooks router, as main mounts it when the env var is set."""
    app = FastAPI()
    app.include_router(test_hooks.router)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client


@requires_postgres
def test_the_mounted_hook_still_answers_404_without_the_env_var(
    client, hooks_client, monkeypatch
) -> None:
    monkeypatch.delenv("WIZARD_TEST_HOOKS", raising=False)
    created = client.post("/sessions", json={"user_id": "hook-user", "title": "Hook"}).json()
    res = hooks_client.post(f"/test/sessions/{created['id']}/draft", json=_draft())
    assert res.status_code == 404
    assert not os.path.exists(
        os.path.join(created["output_dir"], artifact_sync.DRAFT_BLUEPRINT_FILE)
    )


@requires_postgres
def test_the_hook_writes_a_valid_draft_and_reads_it_back(client, hooks_client, monkeypatch) -> None:
    monkeypatch.setenv("WIZARD_TEST_HOOKS", "1")
    created = client.post("/sessions", json={"user_id": "hook-user", "title": "Hook"}).json()
    sid = created["id"]

    assert hooks_client.get(f"/test/sessions/{sid}/draft").status_code == 404
    res = hooks_client.post(f"/test/sessions/{sid}/draft", json=_draft())
    assert res.status_code == 204, res.text

    path = os.path.join(created["output_dir"], artifact_sync.DRAFT_BLUEPRINT_FILE)
    with open(path, encoding="utf-8") as fh:
        assert json.load(fh) == _draft()
    assert hooks_client.get(f"/test/sessions/{sid}/draft").json() == _draft()


@requires_postgres
def test_the_hook_refuses_an_invalid_blueprint(client, hooks_client, monkeypatch) -> None:
    monkeypatch.setenv("WIZARD_TEST_HOOKS", "1")
    created = client.post("/sessions", json={"user_id": "hook-user", "title": "Hook"}).json()

    res = hooks_client.post(f"/test/sessions/{created['id']}/draft", json={"workflow": "x"})

    assert res.status_code == 422
    assert not os.path.exists(
        os.path.join(created["output_dir"], artifact_sync.DRAFT_BLUEPRINT_FILE)
    )


@requires_postgres
def test_the_hook_is_for_the_sessions_owner_only(client, hooks_client, monkeypatch) -> None:
    from wizard_api.ownership import USER_HEADER

    monkeypatch.setenv("WIZARD_TEST_HOOKS", "1")
    alice = {USER_HEADER: "alice@example.com"}
    created = client.post(
        "/sessions", json={"user_id": "alice@example.com", "title": "Hook"}, headers=alice
    ).json()

    res = hooks_client.post(
        f"/test/sessions/{created['id']}/draft",
        json=_draft(),
        headers={USER_HEADER: "bob@example.com"},
    )

    assert res.status_code == 404
