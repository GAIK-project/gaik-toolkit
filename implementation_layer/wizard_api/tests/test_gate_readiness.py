"""A gate can be approved only when what it reviews exists, and nothing moves while the agent works.

Customer test feedback (17 Oct 2026): "Next step" worked while the agent was still
busy, Gate 2 was approved with no components, blueprint or diagram behind it, and
the agent then generated the rest on an approval that covered nothing.
"""

import asyncio
import os

from helpers import requires_postgres, write_gate_artifacts
from wizard_api.services import agent_service, artifact_sync


def _gate_missing(gate, root, successful_run=False, sandbox=False):
    return artifact_sync.gate_missing(
        gate, str(root), successful_run=successful_run, sandbox=sandbox
    )


def test_gate_1_needs_the_specification(tmp_path) -> None:
    assert _gate_missing("gate_1", tmp_path) == "the specification"
    write_gate_artifacts(str(tmp_path), "gate_1")
    assert _gate_missing("gate_1", tmp_path) is None


def test_gate_2_needs_components_blueprint_and_diagram(tmp_path) -> None:
    missing = _gate_missing("gate_2", tmp_path)
    assert "component selection" in missing and "workflow diagram" in missing

    write_gate_artifacts(str(tmp_path), "gate_1")
    assert _gate_missing("gate_2", tmp_path) == "the workflow diagram"

    write_gate_artifacts(str(tmp_path), "gate_2")
    assert _gate_missing("gate_2", tmp_path) is None


def test_gate_3_needs_the_package_and_with_a_sandbox_a_successful_run(tmp_path) -> None:
    write_gate_artifacts(str(tmp_path), "gate_2")
    assert _gate_missing("gate_3", tmp_path) == "the PoC package"

    write_gate_artifacts(str(tmp_path), "gate_3")
    assert _gate_missing("gate_3", tmp_path) is None
    assert _gate_missing("gate_3", tmp_path, sandbox=True) == "a successful sandbox run"
    assert _gate_missing("gate_3", tmp_path, sandbox=True, successful_run=True) is None


def test_gate_4_has_no_file_check(tmp_path) -> None:
    assert _gate_missing("gate_4", tmp_path) is None


def _new_session(client, user="ready-user"):
    return client.post("/sessions", json={"user_id": user}).json()


@requires_postgres
def test_gate_2_with_nothing_behind_it_is_refused(client) -> None:
    created = _new_session(client)
    write_gate_artifacts(created["output_dir"], "gate_1")
    client.patch(
        f"/sessions/{created['id']}", json={"step": 4, "gate_statuses": {"gate_1": "approved"}}
    )
    client.patch(f"/sessions/{created['id']}", json={"step": 9})

    refused = client.patch(
        f"/sessions/{created['id']}", json={"gate_statuses": {"gate_2": "approved"}}
    )
    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert detail["error"] == "gate_not_ready"
    assert detail["gate"] == "gate_2"
    assert "workflow diagram" in detail["missing"]
    assert client.get(f"/sessions/{created['id']}").json()["gate_statuses"]["gate_2"] == "pending"

    write_gate_artifacts(created["output_dir"], "gate_2")
    ok = client.patch(f"/sessions/{created['id']}", json={"gate_statuses": {"gate_2": "approved"}})
    assert ok.status_code == 200
    assert ok.json()["gate_statuses"]["gate_2"] == "approved"


@requires_postgres
def test_an_approval_already_given_is_not_checked_again(client) -> None:
    created = _new_session(client)
    write_gate_artifacts(created["output_dir"], "gate_1")
    client.patch(f"/sessions/{created['id']}", json={"gate_statuses": {"gate_1": "approved"}})
    os.remove(os.path.join(created["output_dir"], "use_case.blueprint.json"))

    # Re-sending the same approval, or rejecting, is not a new approval.
    again = client.patch(
        f"/sessions/{created['id']}", json={"gate_statuses": {"gate_1": "approved"}}
    )
    assert again.status_code == 200
    rejected = client.patch(
        f"/sessions/{created['id']}", json={"gate_statuses": {"gate_2": "rejected"}}
    )
    assert rejected.status_code == 200


@requires_postgres
def test_gate_3_waits_for_a_successful_run_when_the_sandbox_is_configured(
    client, monkeypatch
) -> None:
    from wizard_api.services import sandbox_runner

    monkeypatch.setattr(sandbox_runner, "kubernetes_available", lambda: True)
    monkeypatch.setenv("WIZARD_POC_RUNNER_IMAGE", "runner:test")
    created = _new_session(client)
    write_gate_artifacts(created["output_dir"], "gate_3")

    refused = client.patch(
        f"/sessions/{created['id']}", json={"gate_statuses": {"gate_3": "approved"}}
    )
    assert refused.status_code == 409
    assert refused.json()["detail"]["missing"] == "a successful sandbox run"


@requires_postgres
def test_nothing_moves_forward_while_the_agent_is_working(client) -> None:
    created = _new_session(client)
    session_id = created["id"]
    write_gate_artifacts(created["output_dir"], "gate_2")
    client.patch(f"/sessions/{session_id}", json={"step": 4})

    lock = asyncio.Lock()
    asyncio.run(lock.acquire())
    agent_service.AGENT_SESSIONS[session_id] = {"lock": lock}
    try:
        approve = client.patch(
            f"/sessions/{session_id}", json={"gate_statuses": {"gate_1": "approved"}}
        )
        assert approve.status_code == 409
        assert approve.json()["detail"]["error"] == "agent_busy"

        forward = client.patch(f"/sessions/{session_id}", json={"step": 5})
        assert forward.status_code == 409
        assert forward.json()["detail"]["error"] == "agent_busy"

        # Going back, and patches that do not move the session, still work.
        assert client.patch(f"/sessions/{session_id}", json={"step": 3}).status_code == 200
        assert (
            client.patch(f"/sessions/{session_id}", json={"metadata": {"note": "x"}}).status_code
            == 200
        )
    finally:
        agent_service.AGENT_SESSIONS.pop(session_id, None)

    assert client.patch(f"/sessions/{session_id}", json={"step": 4}).status_code == 200
    assert (
        client.patch(
            f"/sessions/{session_id}", json={"gate_statuses": {"gate_1": "approved"}}
        ).status_code
        == 200
    )


@requires_postgres
def test_the_check_can_be_turned_off_for_the_stack_e2e(client, monkeypatch) -> None:
    monkeypatch.setenv("WIZARD_GATE_READINESS", "off")
    created = _new_session(client)
    ok = client.patch(f"/sessions/{created['id']}", json={"gate_statuses": {"gate_2": "approved"}})
    assert ok.status_code == 200
