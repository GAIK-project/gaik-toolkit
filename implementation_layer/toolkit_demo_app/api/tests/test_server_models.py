"""A signed-in user can switch among the server's own models without a key."""

from __future__ import annotations

import httpx
import pytest
from api.routers import model_settings as router
from api.utils import model_settings as settings
from api.utils.config import (
    get_api_config,
    get_rag_api_config,
    get_transcription_api_config,
    require_vision,
)
from fastapi import HTTPException
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
        "AITTA_API_KEY",
        "AITTA_API_TOKEN",
        "AITTA_TOKEN",
        "AITTA_TRANSCRIPTION_MODEL",
        "AITTA_EMBEDDING_MODEL",
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
    assert models["anthropic_foundry:claude-opus-5-5"].staff
    assert models["anthropic_foundry:claude-opus-5-5"].label == "Claude Opus 5.5"

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
        config = get_rag_api_config()
        observed.append((config["model"], config.get("embedding_model")))
        return {}

    @app.post("/tabular-agent/ask")
    async def tabular():
        observed.append(get_api_config()["model"])
        return {}

    @app.post("/parse")
    async def parse():
        require_vision(get_api_config())
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
    response = await _call(app, "POST", "/tabular-agent/ask", {SERVER: "azure:gpt-6-sol"})
    assert response.status_code == 200
    assert observed == ["gpt-6-luna"]
    # RAG follows a pick whose provider embeds; Claude has no embeddings, so it
    # stays on the default.
    observed.clear()
    await _call(app, "POST", "/rag/index", {SERVER: "azure:gpt-6-sol"})
    await _call(app, "POST", "/rag/index", {SERVER: "anthropic_foundry:claude-haiku-5-5"})
    assert [model for model, _ in observed] == ["gpt-6-sol", "gpt-6-luna"]


@pytest.mark.asyncio
async def test_rag_never_builds_a_collection_on_a_team_model(server_env):
    # A collection is queried later without the team check, so it stays on the default.
    observed = []
    app = _app(observed)
    pick = {SERVER: "azure:gpt-6-astra", TIER: "staff"}
    assert (await _call(app, "POST", "/rag/index", pick)).status_code == 200
    assert [model for model, _ in observed] == ["gpt-6-luna"]


@pytest.fixture
def aitta_env(server_env, monkeypatch):
    monkeypatch.setenv("AITTA_API_KEY", "aitta-token")
    monkeypatch.setattr(settings, "_aitta_status", (0.0, {}))


def test_aitta_models_are_listed_only_with_a_token(server_env, monkeypatch):
    assert not any(m.provider == "aitta" for m in settings.server_models())
    monkeypatch.setenv("AITTA_API_KEY", "aitta-token")
    models = {m.id: m for m in settings.server_models()}
    gemma = models["aitta:google/gemma-4-31b-it"]
    assert (gemma.label, gemma.staff, gemma.audio, gemma.vision) == (
        "Gemma 4 31B",
        False,
        True,
        True,
    )
    assert models["aitta:openai/gpt-oss-120b"].vision is False
    # The server's own model still leads the list.
    assert next(iter(models)) == "azure:gpt-6-luna"


@pytest.mark.asyncio
async def test_env_list_can_mark_a_model_text_only(aitta_env, monkeypatch):
    monkeypatch.setenv("DEMO_SERVER_MODELS", "aitta:some/new-model:text, aitta:other/model")
    models = {m.id: m for m in settings.server_models()}
    assert models["aitta:some/new-model"].vision is False
    assert models["aitta:other/model"].vision is True
    # The mark also stops image requests, not only the menu.
    app = _app([])
    refused = await _call(app, "POST", "/parse", {SERVER: "aitta:some/new-model"})
    assert refused.status_code == 400
    assert (await _call(app, "POST", "/parse", {SERVER: "aitta:other/model"})).status_code == 200


@pytest.mark.asyncio
async def test_an_aitta_pick_keeps_speech_and_embeddings_on_aitta(aitta_env):
    observed = []
    app = _app(observed)

    @app.post("/transcribe")
    async def transcribe():
        speech = get_transcription_api_config()
        observed.append(
            (
                speech["provider"],
                speech["base_url"],
                speech["transcription_model"],
                speech["api_key"],
                speech["model"],
            )
        )
        return {}

    pick = {SERVER: "aitta:google/gemma-4-31b-it"}
    assert (await _call(app, "POST", "/transcribe", pick)).status_code == 200
    # gaik's Transcriber takes OpenAI configs, so Aitta is addressed as an OpenAI base URL.
    assert observed == [
        (
            "openai",
            "https://aitta-api.csc.fi/openai/v1",
            "openai/whisper-large-v3",
            "aitta-token",
            "google/gemma-4-31b-it",
        )
    ]
    observed.clear()
    assert (await _call(app, "POST", "/rag/index", pick)).status_code == 200
    assert observed == [("google/gemma-4-31b-it", "intfloat/multilingual-e5-large")]
    observed.clear()
    assert (await _call(app, "POST", "/pipeline/audio/stream", pick)).status_code == 200
    assert observed == [
        ("transcribe", "google/gemma-4-31b-it"),
        ("extract", "google/gemma-4-31b-it"),
    ]


@pytest.mark.asyncio
async def test_a_text_only_model_is_refused_before_images_are_sent(aitta_env):
    app = _app([])
    ok = await _call(app, "POST", "/parse", {SERVER: "aitta:google/gemma-4-31b-it"})
    assert ok.status_code == 200
    refused = await _call(app, "POST", "/parse", {SERVER: "aitta:openai/gpt-oss-120b"})
    assert refused.status_code == 400
    assert refused.json()["detail"].startswith("gpt-oss 120B cannot read images")
    with pytest.raises(HTTPException):
        require_vision({"provider": "aitta", "model": "openai/gpt-oss-120b"})
    assert require_vision({"provider": "azure", "model": "gpt-6-luna"})


@pytest.mark.asyncio
async def test_the_list_carries_aitta_status_and_vision(aitta_env, monkeypatch):
    monkeypatch.setattr(router, "aitta_model_status", lambda: {"google/gemma-4-31b-it": "running"})
    listed = (await _call(_app([]), "GET", "/model-settings/server", {})).json()
    models = {m["id"]: m for m in listed["models"]}
    assert models["aitta:google/gemma-4-31b-it"]["status"] == "running"
    assert models["aitta:openai/gpt-oss-120b"]["status"] is None
    assert models["aitta:openai/gpt-oss-120b"]["vision"] is False
    assert models["azure:gpt-6-luna"]["status"] is None and models["azure:gpt-6-luna"]["vision"]


@pytest.mark.asyncio
async def test_the_list_names_aittas_speech_and_embedding_models(aitta_env, monkeypatch):
    monkeypatch.setattr(
        router,
        "aitta_model_status",
        lambda: {"openai/whisper-large-v3": "offline", "intfloat/multilingual-e5-large": "running"},
    )
    listed = (await _call(_app([]), "GET", "/model-settings/server", {})).json()
    assert listed["aitta"] == {
        "speech": {"model": "openai/whisper-large-v3", "status": "offline"},
        "embedding": {"model": "intfloat/multilingual-e5-large", "status": "running"},
    }


@pytest.mark.asyncio
async def test_without_aitta_the_list_says_so(server_env):
    listed = (await _call(_app([]), "GET", "/model-settings/server", {})).json()
    assert listed["aitta"] is None


def test_warming_asks_only_for_idle_models_and_not_twice(aitta_env, monkeypatch):
    posted = []

    class Response:
        def raise_for_status(self):
            return None

    monkeypatch.setattr(settings, "_aitta_warmed", 0.0)
    monkeypatch.setattr(
        settings,
        "aitta_model_status",
        lambda: {"openai/whisper-large-v3": "offline", "intfloat/multilingual-e5-large": "running"},
    )
    monkeypatch.setattr(
        settings.httpx, "post", lambda url, **kwargs: posted.append(url) or Response()
    )
    assert settings.warm_aitta_models() == ["openai/whisper-large-v3"]
    assert posted == ["https://aitta-api.csc.fi/model/openai~whisper-large-v3/preload"]
    # Within five minutes a second pick asks for nothing.
    assert settings.warm_aitta_models() == []
    assert len(posted) == 1


def test_e5_embeddings_get_their_prefixes(monkeypatch):
    from api.routers import rag
    from gaik.software_components.RAG.embedder import Embedder

    sent = []

    def fake_embed(self, documents, *, batch_size=None):
        sent.extend(documents)
        return [[0.0] for _ in documents], []

    monkeypatch.setattr(Embedder, "__init__", lambda self, config, model=None: None)
    monkeypatch.setattr(Embedder, "embed", fake_embed)
    embedder = rag._demo_embedder(
        {"provider": "aitta", "embedding_model": "intfloat/multilingual-e5-large"}
    )
    vectors, docs = embedder.embed(["first chunk"])
    assert embedder.embed_query("what?") == [0.0]
    assert sent == ["passage: first chunk", "query: what?"]
    # The stored chunk keeps its own text, without the prefix.
    assert [d.page_content for d in docs] == ["first chunk"] and len(vectors) == 1
    # Aitta refuses an input over E5's 512 tokens, so a long chunk is cut for its vector.
    sent.clear()
    _, long_docs = embedder.embed(["x" * 5000])
    assert len(sent[0]) == len("passage: ") + rag.E5_CHAR_LIMITS[0]
    assert len(long_docs[0].page_content) == 5000


def test_e5_cuts_shorter_when_aitta_refuses_the_batch(monkeypatch):
    from api.routers import rag
    from gaik.software_components.RAG.embedder import Embedder

    lengths = []

    def refuse_long(self, documents, *, batch_size=None):
        lengths.append(len(documents[0]))
        if len(documents[0]) > 400:
            raise RuntimeError("HTTP 500")
        return [[0.0] for _ in documents], []

    monkeypatch.setattr(Embedder, "__init__", lambda self, config, model=None: None)
    monkeypatch.setattr(Embedder, "embed", refuse_long)
    embedder = rag._demo_embedder(
        {"provider": "aitta", "embedding_model": "intfloat/multilingual-e5-large"}
    )
    vectors, _ = embedder.embed(["x" * 5000])
    assert vectors == [[0.0]]
    assert lengths == [len("passage: ") + limit for limit in rag.E5_CHAR_LIMITS]
