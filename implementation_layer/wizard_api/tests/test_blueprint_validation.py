"""A blueprint body is checked when it is written, not when it is read.

``session_detail`` builds ``SessionDetailResponse(blueprint=...)`` from the
stored body, so one body that does not fit ``BlueprintContent`` used to make
every ``GET /sessions/{id}`` a 500 for the rest of the session's life — the
session was bricked by its own PATCH. The write now refuses it with a 422 and
nothing is stored.
"""

import pytest
from helpers import requires_postgres
from wizard_api.services.blueprint_service import InvalidBlueprintContentError, validate_content

VALID = {"name": "Tilaukset", "steps": [{"id": "s1", "name": "Lue", "type": "ai"}], "extra_key": 1}


def test_a_servable_body_passes_unchanged_extra_keys_included():
    assert validate_content(VALID) is VALID


def test_a_body_the_response_model_cannot_serve_is_refused_with_the_field_named():
    with pytest.raises(InvalidBlueprintContentError) as exc:
        validate_content({"steps": "not a list"})
    assert exc.value.errors[0]["loc"] == ["steps"]
    assert "steps" in str(exc.value)
    with pytest.raises(InvalidBlueprintContentError):
        validate_content({"data_objects": ["should", "be", "a", "mapping"]})


def _create(client) -> str:
    res = client.post("/sessions", json={"user_id": "alice@example.com", "title": "t"})
    assert res.status_code == 201, res.text
    return res.json()["id"]


@requires_postgres
def test_a_bad_patch_is_a_422_and_the_session_stays_readable(client) -> None:
    sid = _create(client)
    before = client.get(f"/sessions/{sid}").json()

    res = client.patch(f"/sessions/{sid}/blueprint", json={"content": {"steps": "x"}})
    assert res.status_code == 422
    assert res.json()["detail"]["error"] == "invalid_blueprint"
    assert res.json()["detail"]["errors"][0]["loc"] == ["steps"]

    after = client.get(f"/sessions/{sid}")
    assert after.status_code == 200
    assert after.json()["blueprint"] == before["blueprint"]
    assert after.json()["active_version"] == before["active_version"]


@requires_postgres
def test_a_bad_version_body_is_refused_the_same_way(client) -> None:
    sid = _create(client)
    res = client.post(f"/sessions/{sid}/versions", json={"note": "n", "content": {"gateways": "x"}})
    assert res.status_code == 422
    assert res.json()["detail"]["error"] == "invalid_blueprint"
    assert client.get(f"/sessions/{sid}").status_code == 200


@requires_postgres
def test_a_good_patch_still_lands(client) -> None:
    sid = _create(client)
    res = client.patch(f"/sessions/{sid}/blueprint", json={"content": VALID})
    assert res.status_code == 200
    assert res.json()["blueprint"]["name"] == "Tilaukset"
    assert res.json()["active_version"] == 2
