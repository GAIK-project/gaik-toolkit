"""Transcriber router - Audio/video transcription endpoints"""

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

router = APIRouter()


class TranscribeResponse(BaseModel):
    filename: str
    raw_transcript: str
    enhanced_transcript: str | None
    job_id: str


@router.post("/", response_model=TranscribeResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    custom_context: str = "",
    enhanced: bool = True,
    compress_audio: bool = True,
):
    """
    Transcribe an audio or video file.

    - **file**: Audio/video file (mp3, wav, mp4, m4a, etc.)
    - **custom_context**: Optional context to help transcription
    - **enhanced**: Whether to enhance transcript with LLM
    - **compress_audio**: Whether to compress audio before sending
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Check for OpenAI API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY environment variable not set",
        )

    suffix = Path(file.filename).suffix.lower()

    supported = [".mp3", ".wav", ".m4a", ".mp4", ".webm", ".ogg", ".flac"]
    if suffix not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}. Supported: {', '.join(supported)}",
        )

    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from gaik.building_blocks.transcriber import Transcriber, get_openai_config

        config = get_openai_config(use_azure=False)  # Use standard OpenAI
        config["api_key"] = api_key  # Override with provided key
        transcriber = Transcriber(
            api_config=config,
            enhanced_transcript=enhanced,
            compress_audio=compress_audio,
        )

        result = transcriber.transcribe(
            file_path=tmp_path,
            custom_context=custom_context,
        )

        return TranscribeResponse(
            filename=file.filename,
            raw_transcript=result.raw_transcript,
            enhanced_transcript=result.enhanced_transcript,
            job_id=result.job_id,
        )

    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Transcriber not installed: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        Path(tmp_path).unlink(missing_ok=True)

