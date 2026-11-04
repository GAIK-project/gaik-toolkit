"""Small authenticated-through-Next connectivity check for model settings."""

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

try:
    from utils.config import get_api_config
    from utils.model_settings import request_model_settings
except ImportError:
    from api.utils.config import get_api_config
    from api.utils.model_settings import request_model_settings

try:
    from utils.model_settings import server_models
except ImportError:
    from api.utils.model_settings import server_models

router = APIRouter()


@router.get("/server")
async def list_server_models():
    """Models the deployment runs on its own credentials, default first."""
    models = server_models()
    return {
        "default": models[0].id if models else None,
        "models": [
            {
                "id": m.id,
                "provider": m.provider,
                "model": m.model,
                "label": m.label,
                "audio": m.audio,
            }
            for m in models
        ],
    }


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
