"""Report runs reach the API only from the web app's route handlers once a run token is set,
and the Report Writer's limits hold in the API as well as on the page."""

from __future__ import annotations

import json

import pytest
from api.routers import (
    knowledge_curator,
    knowledge_synthesis,
    report_writer,
    report_writer_v2,
    source_normalizer,
)
from api.utils import report_runs
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROUTERS = {
    "/report-writer": report_writer.router,
    "/report-writer-v2": report_writer_v2.router,
    "/source-normalizer": source_normalizer.router,
    "/knowledge-curator": knowledge_curator.router,
    "/knowledge-synthesis": knowledge_synthesis.router,
}


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    for prefix, router in ROUTERS.items():
        app.include_router(router, prefix=prefix)
    return TestClient(app)


@pytest.mark.parametrize("prefix", sorted(ROUTERS))
def test_a_run_without_the_token_is_refused_when_one_is_set(client, monkeypatch, prefix):
    monkeypatch.setenv("REPORT_RUN_TOKEN", "sample-run-token")
    for headers in ({}, {report_runs.REPORT_RUN_HEADER: "another-value"}):
        response = client.post(f"{prefix}/run", headers=headers)
        assert response.status_code == 403
        assert response.json() == {"detail": "Start this run from the demo's page."}


@pytest.mark.parametrize("prefix", sorted(ROUTERS))
def test_a_run_with_the_token_reaches_the_route(client, monkeypatch, prefix):
    monkeypatch.setenv("REPORT_RUN_TOKEN", "sample-run-token")
    response = client.post(
        f"{prefix}/run", headers={report_runs.REPORT_RUN_HEADER: "sample-run-token"}
    )
    # No form sent: the route's own validation answers, not the token check.
    assert response.status_code == 422


@pytest.mark.parametrize("prefix", sorted(ROUTERS))
def test_without_a_token_runs_are_accepted_as_before(client, monkeypatch, prefix):
    monkeypatch.delenv("REPORT_RUN_TOKEN", raising=False)
    assert client.post(f"{prefix}/run").status_code == 422


def _run(client, config, files=(("files", ("notes.md", b"notes")),)):
    return client.post("/report-writer/run", data={"config": json.dumps(config)}, files=files)


def test_the_report_writer_refuses_more_sections_than_the_limit(client, monkeypatch):
    monkeypatch.delenv("REPORT_RUN_TOKEN", raising=False)
    monkeypatch.setenv("REPORT_WRITER_MAX_SECTIONS", "2")
    response = _run(client, {"sections": [{"title": str(i)} for i in range(3)]})
    assert response.status_code == 400
    assert response.json() == {"detail": "Too many sections (max 2)"}


def test_the_report_writer_refuses_uploads_over_the_limit(client, monkeypatch):
    monkeypatch.delenv("REPORT_RUN_TOKEN", raising=False)
    monkeypatch.setenv("REPORT_WRITER_MAX_UPLOAD_MB", "1")
    big = ("files", ("big.md", b"x" * (1024 * 1024 + 1)))
    response = _run(client, {"sections": []}, files=(big,))
    assert response.status_code == 413
    assert response.json() == {"detail": "Uploads exceed the 1 MB limit"}


def test_the_report_writer_refuses_a_config_that_is_not_an_object(client, monkeypatch):
    monkeypatch.delenv("REPORT_RUN_TOKEN", raising=False)
    assert _run(client, ["not", "an", "object"]).status_code == 400


@pytest.mark.parametrize(
    ("requested", "expected"),
    [(None, 500), (100, 100), (10_000, 500), (0, 500), (-5, 500), (True, 500), ("9", 500)],
)
def test_the_evidence_ceiling_is_capped_at_the_limit(monkeypatch, requested, expected):
    monkeypatch.setenv("REPORT_WRITER_MAX_EVIDENCE_CHARS", "500")
    config: dict = {"sections": []}
    if requested is not None:
        config["max_evidence_chars"] = requested
    report_writer._apply_limits(config, [])
    assert config["max_evidence_chars"] == expected


@pytest.mark.parametrize("name", ["costs.xls", "COSTS.XLS"])
def test_the_report_writer_refuses_an_xls_upload_before_any_source_is_read(
    client, monkeypatch, name
):
    monkeypatch.delenv("REPORT_RUN_TOKEN", raising=False)
    files = (("files", ("notes.md", b"notes")), ("files", (name, b"\xd0\xcf\x11\xe0rest")))
    response = _run(client, {"sections": [{"title": "Summary"}]}, files=files)
    assert response.status_code == 415
    assert response.json() == {
        "detail": f"{name}: the old Excel format .xls is not supported; save it as .xlsx"
    }
    assert ".xls" not in report_writer._SUPPORTED_EXTS
