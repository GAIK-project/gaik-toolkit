"""Transcriber router - Audio/video transcription endpoints"""

import os
from difflib import SequenceMatcher
import tempfile
from pathlib import Path

try:
    from utils import validate_file_size
except ImportError:
    from api.utils import validate_file_size
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

router = APIRouter()


class TranscriptSegment(BaseModel):
    start: float | None = None
    end: float | None = None
    speaker: str | None = None
    text: str | None = None


class CorrectionSummary(BaseModel):
    total_changes: int
    insertions: int
    deletions: int
    substitutions: int


class DiffChunk(BaseModel):
    kind: str
    original: str = ""
    corrected: str = ""


class TranscribeResponse(BaseModel):
    filename: str
    raw_transcript: str
    enhanced_transcript: str | None
    corrected_transcript: str | None = None
    correction_summary: CorrectionSummary | None = None
    diff_chunks: list[DiffChunk] | None = None
    job_id: str
    segments: list[TranscriptSegment] | None = None
    used_fallback: bool = False
    fallback_reason: str | None = None
    transcription_model: str | None = None


@router.post("", response_model=TranscribeResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    custom_context: str = Form(""),
    enhanced: bool = Form(False),
    compress_audio: bool = Form(True),
    language: str = Form("auto"),
    diarization: bool = Form(False),
    speaker_count: int | None = Form(None),
    min_speakers: int | None = Form(None),
    max_speakers: int | None = Form(None),
    initial_prompt: str | None = Form(None),
    prefer_local_first: bool = Form(True),
    fix_transcription_errors: bool = Form(False),
    enhanced_transcript_instructions: str | None = Form(None),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    enhanced = fix_transcription_errors

    use_azure = bool(os.getenv("AZURE_API_KEY"))
    if not use_azure and not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="Either AZURE_API_KEY or OPENAI_API_KEY environment variable must be set",
        )

    suffix = Path(file.filename).suffix.lower()
    supported = [".mp3", ".wav", ".m4a", ".mp4", ".webm", ".ogg", ".flac"]
    if suffix not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}. Supported: {', '.join(supported)}",
        )

    content = await validate_file_size(file)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from gaik.software_components.transcriber import Transcriber, get_openai_config

        config = get_openai_config(use_azure=use_azure)
        local_api_base = os.getenv("LOCAL_TRANSCRIBER_API_BASE")
        local_api_key = os.getenv("LOCAL_TRANSCRIBER_API_KEY")

        transcriber_kwargs = {
            "api_config": config,
            "output_dir": tempfile.gettempdir(),
            "enhanced_transcript": enhanced,
            "enhanced_transcript_instructions": enhanced_transcript_instructions,
            "compress_audio": compress_audio,
            "language": language,
            "diarization": diarization,
            "speaker_count": speaker_count,
            "min_speakers": min_speakers,
            "max_speakers": max_speakers,
            "initial_prompt": initial_prompt,
            "local_api_base": local_api_base,
            "local_api_key": local_api_key,
        }

        used_fallback = False
        fallback_reason = None
        cloud_model = config.get("transcription_model", "whisper")

        if prefer_local_first and local_api_base and local_api_key:
            try:
                transcriber = Transcriber(
                    **transcriber_kwargs,
                    transcription_model="whisper_local",
                )
                result = transcriber.transcribe(file_path=tmp_path, custom_context=custom_context)
                transcription_model_used = "whisper_local"
            except Exception as exc:
                print(f"Local transcription failed: {exc}")
                print("Falling back to configured transcription model.")
                used_fallback = True
                fallback_reason = _categorize_fallback_reason(exc)
                transcriber = Transcriber(**transcriber_kwargs)
                result = transcriber.transcribe(file_path=tmp_path, custom_context=custom_context)
                transcription_model_used = cloud_model
        else:
            if prefer_local_first and not (local_api_base and local_api_key):
                print(
                    "prefer_local_first=True but local_api_base/local_api_key are not configured; "
                    "using configured transcription model instead."
                )
            transcriber = Transcriber(**transcriber_kwargs)
            result = transcriber.transcribe(file_path=tmp_path, custom_context=custom_context)
            transcription_model_used = cloud_model

        corrected_transcript = None
        correction_summary = None
        diff_chunks = None
        if fix_transcription_errors and result.enhanced_transcript:
            corrected_transcript = result.enhanced_transcript
            correction_summary = _summarize_corrections(
                result.raw_transcript,
                corrected_transcript,
            )
            diff_chunks = _build_diff_chunks(
                result.raw_transcript,
                corrected_transcript,
            )

        return TranscribeResponse(
            filename=file.filename,
            raw_transcript=result.raw_transcript,
            enhanced_transcript=result.enhanced_transcript,
            corrected_transcript=corrected_transcript,
            correction_summary=correction_summary,
            diff_chunks=diff_chunks,
            job_id=result.job_id,
            segments=result.segments if diarization else None,
            used_fallback=used_fallback,
            fallback_reason=fallback_reason,
            transcription_model=transcription_model_used,
        )
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Transcriber not installed: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _categorize_fallback_reason(exc: Exception) -> str:
    causes: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None:
        causes.append(current)
        current = getattr(current, "__cause__", None) or getattr(
            current, "__context__", None
        )

    for cause in causes:
        cause_type = type(cause).__name__.lower()
        cause_str = str(cause).lower()
        if "connectionrefused" in cause_type or "connection refused" in cause_str:
            return "Local transcriber server is not reachable (connection refused)"
        if "timeout" in cause_type or "timed out" in cause_str:
            return "Local transcriber server timed out"
        if "name or service not known" in cause_str or "nodename nor servname" in cause_str:
            return "Local transcriber hostname could not be resolved (DNS)"

    return f"Local transcription failed ({type(exc).__name__})"


def _summarize_corrections(original_text: str, corrected_text: str) -> CorrectionSummary:
    original_tokens = original_text.split()
    corrected_tokens = corrected_text.split()
    matcher = SequenceMatcher(a=original_tokens, b=corrected_tokens)

    insertions = 0
    deletions = 0
    substitutions = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
            insertions += j2 - j1
        elif tag == "delete":
            deletions += i2 - i1
        elif tag == "replace":
            a_len = i2 - i1
            b_len = j2 - j1
            substitutions += min(a_len, b_len)
            if b_len > a_len:
                insertions += b_len - a_len
            elif a_len > b_len:
                deletions += a_len - b_len

    return CorrectionSummary(
        total_changes=insertions + deletions + substitutions,
        insertions=insertions,
        deletions=deletions,
        substitutions=substitutions,
    )


def _build_diff_chunks(original_text: str, corrected_text: str) -> list[DiffChunk]:
    original_tokens = original_text.split()
    corrected_tokens = corrected_text.split()
    matcher = SequenceMatcher(a=original_tokens, b=corrected_tokens)
    chunks: list[DiffChunk] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        chunks.append(
            DiffChunk(
                kind=tag,
                original=" ".join(original_tokens[i1:i2]),
                corrected=" ".join(corrected_tokens[j1:j2]),
            )
        )

    return chunks
