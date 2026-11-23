"""GET and PUT /sessions/{id}/blueprint/full: the whole draft, read and saved.

The full draft (``use_case.blueprint.json``) is the canonical blueprint. The
web app's JSON view reads it whole and saves an edited one through the flow
every workspace edit shares (``blueprint_edit_service.apply_edit``): one
"replace the draft" edit, refused when it changes a section the server owns,
when the result is no valid blueprint, or when it adds an error of a refusing
validator rule.
"""

import copy
import json
import os
import uuid

import pytest
from helpers import requires_postgres
from test_blueprint_operations_api import _approved_through_gate_3, _create, _write_draft
from test_blueprint_ops import _draft
from wizard_api.models import BlueprintVersion
from wizard_api.ownership import USER_HEADER
from wizard_api.schemas import blueprint_ops as ops_schema
from wizard_api.services import (
    agent_service,
    artifact_sync,
    blueprint_ops,
    blueprint_service,
    session_service,
)

pytestmark = pytest.mark.skipif(
    not blueprint_ops.solution_wizard_available(),
    reason="solution_wizard package not installed",
)

READONLY = [
    "blueprint_version",
    "metadata",
    "visualizations",
    "package",
    "traceability",
    "change_log",
]
SUMMARY = "Edited the blueprint as JSON"


def _put(
    client,
    sid: str,
    base: int,
    draft: dict,
    *,
    digest: str | None = None,
    headers: dict | None = None,
):
    """A full save; without ``digest``, on the draft's digest as GET answers it now."""
    if digest is None:
        got = client.get(f"/sessions/{sid}/blueprint/full", headers=headers or {})
        digest = got.json().get("draft_digest", "") if got.is_success else ""
    return client.put(
        f"/sessions/{sid}/blueprint/full",
        json={"base_version": base, "base_digest": digest, "draft": draft},
        headers=headers or {},
    )


def _on_disk(output_dir: str) -> dict:
    with open(os.path.join(output_dir, artifact_sync.DRAFT_BLUEPRINT_FILE), encoding="utf-8") as fh:
        return json.load(fh)


def _versions(db_session, sid: str) -> list[BlueprintVersion]:
    db_session.expire_all()
    return blueprint_service.list_versions(db_session, uuid.UUID(sid))


@pytest.fixture
def not_busy(monkeypatch):
    monkeypatch.setattr(agent_service, "is_busy", lambda session_id: False)


def test_the_limit_is_the_blueprints_own() -> None:
    from solution_wizard.blueprint import MAX_BLUEPRINT_CHARS

    assert ops_schema.MAX_BLUEPRINT_CHARS == MAX_BLUEPRINT_CHARS


# ---------------------------------------------------------------- GET


@requires_postgres
def test_get_answers_the_draft_its_version_and_the_readonly_sections(
    client, db_session, not_busy
) -> None:
    created = _create(client, "full-user")

    res = client.get(f"/sessions/{created['id']}/blueprint/full")

    assert res.status_code == 200, res.text
    assert res.json() == {
        "version": created["active_version"],
        "draft": _draft(),
        "readonly_sections": READONLY,
        "draft_digest": artifact_sync.content_digest(_draft()),
    }
    assert len(_versions(db_session, created["id"])) == 1


@requires_postgres
def test_get_without_a_draft_answers_409_no_draft(client, db_session) -> None:
    created = _create(client, "full-user", draft=False)

    res = client.get(f"/sessions/{created['id']}/blueprint/full")

    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "no_draft"


@requires_postgres
def test_another_users_session_is_not_found(client, db_session, not_busy) -> None:
    alice = {USER_HEADER: "alice@example.com"}
    other = {USER_HEADER: "bob@example.com"}
    created = client.post(
        "/sessions", json={"user_id": "alice@example.com", "title": "Full"}, headers=alice
    ).json()
    _write_draft(created["output_dir"])

    got = client.get(f"/sessions/{created['id']}/blueprint/full", headers=other)
    put = _put(client, created["id"], created["active_version"], _draft(), headers=other)

    assert got.status_code == 404
    assert put.status_code == 404
    assert client.get(f"/sessions/{created['id']}/blueprint/full", headers=alice).is_success


# ---------------------------------------------------------------- PUT


@requires_postgres
def test_a_json_edit_of_a_step_redraws(client, db_session, not_busy) -> None:
    created = _create(client, "full-user")
    sid = created["id"]
    base = created["active_version"]
    draft = _draft()
    draft["workflow"]["steps"][1]["name"] = "Read the invoice"

    res = _put(client, sid, base, draft)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["bpmn_changed"] is True
    assert {"session", "warnings", "needs_attention", "bpmn_changed"} == set(body)
    assert body["session"]["active_version"] == base + 1
    assert _on_disk(created["output_dir"]) == draft
    newest = _versions(db_session, sid)[-1]
    assert newest.draft == draft
    assert newest.note == f"Workspace edit: {SUMMARY}"
    assert body["session"]["metadata"]["pending_user_edits"] == [SUMMARY]


@requires_postgres
def test_a_json_edit_outside_the_diagram_does_not_redraw(client, db_session, not_busy) -> None:
    detail = _approved_through_gate_3(client, db_session)
    sid = detail["id"]
    draft = _on_disk(detail["output_dir"])

    # A change the diagram does not show and the approved solution does not cover.
    draft["models"] = {"default": "a-model"}
    res = _put(client, sid, detail["active_version"], draft)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["bpmn_changed"] is False
    assert body["session"]["gate_statuses"]["gate_3"] == "approved"

    # A change the diagram does not show either, to what Gate 2 approved.
    draft["technical_spec"]["model_provider"] = "another-provider"
    res = _put(client, sid, body["session"]["active_version"], draft)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["bpmn_changed"] is False
    assert body["session"]["gate_statuses"]["gate_2"] == "pending"
    assert body["session"]["gate_statuses"]["gate_3"] == "pending"
    assert body["session"]["metadata"]["gate_reopened"]["gate"] == "gate_2"


@requires_postgres
@pytest.mark.parametrize(
    ("section", "value"),
    [
        ("metadata", {"blueprint_id": "mine"}),  # missing before: present counts as changed
        ("blueprint_version", "2.0"),
        ("change_log", [{"version": "1", "change": "mine"}]),
    ],
)
def test_a_changed_readonly_section_is_refused(
    client, db_session, not_busy, section, value
) -> None:
    created = _create(client, "full-user")
    before = _on_disk(created["output_dir"])
    draft = _draft()
    draft[section] = value

    res = _put(client, created["id"], created["active_version"], draft)

    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["error"] == "readonly_section"
    assert detail["field"] == section
    assert _on_disk(created["output_dir"]) == before
    assert len(_versions(db_session, created["id"])) == 1


@requires_postgres
def test_a_removed_readonly_section_is_refused(client, db_session, not_busy) -> None:
    created = _create(client, "full-user")
    _write_draft(created["output_dir"], {**_draft(), "package": {"name": "invoices"}})
    draft = _draft()  # without "package"

    res = _put(client, created["id"], created["active_version"], draft)

    assert res.status_code == 422
    assert res.json()["detail"]["error"] == "readonly_section"
    assert res.json()["detail"]["field"] == "package"


@requires_postgres
def test_an_invalid_draft_is_refused_with_its_field(client, db_session, not_busy) -> None:
    created = _create(client, "full-user")
    before = _on_disk(created["output_dir"])
    draft = _draft()
    del draft["workflow"]["steps"][0]["name"]

    res = _put(client, created["id"], created["active_version"], draft)

    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["error"] == "invalid_draft"
    assert detail["field"] == "workflow.steps.0.name"
    assert detail["message"]
    assert _on_disk(created["output_dir"]) == before
    assert len(_versions(db_session, created["id"])) == 1


@requires_postgres
def test_an_error_of_a_refusing_rule_is_refused_as_an_invalid_operation(
    client, db_session, not_busy
) -> None:
    created = _create(client, "full-user")
    draft = _draft()
    draft["workflow"]["steps"][0]["outputs"].append("undeclared")

    res = _put(client, created["id"], created["active_version"], draft)

    assert res.status_code == 422
    assert res.json()["detail"]["error"] == "invalid_operation"
    assert len(_versions(db_session, created["id"])) == 1


@requires_postgres
def test_a_stale_base_is_refused(client, db_session, not_busy) -> None:
    created = _create(client, "full-user")
    draft = _draft()
    draft["use_case"]["description"] = "changed"

    res = _put(client, created["id"], created["active_version"] - 1, draft)

    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "changed_elsewhere"
    assert _on_disk(created["output_dir"]) == _draft()


@requires_postgres
def test_a_busy_agent_answers_409_agent_busy(client, db_session, monkeypatch) -> None:
    created = _create(client, "full-user")
    monkeypatch.setattr(agent_service, "is_busy", lambda session_id: True)
    draft = _draft()
    draft["use_case"]["description"] = "changed"

    res = _put(client, created["id"], created["active_version"], draft)

    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "agent_busy"


@requires_postgres
def test_an_unchanged_draft_adds_no_version(client, db_session, not_busy) -> None:
    created = _create(client, "full-user")

    res = _put(client, created["id"], created["active_version"], _draft())

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["bpmn_changed"] is False
    assert body["session"]["active_version"] == created["active_version"]
    assert len(_versions(db_session, created["id"])) == 1
    assert not body["session"]["metadata"].get(session_service.PENDING_USER_EDITS_KEY)


@requires_postgres
def test_a_draft_over_64_kb_is_taken(client, db_session, not_busy) -> None:
    created = _create(client, "full-user")
    draft = _draft()
    draft["use_case"]["description"] = "x" * (ops_schema.MAX_REQUEST_BYTES * 2)

    res = _put(client, created["id"], created["active_version"], draft)

    assert res.status_code == 200, res.text
    assert res.json()["bpmn_changed"] is False


@requires_postgres
def test_a_draft_over_the_blueprint_limit_answers_413(client, db_session, not_busy) -> None:
    created = _create(client, "full-user")
    draft = copy.deepcopy(_draft())
    draft["use_case"]["description"] = "x" * ops_schema.MAX_BLUEPRINT_CHARS

    res = _put(client, created["id"], created["active_version"], draft)

    assert res.status_code == 413
    assert res.json()["detail"]["error"] == "too_large"
    assert len(_versions(db_session, created["id"])) == 1


@requires_postgres
def test_a_body_without_a_draft_is_refused(client, db_session, not_busy) -> None:
    created = _create(client, "full-user")

    res = client.put(
        f"/sessions/{created['id']}/blueprint/full",
        json={"base_version": created["active_version"]},
    )

    assert res.status_code == 422


# ---------------------------------------------------------------- the draft's digest


def _agent_writes(output_dir: str, change) -> None:
    """The agent changes its file in a way that adds no version (outside the reduced view)."""
    on_disk = _on_disk(output_dir)
    change(on_disk)
    _write_draft(output_dir, on_disk)


@requires_postgres
def test_a_save_on_a_draft_the_agent_changed_since_is_refused(client, db_session, not_busy) -> None:
    created = _create(client, "full-user")
    sid = created["id"]
    seen = client.get(f"/sessions/{sid}/blueprint/full").json()
    _agent_writes(
        created["output_dir"],
        lambda d: d.__setitem__("target_output_spec", {"fields": ["total", "due_date"]}),
    )
    after_agent = _on_disk(created["output_dir"])
    draft = copy.deepcopy(seen["draft"])
    draft["workflow"]["steps"][1]["name"] = "Read the invoice"

    res = _put(client, sid, seen["version"], draft, digest=seen["draft_digest"])

    assert seen["version"] == created["active_version"]  # the agent added no version
    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "changed_elsewhere"
    assert _on_disk(created["output_dir"]) == after_agent
    assert len(_versions(db_session, sid)) == 1


@requires_postgres
def test_a_change_log_the_agent_wrote_since_answers_changed_elsewhere(
    client, db_session, not_busy
) -> None:
    created = _create(client, "full-user")
    sid = created["id"]
    seen = client.get(f"/sessions/{sid}/blueprint/full").json()
    _agent_writes(
        created["output_dir"],
        lambda d: d.__setitem__("change_log", [{"version": "1", "change": "Gate 2 approved"}]),
    )
    draft = copy.deepcopy(seen["draft"])
    draft["use_case"]["description"] = "changed"

    res = _put(client, sid, seen["version"], draft, digest=seen["draft_digest"])

    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "changed_elsewhere"


@requires_postgres
def test_a_save_without_a_base_digest_is_refused(client, db_session, not_busy) -> None:
    created = _create(client, "full-user")

    res = client.put(
        f"/sessions/{created['id']}/blueprint/full",
        json={"base_version": created["active_version"], "draft": _draft()},
    )

    assert res.status_code == 422
