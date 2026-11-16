"""Small authenticated-through-Next connectivity check for model settings."""

import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

try:
    from utils.config import get_api_config
    from utils.model_settings import request_model_settings
except ImportError:
    from api.utils.config import get_api_config
    from api.utils.model_settings import request_model_settings

try:
    from utils.model_settings import (
        aitta_embedding_model,
        aitta_model_status,
        aitta_speech_model,
        is_staff,
        server_models,
        warm_aitta_models,
    )
except ImportError:
    from api.utils.model_settings import (
        aitta_embedding_model,
        aitta_model_status,
        aitta_speech_model,
        is_staff,
        server_models,
        warm_aitta_models,
    )

router = APIRouter()


@router.get("/server")
async def list_server_models(request: Request):
    """Models the deployment runs on its own credentials, default first.

    ``allowed`` is false for a team-only model when the user is not on the team.
    """
    staff = is_staff(request.scope)
    models = server_models()
    aitta = (
        await run_in_threadpool(aitta_model_status)
        if any(m.provider == "aitta" for m in models)
        else {}
    )
    has_aitta = any(m.provider == "aitta" for m in models)
    return {
        # Where this deployment's own models run, in the deployment's words
        # (DEMO_SERVER_MODELS_NOTE). It depends on the cloud resources behind the
        # keys, which the code cannot know, so there is no default.
        "note": (os.getenv("DEMO_SERVER_MODELS_NOTE") or "").strip()[:300] or None,
        # With an Aitta model picked, these transcribe and embed. An idle one
        # starts on its first request, which can take minutes.
        "aitta": {
            "speech": {
                "model": aitta_speech_model(),
                "status": aitta.get(aitta_speech_model()),
            },
            "embedding": {
                "model": aitta_embedding_model(),
                "status": aitta.get(aitta_embedding_model()),
            },
        }
        if has_aitta
        else None,
        "default": models[0].id if models else None,
        "models": [
            {
                "id": m.id,
                "provider": m.provider,
                "model": m.model,
                "label": m.label,
                "audio": m.audio,
                "vision": m.vision,
                # Aitta only: "running", or "offline" for a model that starts on
                # the first request (minutes). None when the catalog did not answer.
                "status": aitta.get(m.model) if m.provider == "aitta" else None,
                "staff": m.staff,
                "allowed": staff or not m.staff,
            }
            for m in models
        ],
    }


@router.post("/aitta/warm")
async def warm_aitta():
    """Start Aitta's idle speech and embedding models ahead of the first run."""
    return {"asked": await run_in_threadpool(warm_aitta_models)}


@router.post("/test")
async def test_connection():
    from gaik.software_components.llm import create_llm_client

    if request_model_settings() is None:
        raise HTTPException(400, "Enter your provider settings before testing the connection.")
    config = get_api_config()
    try:
        client = create_llm_client(config)
        await run_in_threadpool(
            client.chat,
            [{"role": "user", "content": "Reply with the single word OK."}],
            max_completion_tokens=256,
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            502,
            "Connection failed. Check the key, model or deployment, and endpoint. "
            "Aitta may need time to start the model.",
        ) from None
    return {"provider": config["provider"], "model": config["model"], "status": "ok"}
