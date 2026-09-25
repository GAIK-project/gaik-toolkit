"""Shared configuration utilities for the demo API."""

import os

import fitz
from fastapi import HTTPException, UploadFile

from .model_settings import get_request_api_config, request_model_settings

# File size limits. Audio and video uploads get their own, larger budget: a
# meeting recording is easily tens of megabytes, while the document demos work
# on much smaller files. The audio limit must stay in step with the three layers
# in front of this one, which all allow 50MB — the upload widget
# (FileUpload maxSize), the Next proxy (proxyClientMaxBodySize in next.config.ts)
# and the OpenShift route (proxy-body-size in openshift/route.yaml). When they
# disagree, the upload travels the whole way and is then rejected here.
MAX_FILE_SIZE_MB = 20
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_AUDIO_FILE_SIZE_MB = 50
MAX_AUDIO_FILE_SIZE_BYTES = MAX_AUDIO_FILE_SIZE_MB * 1024 * 1024

# Users keep uploading raw meeting videos, where the audio track is a fraction
# of the size, so the limit error points the way out.
AUDIO_TOO_LARGE_DETAIL = (
    f"File too large. Maximum size is {MAX_AUDIO_FILE_SIZE_MB}MB. "
    "For a video file, extract the audio track first: "
    "ffmpeg -i video.mp4 -vn -ac 1 -ar 16000 -b:a 64k audio.mp3"
)

# Vision parser page limit (CPU environment in CSC Rahti)
MAX_VISION_PAGES = 10

# Shared OpenAI settings for the demo website. Passing ``temperature=None``
# omits that unsupported parameter for newer models while ``reasoning_effort``
# remains available to models that accept it.
MODEL = os.getenv("DEMO_LLM_MODEL", "gpt-6-luna")
MODEL_OPTIONS = {
    "temperature": None,
    "reasoning_effort": "none",
}


async def validate_file_size(file: UploadFile) -> bytes:
    """Validate file size and return content if valid."""
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB",
        )
    await file.seek(0)
    return content


async def validate_audio_file_size(file: UploadFile) -> bytes:
    """Validate an audio/video upload against the audio limit and return content."""
    content = await file.read()
    if len(content) > MAX_AUDIO_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail=AUDIO_TOO_LARGE_DETAIL)
    await file.seek(0)
    return content


def get_api_config():
    """Resolve tab-only settings first, then the deployment's provider and model."""
    request_config = get_request_api_config()
    if request_config is not None:
        return request_config

    from gaik.software_components.llm import get_llm_config

    provider = os.getenv("DEMO_LLM_PROVIDER") or os.getenv("LLM_PROVIDER")
    if not provider:
        if os.getenv("AZURE_API_KEY"):
            provider = "azure"
        elif os.getenv("OPENAI_API_KEY"):
            provider = "openai"
        elif any(os.getenv(name) for name in ("AITTA_API_KEY", "AITTA_API_TOKEN", "AITTA_TOKEN")):
            provider = "aitta"
        else:
            raise HTTPException(
                503, "Configure a server model provider or use Model settings with your own key."
            )
    overrides = {}
    if os.getenv("DEMO_LLM_MODEL"):
        overrides["model"] = os.environ["DEMO_LLM_MODEL"]
    try:
        return get_llm_config(provider, **overrides)
    except ValueError:
        raise HTTPException(503, "The server model provider is not configured correctly.") from None


def get_model_options(config: dict, *, schema: bool = False) -> dict:
    """Use only sampling options supported by the selected model family."""
    model = str(config.get("model", "")).lower()
    if model.startswith("gpt-6"):
        effort = "low" if "astra" in model else "none"
        return {"temperature": None, "reasoning_effort": effort}
    if request_model_settings() is not None or config.get("provider") not in {
        None,
        "openai",
        "azure",
    }:
        return {"temperature": None, "reasoning_effort": None}
    if schema:
        return {"temperature": 0.0, "reasoning_effort": None}
    return {"temperature": None, "reasoning_effort": "medium"}


def validate_vision_page_limit(file_path: str, suffix: str, parser_type: str) -> None:
    """Raise HTTPException if a vision parser PDF exceeds the page limit."""
    if parser_type not in {"vision", "vision_plus"} or suffix != ".pdf":
        return

    with fitz.open(file_path) as document:
        page_count = document.page_count

    if page_count > MAX_VISION_PAGES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{parser_type} parser supports at most {MAX_VISION_PAGES} pages per PDF. "
                f"Received {page_count} pages."
            ),
        )
