"""Each run leaves one audit line with the user, the route and the outcome, no content."""

from __future__ import annotations

import logging

import pytest
from api.utils.audit import AuditMiddleware
from api.utils.result_owner import USER_HEADER
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    app = FastAPI()

    @app.post("/pipeline/document")
    async def run(payload: dict):
        return {"ok": True}

    @app.get("/pipeline/pdf/{job_id}")
    async def pdf(job_id: str):
        return {"job": job_id}

    @app.get("/status")
    async def status():
        return {"ok": True}

    @app.post("/stream")
    async def stream():
        async def chunks():
            yield b"a"
            yield b"b"

        return StreamingResponse(chunks())

    @app.post("/fails")
    async def fails():
        raise RuntimeError("boom with Matti_Virtanen.pdf")

    app.add_middleware(AuditMiddleware)
    return TestClient(app, raise_server_exceptions=False)


def _lines(caplog):
    return [r.getMessage() for r in caplog.records if r.name == "gaik.audit"]


def test_a_run_is_logged_with_its_user_and_route_template(client, caplog):
    with caplog.at_level(logging.INFO, logger="gaik.audit"):
        client.post(
            "/pipeline/document",
            json={"file": "Matti_Virtanen_lab_results.pdf"},
            headers={USER_HEADER: "6f1c2d3e-0000-4a5b-9c8d-123456789abc"},
        )
        client.get("/pipeline/pdf/job-123?inline=true", headers={USER_HEADER: "u1"})

    first, second = _lines(caplog)
    assert first.startswith(
        "audit user=6f1c2d3e-0000-4a5b-9c8d-123456789abc method=POST "
        "route=/pipeline/document status=200 ms="
    )
    assert "route=/pipeline/pdf/{job_id}" in second and "job-123" not in second
    assert "inline" not in second
    assert all("Matti" not in line for line in (first, second))


def test_a_read_without_a_user_is_not_logged(client, caplog):
    with caplog.at_level(logging.INFO, logger="gaik.audit"):
        client.get("/status")

    assert _lines(caplog) == []


def test_a_run_without_a_user_is_logged_as_dash(client, caplog):
    with caplog.at_level(logging.INFO, logger="gaik.audit"):
        client.post("/pipeline/document", json={})

    (line,) = _lines(caplog)
    assert "user=- method=POST" in line


def test_a_forged_user_value_is_not_written_as_given(client, caplog):
    with caplog.at_level(logging.INFO, logger="gaik.audit"):
        client.post("/pipeline/document", json={}, headers={USER_HEADER: "x user=admin route=/x"})

    (line,) = _lines(caplog)
    assert "user=invalid method=POST" in line and "admin" not in line


def test_a_stream_is_logged_once_when_it_ends(client, caplog):
    with caplog.at_level(logging.INFO, logger="gaik.audit"):
        response = client.post("/stream", headers={USER_HEADER: "u1"})

    assert response.content == b"ab"
    (line,) = _lines(caplog)
    assert "route=/stream status=200 ms=" in line  # ended, not "200-incomplete"


def test_a_failure_is_logged_without_its_message(client, caplog):
    with caplog.at_level(logging.INFO, logger="gaik.audit"):
        client.post("/fails", headers={USER_HEADER: "u1"})

    (line,) = _lines(caplog)
    assert "route=/fails status=error" in line and "Matti" not in line


@pytest.mark.parametrize(
    ("method", "path", "template"),
    [
        ("GET", "/pipeline/pdf/abc123?inline=true", "/pipeline/pdf/{job_id}"),
        ("POST", "/classify", "/classify"),
        ("POST", "/tabular-agent/ask", "/tabular-agent/ask"),
        ("POST", "/report-writer/run", "/report-writer/run"),
        ("POST", "/no/such/route", "unmatched"),
    ],
)
def test_the_real_app_logs_the_full_route_template(caplog, method, path, template):
    from api.main import app

    with caplog.at_level(logging.INFO, logger="gaik.audit"):
        TestClient(app, raise_server_exceptions=False).request(
            method, path, headers={USER_HEADER: "u1"}
        )

    (line,) = _lines(caplog)
    assert f" route={template} status=" in line
    assert "abc123" not in line and "inline" not in line
