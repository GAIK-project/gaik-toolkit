"""Pipeline endpoint schemas for diary and incident report generation."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class DiaryResponse(BaseModel):
    """Construction site diary generation response."""

    job_id: str = Field(..., description="Unique job identifier")
    raw_transcript: str | None = Field(None, description="Raw transcript from audio")
    enhanced_transcript: str | None = Field(None, description="LLM-enhanced transcript")
    extracted_data: dict[str, Any] | None = Field(None, description="Extracted diary fields")
    pdf_available: bool = Field(False, description="Whether PDF is available for download")
    error: str | None = Field(None, description="Error message if processing failed")

    model_config = {
        "json_schema_extra": {
            "example": {
                "job_id": "abc123",
                "raw_transcript": "Tänään työmaalla...",
                "enhanced_transcript": "Työmaapäiväkirja - Tänään...",
                "extracted_data": {
                    "kohde": "Saneeraushanke",
                    "paivamaara": "15.01.2026",
                    "saa": "3 °C, pilvistä",
                },
                "pdf_available": True,
            }
        }
    }


class IncidentReportResponse(BaseModel):
    """Incident report generation response."""

    job_id: str = Field(..., description="Unique job identifier")
    input_type: Literal["audio", "text", "document"] = Field(
        ..., description="Type of input processed"
    )
    raw_transcript: str | None = Field(None, description="Raw transcript (audio input only)")
    enhanced_transcript: str | None = Field(
        None, description="Enhanced transcript (audio input only)"
    )
    parsed_content: str | None = Field(
        None, description="Parsed document content (document input only)"
    )
    input_text: str | None = Field(None, description="Original text input (text input only)")
    extracted_data: list[dict[str, Any]] | None = Field(
        None, description="Extracted incident details"
    )
    pdf_available: bool = Field(False, description="Whether PDF is available for download")
    error: str | None = Field(None, description="Error message if processing failed")

    model_config = {
        "json_schema_extra": {
            "example": {
                "job_id": "xyz789",
                "input_type": "text",
                "extracted_data": [
                    {
                        "date": "2026-01-12",
                        "location": "Warehouse Area B",
                        "description": "Employee slipped on wet floor",
                        "injuries": "Minor bruising to right arm",
                    }
                ],
                "pdf_available": True,
            }
        }
    }
