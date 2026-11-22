"""A route runs only the models it offers, and team-only models only for the team."""

from __future__ import annotations

import json

import httpx
import pytest
from api.routers import llm_judge, report_writer, vision_extractor
from api.utils import model_allow_list as allow
from api.utils import model_settings as settings
from fastapi import FastAPI, HTTPException

TIER = settings.TIER_HEADER.decode()


@pytest.fixture
def server_env(monkeypatch):
    for name in (
        "DEMO_SERVER_MODELS",
        "DEMO_LLM_MODEL",
        "DEMO_LLM_PROVIDER",
        "LLM_PROVIDER",
        "DEMO_EXTRA_CHAT_MODELS",
        "DEMO_TRANSCRIPTION_MODELS",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        "GOOGLE_PROJECT_ID",
        "GOOGLE_CLOUD_PROJECT",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AZURE_API_KEY", "server-key")
    monkeypatch.setenv("AZURE_ENDPOINT", "https://server.openai.azure.com")
    monkeypatch.setenv("AZURE_DEPLOYMENT", "gpt-6-luna")
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_API_KEY", "foundry-key")
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_RESOURCE", "server-foundry")


def _app(*routers: tuple[object, str]) -> FastAPI:
    app = FastAPI()
    app.add_middleware(settings.ModelSettingsMiddleware)
    for router, prefix in routers:
        app.include_router(router.router, prefix=prefix)
    return app


async def _send(app, method, path, staff=False, **kwargs):
    headers = {TIER: "staff"} if staff else {}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.request(method, path, headers=headers, **kwargs)


def test_a_model_the_route_does_not_offer_is_refused(server_env):
    with pytest.raises(HTTPException) as refused:
        allow.check_model("any-deployment", ["gpt-6-luna"])
    assert refused.value.status_code == 422
    allow.check_model("gpt-6-luna", ["gpt-6-luna"])
    allow.check_model(None, ["gpt-6-luna"])  # the route's own default


def test_a_team_only_model_needs_the_team_tier(server_env):
    assert "gpt-6-astra" in allow.team_only_models()
    offered = allow.chat_models()
    assert offered[0] == "gpt-6-luna" and "gpt-6-astra" in offered
    # The report demos run on the server's provider only.
    assert not any(m.startswith("claude-") for m in offered)
    with pytest.raises(HTTPException) as refused:
        allow.check_model("gpt-6-astra", offered)
    assert refused.value.status_code == 403
    token = settings._staff.set(True)
    try:
        allow.check_model("gpt-6-astra", offered)
    finally:
        settings._staff.reset(token)


def test_a_team_only_model_stays_so_without_its_providers_credentials(server_env, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_FOUNDRY_API_KEY")
    assert "claude-opus-5-5" in allow.team_only_models()
    assert "claude-sonnet-5-5" not in allow.team_only_models()  # open to everyone
    monkeypatch.setenv("DEMO_SERVER_MODELS", "azure:gpt-6-sol,azure:gpt-6-astra")
    team_only = allow.team_only_models()
    assert "claude-opus-5-5" in team_only  # not listed: the built-in flag holds
    assert "gpt-6-astra" not in team_only  # listed without :staff
    assert "gpt-6-luna" not in team_only  # the server's own model


def test_the_report_demos_keep_their_defaults(server_env):
    assert "gpt-5.5-deployment" in allow.chat_models()  # Report Writer review default
    assert {"gpt-4o-transcribe", "whisper-1"} <= set(allow.transcription_models())


@pytest.mark.asyncio
async def test_a_judge_refuses_a_model_the_demo_does_not_offer(server_env, monkeypatch):
    def must_not_run(*args, **kwargs):
        raise AssertionError("no judge may be built for a refused model")

    monkeypatch.setattr(llm_judge, "_resolve_provider", must_not_run)
    app = _app((llm_judge, "/llm-judge"))
    body = {"extracted_text": "a", "expected_text": "b", "model": "any-deployment"}
    response = await _send(app, "POST", "/llm-judge/text-pair", json=body)
    assert response.status_code == 422
    panel = {
        "extracted_text": "a",
        "expected_text": "b",
        "judges": [
            {"provider": "openai", "model": "any-deployment"},
            {"provider": "openai", "model": "gpt-6-luna"},
        ],
    }
    response = await _send(app, "POST", "/llm-judge/panel/text-pair", json=panel)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_the_vision_catalogue_lists_team_only_models_for_the_team(server_env):
    app = _app((vision_extractor, "/extract-vision"))
    everyone = (await _send(app, "GET", "/extract-vision/models")).json()["models"]
    team = (await _send(app, "GET", "/extract-vision/models", staff=True)).json()["models"]
    # Sonnet and Haiku are open to everyone; the vision list has no team-only Claude model.
    assert "claude-sonnet-5-5" in team["claude"]
    assert "claude-sonnet-5-5" in everyone["claude"]
    assert "claude-haiku-5-5" in everyone["claude"]


@pytest.mark.asyncio
async def test_a_report_run_refuses_a_writer_model_the_demo_does_not_offer(server_env):
    app = _app((report_writer, "/report-writer"))
    config = {"writer_options": {"model": "any-deployment"}}
    response = await _send(
        app,
        "POST",
        "/report-writer/run",
        data={"config": json.dumps(config)},
        files={"files": ("notes.txt", b"text")},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "writer model" in detail and "gpt-6-luna" in detail
    assert "gpt-6-astra" not in detail  # team-only names are listed for the team only


@pytest.mark.asyncio
async def test_the_model_list_names_what_the_report_fields_accept(server_env, monkeypatch):
    """The report demos' model fields offer the names their routes check, so a name
    picked there is never refused as unknown; team-only names only for the team."""
    from api.routers import model_settings

    monkeypatch.setenv("DEMO_EXTRA_CHAT_MODELS", "extra-deployment")
    app = _app((model_settings, "/model-settings"))
    everyone = (await _send(app, "GET", "/model-settings/server")).json()["report_models"]
    team = (await _send(app, "GET", "/model-settings/server", staff=True)).json()["report_models"]

    assert team == {"chat": allow.chat_models(), "transcription": allow.transcription_models()}
    assert everyone["chat"][0] == "gpt-6-luna" and "extra-deployment" in everyone["chat"]
    assert "gpt-6-astra" in team["chat"] and "gpt-6-astra" not in everyone["chat"]
    assert set(everyone["chat"]) == set(team["chat"]) - allow.team_only_models()
    assert "gpt-4o-transcribe" in everyone["transcription"]
    for name in everyone["chat"]:
        allow.check_model(name, allow.chat_models())  # accepted outside the team too
