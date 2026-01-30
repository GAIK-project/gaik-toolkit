"""Transcribe endpoint schemas."""

from pydantic import BaseModel, Field


class TranscribeResponse(BaseModel):
    """Transcription response."""

    filename: str = Field(..., description="Original filename")
    raw_transcript: str = Field(..., description="Raw transcript from Whisper")
    enhanced_transcript: str | None = Field(None, description="LLM-enhanced transcript")
    job_id: str = Field(..., description="Unique job identifier")

    model_config = {
        "json_schema_extra": {
            "example": {
                "filename": "meeting.mp3",
                "raw_transcript": "This is the raw transcript...",
                "enhanced_transcript": "This is the enhanced, cleaned transcript...",
                "job_id": "abc123def4",
            }
        }
    }
