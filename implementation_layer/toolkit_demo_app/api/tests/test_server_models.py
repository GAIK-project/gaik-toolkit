"""A signed-in user can switch among the server's own models without a key."""

from __future__ import annotations

import httpx
import pytest
from api.routers import model_settings as router
from api.utils import model_settings as settings
from api.utils.config import get_api_config, get_transcription_api_config
from fastapi import FastAPI

SERVER = settings.SERVER_HEADER.decode()
TIER = settings.TIER_HEADER.decode()


@pytest.fixture
def server_env(monkeypatch):
    for name in (
        "DEMO_SERVER_MODELS",
        "DEMO_LLM_MODEL",
        "DEMO_LLM_PROVIDER",
        "LLM_PROVIDER",
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


def test_lists_only_providers_with_credentials_default_first(server_env, monkeypatch):
    models = {m.id: m for m in settings.server_models()}
    ids = list(models)
    assert ids[0] == "azure:gpt-6-luna"
    assert "anthropic_foundry:claude-haiku-5-5" in ids
    assert not any(i.startswith(("vertex:", "google:")) for i in ids)
    assert models["anthropic_foundry:claude-haiku-5-5"].label == "Claude Haiku 5.5"
    assert models["anthropic_foundry:claude-haiku-5-5"].audio is False
    assert models["azure:gpt-6-astra"].staff and not models["azure:gpt-6-luna"].staff

    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
    monkeypatch.setenv("GOOGLE_PROJECT_ID", "p")
    models = {m.id: m for m in settings.server_models()}
    assert models["vertex:gemini-3.8-flash"].label == "Gemini 3.8 Flash"
    assert models["vertex:gemini-4-argon"].staff


def test_env_list_overrides_and_still_needs_credentials(server_env, monkeypatch):
    monkeypatch.setenv(
        "DEMO_SERVER_MODELS", "azure:gpt-6-sol, vertex:gemini-x, azure:gpt-6-astra:staff"
    )
    models = settings.server_models()
    # The server's own model (AZURE_DEPLOYMENT) always leads, even when unlisted.
    assert [(m.id, m.staff) for m in models] == [
        ("azure:gpt-6-luna", False),
        ("azure:gpt-6-sol", False),
        ("azure:gpt-6-astra", True),
    ]


def test_a_team_model_as_server_default_is_open_to_all(server_env, monkeypatch):
    # With no choice the default runs for anyone, so the list must not lock it.
    monkeypatch.setenv("DEMO_LLM_MODEL", "gpt-6-astra")
    models = settings.server_models()
    assert models[0].id == "azure:gpt-6-astra" and not models[0].staff


def _app(observed):
    app = FastAPI()
    app.add_middleware(settings.ModelSettingsMiddleware)
    app.include_router(router.router, prefix="/model-settings")

    @app.post("/extract")
    async def extract():
        config = get_api_config()
        observed.append((config["provider"], config["model"]))
        return {}

    @app.post("/pipeline/audio/stream")
    async def audio():
        observed.append(("transcribe", get_transcription_api_config()["model"]))
        observed.append(("extract", get_api_config()["model"]))
        return {}

    @app.post("/rag/index")
    async def rag():
        observed.append(get_api_config()["model"])
        return {}

    return app


async def _call(app, method, path, headers):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.request(method, path, headers=headers)


@pytest.mark.asyncio
async def test_picked_server_model_runs_the_request(server_env):
    observed = []
    app = _app(observed)
    assert (await _call(app, "POST", "/extract", {SERVER: "azure:gpt-6-sol"})).status_code == 200
    assert (await _call(app, "POST", "/extract", {})).status_code == 200
    assert observed == [("azure", "gpt-6-sol"), ("azure", "gpt-6-luna")]
    assert settings.request_server_model() is None


@pytest.mark.asyncio
async def test_unknown_server_model_is_refused(server_env):
    observed = []
    response = await _call(_app(observed), "POST", "/extract", {SERVER: "azure:someone-elses"})
    assert response.status_code == 400
    assert observed == []


@pytest.mark.asyncio
async def test_team_models_need_the_staff_tier(server_env):
    observed = []
    app = _app(observed)
    refused = await _call(app, "POST", "/extract", {SERVER: "azure:gpt-6-astra"})
    assert refused.status_code == 403
    allowed = await _call(app, "POST", "/extract", {SERVER: "azure:gpt-6-astra", TIER: "staff"})
    assert allowed.status_code == 200
    assert observed == [("azure", "gpt-6-astra")]

    listed = (await _call(app, "GET", "/model-settings/server", {})).json()
    flags = {m["id"]: m["allowed"] for m in listed["models"]}
    assert flags["azure:gpt-6-luna"] and not flags["azure:gpt-6-astra"]
    listed = (await _call(app, "GET", "/model-settings/server", {TIER: "staff"})).json()
    assert all(m["allowed"] for m in listed["models"])


@pytest.mark.asyncio
async def test_claude_extracts_audio_after_the_server_transcribes(server_env):
    observed = []
    app = _app(observed)
    response = await _call(
        app, "POST", "/pipeline/audio/stream", {SERVER: "anthropic_foundry:claude-haiku-5-5"}
    )
    assert response.status_code == 200
    assert observed == [("transcribe", "gpt-6-luna"), ("extract", "claude-haiku-5-5")]
    # Routes outside model settings keep the server default.
    observed.clear()
    response = await _call(app, "POST", "/rag/index", {SERVER: "azure:gpt-6-sol"})
    assert response.status_code == 200
    assert observed == ["gpt-6-luna"]
