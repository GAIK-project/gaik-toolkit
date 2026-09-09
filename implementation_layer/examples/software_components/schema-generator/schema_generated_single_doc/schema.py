"""Auto-generated schema - do not edit manually."""

from decimal import Decimal
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class participants_record_Extraction(BaseModel):
    """Extraction model for participants_record"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Participant’s name.")
    organization: Optional[str] = Field(
        description="Participant’s organization. Can be null.", default=None
    )
    role: Optional[str] = Field(
        description="Participant’s role in the meeting. Can be null.", default=None
    )


class action_items_record_Extraction(BaseModel):
    """Extraction model for action_items_record"""

    model_config = ConfigDict(extra="forbid")

    task: str = Field(description="Task for the action item.")
    responsible_person: Optional[str] = Field(
        description="Responsible person for the action item; can be null.", default=None
    )
    deadline: Optional[str] = Field(
        description="Deadline for the action item; can be null.", default=None
    )
    priority: Literal["", "low", "medium", "high"] = Field(
        description="Priority for the action item; must be low, medium, or high.", default=""
    )
    status: Literal["", "not_started", "in_progress", "completed", "unknown"] = Field(
        description="Status for the action item; must be not_started, in_progress, completed, or unknown.",
        default="",
    )


class meeting_minutes_header_fields_Extraction(BaseModel):
    """Extraction model for meeting_minutes_header_fields with repeated participants, action_items"""

    model_config = ConfigDict(extra="forbid")

    meeting_title: str = Field(description="Meeting title.")
    date: str = Field(description="Date of the meeting.")
    start_time: str = Field(description="Start time of the meeting.")
    end_time: Optional[str] = Field(description="End time of the meeting.", default=None)
    location_or_online_platform: Optional[str] = Field(
        description="Location or online platform of the meeting.", default=None
    )
    chairperson: Optional[str] = Field(description="Chairperson of the meeting.", default=None)
    summary: str = Field(description="Summary of the meeting.")
    participants: list[participants_record_Extraction] = Field(
        description="List of structured participant records mentioned in the meeting minutes"
    )
    action_items: list[action_items_record_Extraction] = Field(
        description="List of structured action item records from the meeting minutes"
    )
