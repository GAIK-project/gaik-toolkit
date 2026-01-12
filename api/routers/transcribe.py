"""Transcribe endpoint for audio/video transcription."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from api.config import get_openai_config, settings
from api.dependencies import verify_api_key
from api.schemas.transcribe import TranscribeResponse
from api.utils import temp_file, validate_file_size, validate_upload
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
    suffix = validate_upload(file, settings.ALLOWED_AUDIO_EXTENSIONS)

    content = await file.read()
    validate_file_size(content)

    with temp_file(content, suffix) as tmp_path:
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
            raise HTTPException(status_code=500, detail="Transcription failed: file error")
        except Exception:
            raise HTTPException(status_code=500, detail="Transcription failed")
