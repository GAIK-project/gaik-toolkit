"""Shared configuration utilities for the demo API."""

import os

import fitz
from fastapi import HTTPException, UploadFile

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
MODEL = "gpt-5.4"
MODEL_OPTIONS = {
    "temperature": None,
    "reasoning_effort": "medium",
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
    """
    Get OpenAI configuration from environment variables.

    Checks for either Azure or standard OpenAI API keys and returns
    the appropriate configuration.

    Raises:
        HTTPException: If neither AZURE_API_KEY nor OPENAI_API_KEY is set.
    """
    use_azure = bool(os.getenv("AZURE_API_KEY"))
    if not use_azure and not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail=(
                "Set AZURE_API_KEY or OPENAI_API_KEY. "
                "For Gemini, set OPENAI_API_KEY=<google-api-key> and "
                "OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/"
            ),
        )

    from gaik.software_components.config import get_openai_config

    config = get_openai_config(use_azure=use_azure)
    config["model"] = MODEL
    return config


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
