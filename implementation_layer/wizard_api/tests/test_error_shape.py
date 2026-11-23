"""Errors carry no internal detail: one shape, a stable code, the cause in the log.

Every error answer is ``{"detail": {"error", "message", "trace_id", ...}}``. The
codes the web branches on keep their names and the details a person needs to
act; an exception's text, a server path, a stack trace or a Kubernetes message
is logged under the trace id and never sent.
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from helpers import requires_postgres
from wizard_api import errors
from wizard_api.main import app

LEAK = "/srv/wizard/output/secret-session/poc Traceback (most recent call last)"


def _assert_shape(body: dict, code: str) -> dict:
    detail = body["detail"]
    assert detail["error"] == code
    assert isinstance(detail["message"], str) and detail["message"]
    assert isinstance(detail["trace_id"], str) and detail["trace_id"]
    return detail


def _assert_no_leak(text: str) -> None:
    for internal in ("/srv/wizard", "Traceback", "secret-session"):
        assert internal not in text


# --- without a database -------------------------------------------------------


def test_an_unknown_route_answers_in_the_shape_with_the_callers_trace_id(api_client) -> None:
    res = api_client.get("/no-such-route", headers={"x-trace-id": "trace-abc-123"})

    assert res.status_code == 404
    detail = _assert_shape(res.json(), "not_found")
    assert detail["trace_id"] == "trace-abc-123"
    assert res.headers["x-trace-id"] == "trace-abc-123"


def test_a_trace_id_that_is_not_an_id_is_replaced(api_client) -> None:
    res = api_client.get("/no-such-route", headers={"x-trace-id": "<script>alert(1)</script>"})

    detail = _assert_shape(res.json(), "not_found")
    assert "script" not in detail["trace_id"]
    assert res.headers["x-trace-id"] == detail["trace_id"]


def test_the_health_check_carries_a_trace_id(api_client) -> None:
    assert api_client.get("/health").headers["x-trace-id"]


def test_an_unhandled_error_is_logged_with_the_trace_id_and_answered_generically(
    monkeypatch, caplog
) -> None:
    from wizard_api.routers import sessions

    def boom(*_a, **_k):
        raise RuntimeError(LEAK)

    monkeypatch.setattr(sessions.session_service, "get_session", boom)
    app.dependency_overrides[sessions.get_db] = lambda: None
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            with caplog.at_level(logging.ERROR):
                res = client.get(
                    "/sessions/00000000-0000-4000-8000-000000000000",
                    headers={"x-trace-id": "trace-unhandled-1"},
                )
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 500
    detail = _assert_shape(res.json(), "internal_error")
    assert detail["trace_id"] == "trace-unhandled-1"
    _assert_no_leak(res.text)
    logged = [r for r in caplog.records if "trace-unhandled-1" in r.getMessage()]
    assert logged and logged[0].exc_info is not None


def test_a_malformed_request_names_the_field_but_echoes_no_input(api_client) -> None:
    res = api_client.post("/sessions", json={"title": LEAK})

    assert res.status_code == 422
    detail = _assert_shape(res.json(), "invalid_request")
    assert ["body", "user_id"] in [e["loc"] for e in detail["errors"]]
    assert all(set(e) == {"loc", "msg", "type"} for e in detail["errors"])
    _assert_no_leak(res.text)


def test_a_plain_refusal_gets_the_code_of_its_status() -> None:
    import asyncio

    from starlette.exceptions import HTTPException

    request = SimpleNamespace(state=SimpleNamespace(trace_id="trace-plain-1"))
    res = asyncio.run(
        errors.http_exception_handler(request, HTTPException(409, "no PoC package to run yet"))
    )

    assert json.loads(res.body) == {
        "detail": {
            "error": "conflict",
            "message": "no PoC package to run yet",
            "trace_id": "trace-plain-1",
        }
    }


def test_a_structured_refusal_keeps_its_code_and_what_the_person_needs() -> None:
    import asyncio

    from fastapi import HTTPException

    request = SimpleNamespace(state=SimpleNamespace(trace_id="trace-gate-1"))
    exc = HTTPException(
        409, detail={"error": "gate_not_ready", "gate": "gate_2", "missing": "the BPMN"}
    )
    body = json.loads(asyncio.run(errors.http_exception_handler(request, exc)).body)

    assert body["detail"]["error"] == "gate_not_ready"
    assert body["detail"]["missing"] == "the BPMN"
    assert body["detail"]["trace_id"] == "trace-gate-1"


@pytest.mark.parametrize(
    ("phase", "message", "expected"),
    [
        ("failed", "Job has reached the specified backoff limit", None),
        ("timeout", "the run passed its ten-minute limit and was stopped", "the run passed"),
        ("succeeded", None, None),
    ],
)
def test_a_run_status_says_only_the_runners_own_words(phase, message, expected) -> None:
    said = errors.public_run_message(SimpleNamespace(run_id="r", phase=phase, message=message))

    if expected is None:
        assert said is None
    else:
        assert said is not None and said.startswith(expected)


# --- through the session routes ----------------------------------------------


@requires_postgres
def test_a_bpmn_failure_names_no_path(client, monkeypatch, caplog) -> None:
    from wizard_api.services import bpmn_service

    def broken(*_a, **_k):
        raise bpmn_service.BpmnGenerationError(LEAK)

    monkeypatch.setattr(bpmn_service, "generate_bpmn_xml", broken)
    sid = client.post("/sessions", json={"user_id": "a@example.com", "title": "a"}).json()["id"]

    with caplog.at_level(logging.ERROR):
        res = client.get(f"/sessions/{sid}/bpmn")

    assert res.status_code == 503
    detail = _assert_shape(res.json(), "bpmn_unavailable")
    _assert_no_leak(res.text)
    assert any(
        detail["trace_id"] in r.getMessage() and LEAK in r.getMessage() for r in caplog.records
    )


@requires_postgres
def test_a_sandbox_missing_a_piece_says_unavailable_and_logs_which(client, monkeypatch) -> None:
    from wizard_api.services import sandbox_runner

    class Unconfigured:
        def __init__(self, *_a, **_k):
            raise sandbox_runner.SandboxNotConfiguredError(
                "no sandbox namespace — set WIZARD_SANDBOX_NAMESPACE"
            )

    monkeypatch.setattr(sandbox_runner, "SandboxRunner", Unconfigured)
    sid = client.post("/sessions", json={"user_id": "a@example.com", "title": "a"}).json()["id"]

    res = client.get(f"/sessions/{sid}/runs/run-1")

    assert res.status_code == 503
    detail = _assert_shape(res.json(), "sandbox_unavailable")
    assert "WIZARD_" not in res.text and "namespace" not in detail["message"]


@requires_postgres
def test_a_refused_upload_keeps_the_reason_the_person_acts_on(client, db_session) -> None:
    from test_poc_endpoints import _session_output_dir, _session_ready_to_generate, _write_poc

    created = _session_ready_to_generate(client, "upload")
    _write_poc(_session_output_dir(db_session, created["id"]))

    res = client.post(
        f"/sessions/{created['id']}/poc/input",
        files={"file": ("empty.txt", b"", "text/plain")},
    )

    assert res.status_code == 422
    detail = _assert_shape(res.json(), "input_rejected")
    assert detail["message"] == "the file is empty"
