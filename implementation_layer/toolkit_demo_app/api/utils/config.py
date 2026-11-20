"""Shared configuration utilities for the demo API."""

import os
import re

import fitz
from fastapi import HTTPException, UploadFile

from .model_settings import (
    AITTA_BASE_URL,
    aitta_embedding_model,
    aitta_speech_model,
    get_request_api_config,
    model_name,
    reads_images,
    request_model_settings,
    request_reasoning_effort,
    request_server_model,
)

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
    return server_api_config()


def get_transcription_api_config():
    """The config that transcribes audio for this request.

    A server model without speech-to-text (Claude, Gemini) leaves transcription
    to the server's own transcriber; the picked model still does the extraction.
    An Aitta model transcribes with Aitta's Whisper, on the same key.
    """
    chosen = request_server_model()
    if request_model_settings() is None and chosen is not None and not chosen.audio:
        return server_api_config()
    config = get_api_config()
    return aitta_speech_config(config) if on_aitta(config) else config


def on_aitta(config: dict) -> bool:
    return config.get("provider") == "aitta"


def aitta_speech_config(config: dict) -> dict:
    """Aitta's speech-to-text for gaik's Transcriber, from an Aitta chat config.

    The Transcriber takes OpenAI and Azure configs only, so Aitta's
    OpenAI-compatible ``/audio/transcriptions`` is addressed as an OpenAI base
    URL. The chat model stays in the config for the optional transcript fix.
    gaik checks an OpenAI config's address against OpenAI's hosts, so the config
    names the Aitta address it uses, which comes from the server's own Aitta
    configuration, as allowed.
    """
    base_url = config.get("base_url") or AITTA_BASE_URL
    speech = {
        "provider": "openai",
        "use_azure": False,
        "api_key": config["api_key"],
        "base_url": base_url,
        "allowed_endpoint_hosts": [base_url],
        "model": config["model"],
        "transcription_model": aitta_speech_model(),
        "timeout": config.get("timeout") or 600.0,
        "max_retries": 0,
    }
    if config.get("http_client") is not None:
        speech["http_client"] = config["http_client"]
    return speech


def get_rag_api_config() -> dict:
    """The config that embeds and answers for a RAG collection.

    A picked server model applies when its provider also serves embeddings
    (Azure, OpenAI, Aitta). Any other pick leaves RAG on the server default, and
    so does a team-only model: a collection outlives the request that built it,
    and its questions arrive without the team check.
    """
    chosen = request_server_model()
    if chosen is not None and chosen.staff:
        return server_api_config()
    config = get_api_config()
    if on_aitta(config):
        return {**config, "embedding_model": aitta_embedding_model()}
    if config.get("provider") in {"azure", "openai"}:
        return config
    return server_api_config()


def require_vision(config: dict) -> dict:
    """Refuse a text-only model before page images are sent to it.

    Such a model answers an image request with an error, or with text that
    ignores the image, so the demo stops here and says which kind of model to pick.
    """
    chosen = request_server_model()
    # The deployment can mark a model text-only (DEMO_SERVER_MODELS, ":text").
    marked_text_only = (
        chosen is not None and chosen.model == config.get("model") and not chosen.vision
    )
    if marked_text_only or not reads_images(config.get("provider"), config.get("model")):
        raise HTTPException(
            400,
            f"{model_name(config.get('model'))} cannot read images or scanned pages. "
            "Pick a model that reads images in the model menu, such as Gemma 4 31B.",
        )
    return config


def server_api_config():
    """The deployment's own provider and model, ignoring any per-request choice."""
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
    """Use only sampling options supported by the selected model family.

    A reasoning effort picked in the model menu replaces the GPT-6 default below.
    Other models never get it.
    """
    model = str(config.get("model", "")).lower()
    if model.startswith("gpt-6"):
        picked = request_reasoning_effort()
        if picked:
            effort = picked
        # gpt-6.1 and later point releases (gpt-6.2-sol) reject "none"; the first
        # gpt-6 models accept it.
        elif re.match(r"gpt-6\.[1-9]", model):
            effort = "medium"
        else:
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
