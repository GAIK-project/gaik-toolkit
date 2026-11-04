"""A signed-in user can switch among the server's own models without a key."""

from __future__ import annotations

import httpx
import pytest
from api.utils import model_settings as settings
from api.utils.config import get_api_config
from fastapi import FastAPI

SERVER = settings.SERVER_HEADER.decode()


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
        "GOOGLE_APPLICATION_CREDENTIALS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AZURE_API_KEY", "server-key")
    monkeypatch.setenv("AZURE_ENDPOINT", "https://server.openai.azure.com")
    monkeypatch.setenv("AZURE_DEPLOYMENT", "gpt-6-luna")
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_API_KEY", "foundry-key")
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_RESOURCE", "server-foundry")
    monkeypatch.setenv("ANTHROPIC_DEFAULT_SONNET_MODEL", "claude-sonnet-5-5")


def test_lists_only_providers_with_credentials_default_first(server_env, monkeypatch):
    ids = [m.id for m in settings.server_models()]
    assert ids[0] == "azure:gpt-6-luna"
    assert "azure:gpt-6-sol" in ids
    assert "anthropic_foundry:claude-sonnet-5-5" in ids
    assert not any(i.startswith(("google:", "vertex:", "anthropic:")) for i in ids)
    claude = next(m for m in settings.server_models() if m.provider == "anthropic_foundry")
    assert claude.label == "Claude Sonnet 5.5"
    assert claude.audio is False

    monkeypatch.delenv("ANTHROPIC_FOUNDRY_API_KEY")
    monkeypatch.setenv("GOOGLE_API_KEY", "g")
    ids = [m.id for m in settings.server_models()]
    assert not any(i.startswith("anthropic") for i in ids)
    assert "google:gemini-2.5-flash" in ids


def test_env_list_overrides_and_still_needs_credentials(server_env, monkeypatch):
    monkeypatch.setenv("DEMO_SERVER_MODELS", "azure:gpt-6-sol, google:gemini-x, azure:gpt-6-luna")
    assert [m.id for m in settings.server_models()] == ["azure:gpt-6-sol", "azure:gpt-6-luna"]


def _app(observed):
    app = FastAPI()
    app.add_middleware(settings.ModelSettingsMiddleware)

    @app.post("/extract")
    async def extract():
        config = get_api_config()
        observed.append((config["provider"], config["model"]))
        return {}

    @app.post("/pipeline/audio/stream")
    async def audio():
        observed.append("audio-ran")
        return {}

    @app.post("/rag/index")
    async def rag():
        observed.append(get_api_config()["model"])
        return {}

    return app


async def _post(app, path, headers):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.post(path, headers=headers)


@pytest.mark.asyncio
async def test_picked_server_model_runs_the_request(server_env):
    observed = []
    app = _app(observed)
    response = await _post(app, "/extract", {SERVER: "azure:gpt-6-sol"})
    assert response.status_code == 200
    response = await _post(app, "/extract", {})
    assert response.status_code == 200
    assert observed == [("azure", "gpt-6-sol"), ("azure", "gpt-6-luna")]
    assert settings.request_server_model() is None


@pytest.mark.asyncio
async def test_unknown_server_model_is_refused(server_env):
    observed = []
    response = await _post(_app(observed), "/extract", {SERVER: "azure:someone-elses"})
    assert response.status_code == 400
    assert observed == []


@pytest.mark.asyncio
async def test_claude_is_refused_on_audio_and_ignored_on_other_routes(server_env):
    observed = []
    app = _app(observed)
    response = await _post(
        app, "/pipeline/audio/stream", {SERVER: "anthropic_foundry:claude-sonnet-5-5"}
    )
    assert response.status_code == 400
    assert "transcribe" in response.json()["detail"]
    # Routes outside model settings keep the server default.
    response = await _post(app, "/rag/index", {SERVER: "azure:gpt-6-sol"})
    assert response.status_code == 200
    assert observed == ["gpt-6-luna"]
