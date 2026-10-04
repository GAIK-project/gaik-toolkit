"""
Auto-generated schema module (do not edit manually).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class participants_Extraction(BaseModel):
    """Extraction model for participants"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Participant's name.")
    organization: str | None = Field(default=None, description="Participant's organization.")
    role: str | None = Field(default=None, description="Participant's role in the meeting.")


class action_items_Extraction(BaseModel):
    """Extraction model for action_items"""

    model_config = ConfigDict(extra="forbid")

    task: str = Field(description="The task for the action item.")
    responsible_person: str | None = Field(
        default=None, description="The person responsible for the action item."
    )
    deadline: str | None = Field(default=None, description="The deadline for the action item.")
    priority: Literal["", "low", "medium", "high"] = Field(
        default="", description="The action item's priority. Must be low, medium, or high."
    )
    status: Literal["", "not_started", "in_progress", "completed", "unknown"] = Field(
        default="",
        description="The action item's status. Must be not_started, in_progress, completed, or unknown.",
    )


class meeting_minutes_Extraction(BaseModel):
    """Extraction model for meeting_minutes with repeated participants, action_items"""

    model_config = ConfigDict(extra="forbid")

    meeting_title: str = Field(description="Title of the meeting.")
    date: str = Field(description="Date of the meeting.")
    start_time: str = Field(description="Start time of the meeting.")
    end_time: str | None = Field(default=None, description="End time of the meeting; can be null.")
    location_or_online_platform: str | None = Field(
        default=None, description="Meeting location or online platform; can be null."
    )
    chairperson: str | None = Field(
        default=None, description="Chairperson of the meeting; can be null."
    )
    summary: str = Field(description="Summary of the meeting.")
    participants: list[participants_Extraction] = Field(
        description="Repeated participant records containing name, organization, and role in the meeting. Organization and role may be null."
    )
    action_items: list[action_items_Extraction] = Field(
        description="Repeated action-item records containing task, responsible person, deadline, priority, and status. Responsible person and deadline may be null. Priority must be low, medium, or high; status must be not_started, in_progress, completed, or unknown."
    )
