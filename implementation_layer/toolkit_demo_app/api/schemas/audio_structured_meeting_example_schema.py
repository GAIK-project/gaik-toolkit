"""
Auto-generated schema module (do not edit manually).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class action_items_Extraction(BaseModel):
    """Extraction model for action_items"""

    model_config = ConfigDict(extra="forbid")

    task: str = Field(description="The action item task, written in English.")
    person_responsible: str = Field(
        description="The person responsible for the action item, written in English."
    )
    deadline: str | None = Field(
        default=None,
        description="The deadline as said in the recording, written in English. Can be null.",
    )
    action_type: Literal["", "booking", "delivery", "confirmation"] = Field(
        default="",
        description="Whether the action item is a booking, a delivery or a confirmation. Allowed values: booking, delivery, confirmation.",
    )


class site_meeting_Extraction(BaseModel):
    """Extraction model for site_meeting with repeated action_items"""

    model_config = ConfigDict(extra="forbid")

    meeting_topic: str = Field(description="The topic of the site meeting.")
    summary: str = Field(description="A short summary of the site meeting in English.")
    schedule_status: Literal["", "on_time", "delayed"] = Field(
        default="",
        description="Whether the schedule is on time or delayed, using one of: on_time, delayed.",
    )
    delay_in_weeks: int | None = Field(
        default=None,
        description="The schedule delay in weeks as a number; null if the schedule is on time.",
    )
    action_items: list[action_items_Extraction] = Field(
        description="Repeated action-item records with task, person responsible, deadline as stated in the recording (may be null), and category (booking, delivery, confirmation). Values are in English."
    )
