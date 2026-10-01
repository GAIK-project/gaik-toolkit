"""
Auto-generated schema module (do not edit manually).
"""

from pydantic import BaseModel, ConfigDict, Field


class daily_diary_entry_Extraction(BaseModel):
    """Extraction model for daily_diary_entry"""

    model_config = ConfigDict(extra="forbid")

    project: str | None = Field(default=None, description="Project or site name.")
    author: str | None = Field(default=None, description="Who wrote the diary, with their role.")
    date: str | None = Field(default=None, description="Date of the diary day.")
    week_number: int | None = Field(default=None, description="Work week number, if mentioned.")
    weather: str | None = Field(
        default=None, description="Weather conditions: temperature, wind, rain or snow."
    )
    personnel: str | None = Field(
        default=None, description="People on site: supervisors, workers, subcontractors, total."
    )
    work_done: list[str] | None = Field(
        default=None, description="The day's work tasks, one entry for each."
    )
    events: list[str] | None = Field(default=None, description="Notable events of the day.")
    phases_started: list[str] | None = Field(
        default=None, description="Work phases that were started."
    )
    phases_ongoing: list[str] | None = Field(
        default=None, description="Work phases that are in progress."
    )
    phases_completed: list[str] | None = Field(
        default=None, description="Work phases that were completed."
    )
    phases_interrupted: list[str] | None = Field(
        default=None, description="Work phases that were interrupted or paused."
    )
    supervisor_observations: str | None = Field(
        default=None, description="The supervisor's observations and remarks."
    )
    deviations: list[str] | None = Field(
        default=None, description="Deviations from the plan or the schedule."
    )
    inspections: list[str] | None = Field(
        default=None, description="Inspections, surveys or visits made."
    )
    safety: list[str] | None = Field(
        default=None, description="Safety observations, near misses or accidents."
    )
    equipment: list[str] | None = Field(
        default=None, description="Machines and equipment used on site."
    )
    deliveries: list[str] | None = Field(default=None, description="Material deliveries received.")
    delays: list[str] | None = Field(default=None, description="Delays and what caused them.")
    plans_for_the_next_day: list[str] | None = Field(
        default=None, description="What is planned for the next working day."
    )
    attachments: list[str] | None = Field(
        default=None, description="Photos or documents attached to the diary."
    )


class daily_diary_entry_Collection(BaseModel):
    """Collection of daily_diary_entry items"""

    model_config = ConfigDict(extra="forbid")

    entries: list[daily_diary_entry_Extraction] = Field(
        description="List of diary day records, one object per day mentioned in the text."
    )
