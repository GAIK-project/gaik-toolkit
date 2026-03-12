"""Video transcription router - Audio/video transcription with SRT/VTT subtitle generation."""

import asyncio
import os
import tempfile
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from pathlib import Path

try:
    from utils import (
        MAX_FILE_SIZE_BYTES,
        MAX_FILE_SIZE_MB,
        create_s3_client,
        sse_error_response,
        sse_event,
    )
except ImportError:
    from api.utils import (
        MAX_FILE_SIZE_BYTES,
        MAX_FILE_SIZE_MB,
        create_s3_client,
        sse_error_response,
        sse_event,
    )
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse

router = APIRouter()

# Temporary storage for generated subtitle files
SRT_STORAGE: dict[str, tuple[str, str]] = {}  # job_id -> (srt_content, vtt_content)
SRT_TIMESTAMPS: dict[str, datetime] = {}
CLEANUP_HOURS = 1
EXAMPLE_VIDEO_ID = "99b5e26d14b5"
EXAMPLE_VIDEO_TITLE = "Kielitaito tuo etulyöntiaseman työelämässä"
EXAMPLE_SOURCE_URL = "https://www.youtube.com/watch?v=0Ijh-3oF0_U"


async def _cleanup_old_subtitles():
    """Background cleanup of old subtitle artifacts."""
    while True:
        await asyncio.sleep(3600)
        cutoff = datetime.now() - timedelta(hours=CLEANUP_HOURS)
        expired = [jid for jid, ts in SRT_TIMESTAMPS.items() if ts < cutoff]
        for jid in expired:
            SRT_STORAGE.pop(jid, None)
            SRT_TIMESTAMPS.pop(jid, None)


@router.post("/stream")
async def dental_transcription_stream(
    file: UploadFile = File(...),
    language: str = Form("auto"),
):
    """
    Transcribe audio/video and generate SRT/VTT subtitles with SSE progress.

    - **file**: Audio or video file
    - **language**: Language code (auto, fi, en, sv)
    """
    job_id = str(uuid.uuid4())

    if not file.filename:
        return sse_error_response("No filename provided")

    suffix = Path(file.filename).suffix.lower()
    supported = [".mp3", ".wav", ".m4a", ".mp4", ".webm", ".ogg", ".flac", ".mov"]
    if suffix not in supported:
        return sse_error_response(f"Unsupported file type: {suffix}")

    # Check local Whisper configuration
    local_api_base = os.getenv("LOCAL_WHISPER_BASE")
    local_api_key = os.getenv("LOCAL_WHISPER_KEY")
    if not local_api_base or not local_api_key:
        return sse_error_response(
            "Local Whisper service not configured. "
            "Set LOCAL_WHISPER_BASE and LOCAL_WHISPER_KEY environment variables."
        )

    # Validate file size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        return sse_error_response(f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB")

    # Save uploaded file
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    async def event_generator() -> AsyncGenerator[str, None]:
        steps = [
            {"step": 1, "name": "Transcription", "status": "pending"},
            {"step": 2, "name": "Subtitle Generation", "status": "pending"},
        ]

        yield sse_event("steps", {"steps": steps})

        try:
            # Step 1: Transcribe with local Whisper
            steps[0]["status"] = "in_progress"
            steps[0]["message"] = "Transcribing audio with local Whisper..."
            yield sse_event("step_update", steps[0])

            from gaik.software_components.transcriber.whisper_local import (
                transcribe as whisper_local_transcribe,
            )

            result = await asyncio.to_thread(
                whisper_local_transcribe,
                audio_path=tmp_path,
                api_base=local_api_base,
                key=local_api_key,
                language=language,
            )

            segments = result.get("segments", [])
            raw_text = (result.get("text") or "").strip()
            if not raw_text and segments:
                raw_text = " ".join(
                    seg.get("text", "").strip() for seg in segments if seg.get("text")
                ).strip()

            steps[0]["status"] = "completed"
            steps[0]["message"] = f"Transcription complete ({len(segments)} segments)"
            yield sse_event("step_update", steps[0])

            # Step 2: Generate subtitles
            steps[1]["status"] = "in_progress"
            steps[1]["message"] = "Generating SRT and VTT subtitles..."
            yield sse_event("step_update", steps[1])

            from gaik.software_components.transcriber.srt_utils import (
                segments_to_srt,
                segments_to_vtt,
            )

            srt_content = segments_to_srt(segments) if segments else ""
            vtt_content = segments_to_vtt(segments) if segments else ""

            # Store for download
            SRT_STORAGE[job_id] = (srt_content, vtt_content)
            SRT_TIMESTAMPS[job_id] = datetime.now()

            steps[1]["status"] = "completed"
            steps[1]["message"] = "Subtitles generated"
            yield sse_event("step_update", steps[1])

            # Send result
            yield sse_event(
                "result",
                {
                    "job_id": job_id,
                    "raw_transcript": raw_text,
                    "srt_content": srt_content,
                    "vtt_content": vtt_content,
                    "segments_count": len(segments),
                },
            )

        except Exception as e:
            for step in steps:
                if step["status"] == "in_progress":
                    step["status"] = "error"
                    step["message"] = str(e)
                    yield sse_event("step_update", step)
                    break
            yield sse_event("error", {"message": str(e)})
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/example")
async def dental_transcription_example():
    """Return a ready-made example video and subtitles for the demo page."""
    try:
        s3, bucket = create_s3_client()
        prefix = f"dental-demo/{EXAMPLE_VIDEO_ID}"
        video_key = f"{prefix}/video.mp4"
        srt_key = f"{prefix}/subtitles.srt"

        s3.head_object(Bucket=bucket, Key=video_key)
        s3.head_object(Bucket=bucket, Key=srt_key)

        srt_response = s3.get_object(Bucket=bucket, Key=srt_key)
        srt_content = srt_response["Body"].read().decode("utf-8")

        from gaik.software_components.transcriber.srt_utils import parse_srt, segments_to_vtt

        segments = parse_srt(srt_content)
        vtt_content = segments_to_vtt(segments)
        raw_transcript = " ".join(
            segment.get("text", "").strip() for segment in segments if segment.get("text")
        ).strip()

        video_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": video_key},
            ExpiresIn=900,
        )

        return {
            "video_id": EXAMPLE_VIDEO_ID,
            "title": EXAMPLE_VIDEO_TITLE,
            "source_url": EXAMPLE_SOURCE_URL,
            "video_url": video_url,
            "raw_transcript": raw_transcript,
            "srt_content": srt_content,
            "vtt_content": vtt_content,
            "segments_count": len(segments),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load example video: {exc}") from exc


@router.get("/srt/{job_id}")
async def download_srt(job_id: str):
    """Download generated SRT subtitle file."""
    if job_id not in SRT_STORAGE:
        raise HTTPException(status_code=404, detail="SRT file not found or expired")
    srt_content, _ = SRT_STORAGE[job_id]
    return Response(
        content=srt_content,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="subtitles_{job_id[:8]}.srt"'},
    )


@router.get("/vtt/{job_id}")
async def download_vtt(job_id: str):
    """Download generated VTT subtitle file."""
    if job_id not in SRT_STORAGE:
        raise HTTPException(status_code=404, detail="VTT file not found or expired")
    _, vtt_content = SRT_STORAGE[job_id]
    return Response(
        content=vtt_content,
        media_type="text/vtt",
        headers={"Content-Disposition": f'attachment; filename="subtitles_{job_id[:8]}.vtt"'},
    )
