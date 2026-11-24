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
        "DEMO_OPEN_MODELS",
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
    assert allow.is_team_only("gpt-6-astra")
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
    assert allow.is_team_only("claude-opus-5-5")
    assert allow.is_team_only("claude-sonnet-5-5")  # only GPT-6 Luna and Haiku are open
    assert not allow.is_team_only("claude-haiku-5-5")
    assert allow.is_team_only("gpt-5.6-terra")  # not in any list: for the team too
    monkeypatch.setenv("DEMO_SERVER_MODELS", "azure:gpt-6-sol,azure:gpt-6-astra")
    assert allow.is_team_only("claude-opus-5-5")  # not listed: not open
    assert not allow.is_team_only("gpt-6-astra")  # listed without :staff
    assert not allow.is_team_only("gpt-6-luna")  # the server's own model


def test_speech_models_are_not_limited(server_env):
    for name in allow.transcription_models():
        assert not allow.is_team_only(name)


def test_the_open_models_can_be_set_on_the_deployment(server_env, monkeypatch):
    monkeypatch.setenv("DEMO_OPEN_MODELS", "gpt-6-luna, gpt-6-sol")
    assert not allow.is_team_only("gpt-6-sol")
    assert allow.is_team_only("claude-haiku-5-5")


def test_a_team_model_as_server_default_gives_way_outside_the_team(server_env, monkeypatch):
    """With DEMO_LLM_MODEL on a team model, a run without a choice is on GPT-6 Luna
    outside the team and on the deployment's model for the team."""
    from api.utils.config import get_api_config

    monkeypatch.setenv("DEMO_LLM_MODEL", "gpt-6-sol")
    assert get_api_config()["model"] == "gpt-6-luna"
    assert allow.chat_models()[0] == "gpt-6-luna"
    assert allow.is_team_only("gpt-6-sol")
    token = settings._staff.set(True)
    try:
        assert get_api_config()["model"] == "gpt-6-sol"
        assert allow.chat_models()[0] == "gpt-6-sol"
    finally:
        settings._staff.reset(token)


def test_a_team_default_stays_where_the_provider_has_no_open_model(server_env, monkeypatch):
    from api.utils.config import get_api_config

    monkeypatch.setenv("DEMO_LLM_MODEL", "gpt-6-sol")
    monkeypatch.setenv("DEMO_OPEN_MODELS", "claude-haiku-5-5")
    # Nothing open runs on Azure, so the deployment's own model runs for everyone.
    assert get_api_config()["model"] == "gpt-6-sol"
    assert not allow.is_team_only("gpt-6-sol")


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
    # Outside the team: GPT-6 Luna and Claude Haiku only.
    assert everyone["openai"] == ["gpt-6-luna"]
    assert everyone["claude"] == ["claude-haiku-5-5"]
    assert "claude-sonnet-5-5" in team["claude"]
    assert {"gpt-6-sol", "gpt-5.6-terra"} <= set(team["openai"])


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
    assert everyone["chat"][0] == "gpt-6-luna"
    # A further deployment is for the team, like any model outside the open list.
    assert "extra-deployment" in team["chat"] and "extra-deployment" not in everyone["chat"]
    assert "gpt-6-astra" in team["chat"] and "gpt-6-astra" not in everyone["chat"]
    assert set(everyone["chat"]) == {m for m in team["chat"] if not allow.is_team_only(m)}
    assert "gpt-4o-transcribe" in everyone["transcription"]
    for name in everyone["chat"]:
        allow.check_model(name, allow.chat_models())  # accepted outside the team too


def test_a_claude_judge_runs_through_foundry(server_env, monkeypatch):
    """The panel's Claude judge: Foundry when the deployment has no Anthropic key, and
    only the open Claude model outside the team."""
    import gaik.software_components.validators as validators

    built = []

    class FakeJudge:
        def __init__(self, *args, config=None, model=None, **kwargs):
            built.append((config["provider"] if config else kwargs.get("model_provider"), model))

    monkeypatch.setattr(validators, "LLMJudge", FakeJudge)
    llm_judge._make_judge("anthropic", "claude-haiku-5-5")
    assert built == [("anthropic_foundry", "claude-haiku-5-5")]
    with pytest.raises(HTTPException) as refused:
        llm_judge._make_judge("anthropic", "claude-sonnet-5-5")
    assert refused.value.status_code == 403


def test_csc_aitta_models_are_open(server_env, monkeypatch):
    # CSC hosts them at no cost: open whatever DEMO_OPEN_MODELS says.
    assert not allow.is_team_only("google/gemma-4-31b-it")
    assert not allow.is_team_only("openai/gpt-oss-120b")
    monkeypatch.setenv("DEMO_OPEN_MODELS", "gpt-6-luna")
    assert not allow.is_team_only("google/gemma-4-31b-it")


def test_a_judge_with_no_model_runs_an_open_one_outside_the_team(server_env, monkeypatch):
    """gaik's Foundry default is Claude Sonnet: a judge with no model named must not
    run it outside the team."""
    import gaik.software_components.validators as validators

    built = []

    class FakeJudge:
        def __init__(self, *args, config=None, model=None, **kwargs):
            built.append(model)

    monkeypatch.setattr(validators, "LLMJudge", FakeJudge)
    llm_judge._make_judge("anthropic", None)
    assert built == ["claude-haiku-5-5"]
    monkeypatch.setenv("GOOGLE_API_KEY", "g")
    with pytest.raises(HTTPException) as refused:
        llm_judge._make_judge("google", None)  # no open Gemini model
    assert refused.value.status_code == 403


def test_a_judge_with_no_model_runs_the_server_model(server_env, monkeypatch):
    """The model menu says the server default runs the judge: GPT-6 Sol for the team,
    the open GPT-6 Luna outside it, not gaik's AZURE_DEPLOYMENT."""
    import gaik.software_components.validators as validators

    built = []

    class FakeJudge:
        def __init__(self, *args, config=None, model=None, **kwargs):
            built.append(model)

    monkeypatch.setattr(validators, "LLMJudge", FakeJudge)
    monkeypatch.setenv("DEMO_LLM_MODEL", "gpt-6-sol")
    # The pages ask for "openai", which runs on the deployment's Azure.
    for provider in ("openai", "azure"):
        llm_judge._make_judge(provider, None)
        token = settings._staff.set(True)
        try:
            llm_judge._make_judge(provider, None)
        finally:
            settings._staff.reset(token)
    assert built == ["gpt-6-luna", "gpt-6-sol"] * 2


def test_rag_collections_are_built_on_an_open_model_for_the_team_too(server_env, monkeypatch):
    """The example collections are shared, so the team's default (GPT-6 Sol) must not
    build one that everyone then queries."""
    from api.utils.config import get_rag_api_config

    monkeypatch.setenv("DEMO_LLM_MODEL", "gpt-6-sol")
    token = settings._staff.set(True)
    try:
        assert get_rag_api_config()["model"] == "gpt-6-luna"
    finally:
        settings._staff.reset(token)


def test_claude_is_not_offered_without_claude_credentials(server_env, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_FOUNDRY_API_KEY")
    assert vision_extractor._offered_models("claude") == ()
