"""A session is served only to the user it belongs to (#134, review K2).

The web proxy already checked ownership; the API did not, so anyone holding
the service token could read or change any session. `X-Wizard-User-Id` now
names the user a call acts for, and every `/sessions/{id}/...` route answers
404 for a session that is not theirs — the same 404 a missing session gets.
"""

import os

import pytest
from fastapi import HTTPException
from helpers import requires_postgres
from wizard_api import config
from wizard_api.ownership import USER_HEADER, requesting_user
from wizard_api.services.session_service import (
    SERVER_OWNED_METADATA_KEYS,
    ServerOwnedMetadataError,
    check_metadata_patch,
)

ALICE = {USER_HEADER: "alice@example.com"}
BOB = {USER_HEADER: "bob@example.com"}


def _create(client, user_id: str, headers: dict | None = None) -> str:
    res = client.post("/sessions", json={"user_id": user_id, "title": "t"}, headers=headers or {})
    assert res.status_code == 201, res.text
    return res.json()["id"]


# --- pure: the header and the flag -------------------------------------------


def test_a_blank_header_counts_as_absent(monkeypatch):
    monkeypatch.delenv("WIZARD_REQUIRE_USER_HEADER", raising=False)
    assert requesting_user(None) is None
    assert requesting_user("   ") is None
    assert requesting_user(" alice ") == "alice"


def test_the_header_is_optional_until_the_deployment_requires_it(monkeypatch):
    monkeypatch.delenv("WIZARD_REQUIRE_USER_HEADER", raising=False)
    assert config.user_header_required() is False
    monkeypatch.setenv("WIZARD_REQUIRE_USER_HEADER", "1")
    assert config.user_header_required() is True
    with pytest.raises(HTTPException) as exc:
        requesting_user(None)
    assert exc.value.status_code == 400


def test_server_owned_metadata_keys_are_refused():
    check_metadata_patch({"title": "ok", "status": "done"})
    with pytest.raises(ServerOwnedMetadataError) as exc:
        check_metadata_patch({"title": "ok", "last_successful_run": "run-1", "messages": []})
    assert exc.value.keys == ["last_successful_run", "messages"]
    assert "last_successful_run" in SERVER_OWNED_METADATA_KEYS
    assert "agent_sdk_session_id" in SERVER_OWNED_METADATA_KEYS
    assert "latest_run_inputs" in SERVER_OWNED_METADATA_KEYS


# --- through the API ----------------------------------------------------------


@requires_postgres
def test_the_owner_sees_the_session_and_another_user_gets_404(client) -> None:
    sid = _create(client, "alice@example.com", ALICE)

    assert client.get(f"/sessions/{sid}", headers=ALICE).status_code == 200
    denied = client.get(f"/sessions/{sid}", headers=BOB)
    assert denied.status_code == 404
    # Indistinguishable from a session that does not exist (but for the trace id).
    missing = client.get(
        f"/sessions/{os.urandom(16).hex()[:8]}-0000-4000-8000-000000000000", headers=BOB
    ).json()
    assert {**denied.json()["detail"], "trace_id": None} == {**missing["detail"], "trace_id": None}


@requires_postgres
def test_every_session_route_is_covered_not_only_get(client) -> None:
    """The dependency sits on the router, so a route added later is covered too."""
    sid = _create(client, "alice@example.com", ALICE)

    assert (
        client.patch(f"/sessions/{sid}", json={"metadata": {"title": "x"}}, headers=BOB).status_code
        == 404
    )
    assert client.get(f"/sessions/{sid}/bpmn", headers=BOB).status_code == 404
    assert client.get(f"/sessions/{sid}/poc", headers=BOB).status_code == 404
    assert (
        client.post(f"/sessions/{sid}/versions", json={"note": "n"}, headers=BOB).status_code == 404
    )
    assert client.post(f"/sessions/{sid}/runs", headers=BOB).status_code == 404
    # ...and the owner is not affected.
    assert (
        client.patch(
            f"/sessions/{sid}", json={"metadata": {"title": "x"}}, headers=ALICE
        ).status_code
        == 200
    )


@requires_postgres
def test_a_call_without_the_header_is_still_served_until_the_flag_is_set(
    client, monkeypatch
) -> None:
    """The sandbox init container and the E2E helpers call with the token alone."""
    monkeypatch.delenv("WIZARD_REQUIRE_USER_HEADER", raising=False)
    sid = _create(client, "alice@example.com")
    assert client.get(f"/sessions/{sid}").status_code == 200

    monkeypatch.setenv("WIZARD_REQUIRE_USER_HEADER", "1")
    refused = client.get(f"/sessions/{sid}")
    assert refused.status_code == 400
    assert USER_HEADER in refused.json()["detail"]["message"]
    assert client.get(f"/sessions/{sid}", headers=ALICE).status_code == 200


@requires_postgres
def test_listing_and_creating_as_someone_else_is_refused(client) -> None:
    _create(client, "alice@example.com", ALICE)

    assert (
        client.get("/sessions", params={"user_id": "alice@example.com"}, headers=ALICE).status_code
        == 200
    )
    assert (
        client.get("/sessions", params={"user_id": "alice@example.com"}, headers=BOB).status_code
        == 403
    )
    assert (
        client.post("/sessions", json={"user_id": "alice@example.com"}, headers=BOB).status_code
        == 403
    )


@requires_postgres
def test_the_caller_cannot_choose_the_output_dir(client) -> None:
    res = client.post(
        "/sessions",
        json={"user_id": "alice@example.com", "output_dir": "/data/sessions/bob/stolen"},
        headers=ALICE,
    )
    assert res.status_code == 201
    assert "stolen" not in res.json()["output_dir"]
    assert res.json()["output_dir"].endswith(res.json()["id"])


@requires_postgres
def test_a_patch_cannot_forge_what_the_server_records(client) -> None:
    sid = _create(client, "alice@example.com", ALICE)
    res = client.patch(
        f"/sessions/{sid}",
        json={"metadata": {"last_successful_run": "run-1", "title": "fine"}},
        headers=ALICE,
    )
    assert res.status_code == 422
    assert res.json()["detail"]["error"] == "server_owned_metadata"
    assert res.json()["detail"]["keys"] == ["last_successful_run"]
    # Nothing of the patch was applied.
    assert client.get(f"/sessions/{sid}", headers=ALICE).json()["metadata"].get("title") == "t"


@requires_postgres
@pytest.mark.parametrize(
    "key, value",
    [
        ("last_successful_run", {"run_id": "r1"}),
        ("agent_sdk_session_id", "11111111-1111-4111-8111-111111111111"),
        ("messages", [{"role": "user", "content": "hei"}]),
    ],
)
def test_a_new_session_cannot_carry_server_owned_metadata(client, key, value) -> None:
    res = client.post(
        "/sessions", json={"user_id": "new-user", "title": "T", "metadata": {key: value}}
    )

    assert res.status_code == 422
    assert res.json()["detail"]["error"] == "server_owned_metadata"
    assert res.json()["detail"]["keys"] == [key]


@requires_postgres
def test_a_new_session_keeps_the_callers_own_metadata(client) -> None:
    res = client.post(
        "/sessions", json={"user_id": "new-user", "title": "T", "metadata": {"note": "x"}}
    )

    assert res.status_code == 201, res.text
    assert res.json()["metadata"]["note"] == "x"
