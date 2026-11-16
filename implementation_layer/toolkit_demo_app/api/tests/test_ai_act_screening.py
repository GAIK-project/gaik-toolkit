"""The AI Act screening endpoint runs the skill's own checker over a screening."""

from __future__ import annotations

import copy

import pytest
from api.routers import ai_act_screening as route
from fastapi import FastAPI
from fastapi.testclient import TestClient

DESCRIPTION = "We use an AI tool to summarise our team meetings for the attendees."
ANSWER = "Only our own staff use it."

INTAKE = {
    "intake_version": "1.0",
    "use_case_name": "Meeting summariser",
    "mode": "existing",
    "lifecycle_stage": "production",
    "description": DESCRIPTION,
    "documents": [],
    "questions": [
        {"id": "Q1", "batch": "B", "question": "Who uses it?", "answer": ANSWER},
    ],
}


def _finding(fid: str, status: str, citation: str, quote: dict) -> dict:
    return {
        "id": fid,
        "question": "q",
        "status": status,
        "answer": "a",
        "evidence": [quote],
        "citations": [{"ref": citation}],
        "reasoning": "r",
        "confidence": "medium",
    }


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(route.router, prefix="/ai-act-screening")
    return TestClient(app)


def test_the_skill_folder_and_checker_are_found() -> None:
    assert (route._skill_dir() / "scripts" / "check_screening.py").is_file()


def test_a_broken_screening_is_reported_and_not_returned(client) -> None:
    response = client.post(
        "/ai-act-screening/check", json={"intake": INTAKE, "screening": {"summary": {}}}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["errors"]
    assert body["screening"] is None


def test_an_invented_quote_is_caught(client) -> None:
    quote = {"source": "description", "locator": "description", "quote": "Nobody wrote this."}
    screening = {"findings": [_finding("F1", "yes", "Art. 3(1)", quote)]}
    body = client.post(
        "/ai-act-screening/check", json={"intake": INTAKE, "screening": screening}
    ).json()
    assert body["ok"] is False
    assert any("quote" in e.lower() for e in body["errors"])


def test_the_server_stamps_the_values_the_model_cannot_know(client) -> None:
    body = client.post("/ai-act-screening/check", json={"intake": INTAKE, "screening": {}}).json()
    # Still an error (the screening is empty), but never about the stamped fields.
    joined = " ".join(body["errors"])
    assert "intake_sha256" not in joined
    assert "reference_last_verified" not in joined
    assert "screening_version" not in joined


def test_the_request_is_not_mutated_between_calls(client) -> None:
    before = copy.deepcopy(INTAKE)
    client.post("/ai-act-screening/check", json={"intake": INTAKE, "screening": {}})
    assert INTAKE == before


def test_an_oversized_screening_is_refused(client) -> None:
    big = {"x": "y" * (route.MAX_JSON_BYTES + 10)}
    response = client.post("/ai-act-screening/check", json={"intake": INTAKE, "screening": big})
    assert response.status_code == 413


def test_a_valid_screening_passes_and_is_returned_stamped(client) -> None:
    from api.utils.ai_act_sample import sample

    intake, screening = sample()
    body = client.post(
        "/ai-act-screening/check", json={"intake": intake, "screening": screening}
    ).json()
    assert body["ok"] is True, body["errors"]
    assert body["screening"]["summary"]["risk_class"] == "minimal"
    assert len(body["screening"]["intake_sha256"]) == 64


def test_a_changed_class_that_the_findings_do_not_support_is_refused(client) -> None:
    from api.utils.ai_act_sample import sample

    intake, screening = sample()
    screening["summary"]["risk_class"] = "high"
    body = client.post(
        "/ai-act-screening/check", json={"intake": intake, "screening": screening}
    ).json()
    assert body["ok"] is False
    assert body["screening"] is None
