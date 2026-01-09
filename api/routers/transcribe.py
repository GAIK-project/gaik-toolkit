"""Transcribe endpoint for audio/video transcription."""

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from api.config import get_openai_config, settings
from api.dependencies import verify_api_key
from api.schemas.transcribe import TranscribeResponse
from gaik.building_blocks.transcriber.transcriber import Transcriber

router = APIRouter()


@router.post(
    "/",
    response_model=TranscribeResponse,
    dependencies=[Depends(verify_api_key)],
    summary="Transcribe audio/video file",
    description="Transcribe an audio or video file using Whisper with optional LLM enhancement.",
)
async def transcribe_audio(
    file: UploadFile = File(..., description="Audio/video file to transcribe"),
    custom_context: str = Form(default="", description="Optional context for transcription"),
    enhanced: bool = Form(default=True, description="Enhance transcript with LLM post-processing"),
):
    """
    Transcribe an audio or video file.

    - **file**: Audio/video file (mp3, wav, mp4, m4a, webm, ogg, flac)
    - **custom_context**: Optional context to improve transcription accuracy
    - **enhanced**: Enable LLM enhancement for better readability (default: True)

    Returns transcription with raw and optionally enhanced text.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    # Validate file extension
    suffix = Path(file.filename).suffix.lower()
    if suffix not in settings.ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {suffix}. Allowed: {settings.ALLOWED_AUDIO_EXTENSIONS}",
        )

    # Read and validate file size
    content = await file.read()
    if len(content) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {settings.MAX_FILE_SIZE_MB}MB",
        )

    # Save to temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        config = get_openai_config()
        transcriber = Transcriber(
            api_config=config,
            enhanced_transcript=enhanced,
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

    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Transcription failed: file processing error")
    except Exception:
        raise HTTPException(status_code=500, detail="Transcription failed")
    finally:
        # Clean up temporary file
        Path(tmp_path).unlink(missing_ok=True)
