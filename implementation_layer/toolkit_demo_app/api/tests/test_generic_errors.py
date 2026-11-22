"""A failed request tells the user an error id, never the exception's own text."""

from __future__ import annotations

import importlib
import logging

import pytest
from api.routers import llm_judge
from api.utils import model_settings as settings
from api.utils.errors import error_detail, public_error
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

RAW = "upstream said: internal-host.example:8443 /srv/app/secret.txt"


def test_the_message_names_an_id_that_the_log_names_too(caplog):
    with caplog.at_level(logging.ERROR, logger="demo_api.errors"):
        message = public_error(RuntimeError(RAW), "The question")
    assert RAW not in message
    assert message.startswith("The question failed on the server (error id ")
    error_id = message.split("error id ")[1].split(")")[0]
    record = caplog.records[-1]
    assert error_id in record.getMessage()
    assert RAW in str(record.exc_info[1])


def test_a_deliberate_http_error_keeps_its_detail():
    assert error_detail(HTTPException(400, "No files provided")) == "No files provided"
    assert settings.provider_error_detail(HTTPException(409, "Schema changed")) == (
        "Schema changed"
    )


def test_a_server_model_error_returns_an_id_not_the_provider_text():
    detail = settings.provider_error_detail(RuntimeError(RAW))
    assert RAW not in detail and "error id" in detail


def test_a_too_large_request_says_so_without_the_provider_text():
    class TooLargeError(Exception):
        status_code = 413

    detail = settings.provider_error_detail(TooLargeError(RAW))
    assert RAW not in detail
    assert detail.startswith("The model's service refused the request as too large.")
    # A 413 the demo raises itself keeps its own detail.
    assert settings.provider_error_detail(HTTPException(413, "File too big")) == "File too big"


def test_a_panel_judge_error_returns_an_id_not_the_judge_text(monkeypatch):
    class Judge:
        def judge_text_pair(self, **_kwargs):
            raise RuntimeError(RAW)

    monkeypatch.setattr(llm_judge, "_make_judge", lambda provider, model: Judge())
    app = FastAPI()
    app.include_router(llm_judge.router, prefix="/llm-judge")
    body = {
        "extracted_text": "a",
        "expected_text": "b",
        "judges": [{"provider": "openai", "model": "m1"}, {"provider": "openai", "model": "m2"}],
    }
    response = TestClient(app).post("/llm-judge/panel/text-pair", json=body)
    assert response.status_code == 502
    for entry in response.json()["detail"]["per_judge"]:
        assert RAW not in entry["error"] and "error id" in entry["error"]


def test_an_unhandled_error_returns_an_id(monkeypatch):
    from api import main

    @main.app.get("/test-unhandled-error")
    async def boom():
        raise RuntimeError(RAW)

    try:
        response = TestClient(main.app, raise_server_exceptions=False).get("/test-unhandled-error")
    finally:
        main.app.router.routes.pop()
    assert response.status_code == 500
    assert RAW not in response.text and "error id" in response.json()["detail"]


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_the_api_docs_are_off_unless_turned_on(monkeypatch, path):
    from api import main

    try:
        monkeypatch.delenv("DEMO_API_DOCS", raising=False)
        # main loads .env.local with override; keep that file out of this check.
        monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
        off = importlib.reload(main)
        assert TestClient(off.app).get(path).status_code == 404
        assert "docs" not in TestClient(off.app).get("/").json()

        monkeypatch.setenv("DEMO_API_DOCS", "true")
        on = importlib.reload(main)
        assert TestClient(on.app).get(path).status_code == 200
    finally:
        monkeypatch.undo()
        importlib.reload(main)


def test_a_component_value_error_is_shown_but_other_errors_get_an_id():
    from api.utils.errors import component_error
    from pydantic import BaseModel, ValidationError

    assert component_error(ValueError("broken.pdf: PDF has no text layer")) == (
        "broken.pdf: PDF has no text layer"
    )
    assert "error id" in component_error(RuntimeError(RAW))

    class Answer(BaseModel):
        n: int

    try:
        Answer(n=RAW)
    except ValidationError as exc:
        message = component_error(exc)
    assert RAW not in message and "error id" in message


def test_on_the_users_own_key_the_log_keeps_the_error_id(caplog):
    token = settings._settings.set(settings.RequestModelSettings("openai", "m", "user-key-123"))
    try:
        with caplog.at_level(logging.ERROR, logger="demo_api.errors"):
            message = public_error(RuntimeError(RAW))
    finally:
        settings._settings.reset(token)
    error_id = message.split("error id ")[1].split(")")[0]
    record = caplog.records[-1]
    assert error_id in record.getMessage()
    assert record.exc_info is None and RAW not in record.getMessage()
