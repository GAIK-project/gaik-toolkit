"""Text-to-speech router."""

from __future__ import annotations

import asyncio
import base64

from fastapi import APIRouter, Form, HTTPException
from pydantic import BaseModel

try:
    from utils.config import get_api_config
except ImportError:
    from api.utils.config import get_api_config

router = APIRouter()

SUPPORTED_LANGUAGES = {"fi", "en"}
SUPPORTED_VOICES = {
    "alloy",
    "echo",
    "fable",
    "nova",
    "onyx",
    "shimmer",
}
MAX_TEXT_LENGTH = 1000


class TextToSpeechResponse(BaseModel):
    filename: str
    job_id: str
    model: str
    voice: str
    language: str
    response_format: str
    content_type: str
    character_count: int
    audio_base64: str


def _retry_after(exc: Exception) -> float | None:
    """Seconds to wait when the speech deployment is rate limited (HTTP 429), else None."""
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if status != 429 and "429" not in str(exc):
        return None
    try:
        return min(float(response.headers.get("Retry-After", 2)), 10.0)
    except (AttributeError, TypeError, ValueError):
        return 2.0


async def _synthesize_with_retry(tts, text: str, attempts: int = 3):
    """The page asks for up to three voices at once, more than the deployment's
    per-second limit allows: wait and retry a rate-limited request instead of failing.
    The call runs in a thread so a long synthesis does not block other requests."""
    for attempt in range(attempts):
        try:
            return await asyncio.to_thread(tts.synthesize, text)
        except Exception as exc:
            wait = _retry_after(exc)
            if wait is None or attempt == attempts - 1:
                raise
            await asyncio.sleep(wait * (attempt + 1))
    raise RuntimeError("unreachable")


@router.post("", response_model=TextToSpeechResponse)
async def synthesize_text(
    text: str = Form(...),
    language: str = Form("fi"),
    voice: str = Form("alloy"),
):
    normalized_text = text.strip()
    if not normalized_text:
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    if len(normalized_text) > MAX_TEXT_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Text exceeds maximum length of {MAX_TEXT_LENGTH} characters",
        )
    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language '{language}'. Supported languages: fi, en",
        )
    if voice not in SUPPORTED_VOICES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported voice selection",
        )

    try:
        from gaik.software_components.text_to_speech import TextToSpeech

        tts = TextToSpeech(api_config=get_api_config(), language=language, voice=voice)
        result = await _synthesize_with_retry(tts, normalized_text)
    except ImportError as exc:
        raise HTTPException(
            status_code=500, detail=f"Text-to-speech component not installed: {exc}"
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return TextToSpeechResponse(
        filename=result.filename,
        job_id=result.job_id,
        model=result.model,
        voice=result.voice,
        language=result.language,
        response_format=result.response_format,
        content_type=result.content_type,
        character_count=len(normalized_text),
        audio_base64=base64.b64encode(result.audio_bytes).decode("ascii"),
    )
