"""
Auto-generated schema module (do not edit manually).
"""

import decimal
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, ConfigDict

class construction_diary_extraction_Extraction(BaseModel):
    """Extraction model for construction_diary_extraction"""
    model_config = ConfigDict(extra='forbid')

    project_or_site_name: str | None = Field(None, description="Name of the construction project or site")
    author_or_supervisor_name: str | None = Field(None, description="Name of the person authoring the diary or supervising the site")
    date: str | None = Field(None, description="Date of the diary entry")
    week_number: str | None = Field(None, description="Calendar week number corresponding to the diary entry date")
    weather_conditions: str | None = Field(None, description="Description of the weather conditions during the day")
    personnel_and_subcontractors: list[str] | None = Field(None, description="List of personnel and subcontractor entities present or involved")
    days_work_tasks: list[str] | None = Field(None, description="List of work tasks performed during the day")
    days_events: list[str] | None = Field(None, description="List of notable events during the day")
    started_work_phases: list[str] | None = Field(None, description="Work phases that were started on this day")
    ongoing_work_phases: list[str] | None = Field(None, description="Work phases that were ongoing during this day")
    completed_work_phases: list[str] | None = Field(None, description="Work phases that were completed on this day")
    interrupted_work_phases: list[str] | None = Field(None, description="Work phases that were interrupted or paused on this day")
    supervisor_observations_or_remarks: str | None = Field(None, description="Supervisor’s observations, comments, or remarks for the day")
    attachments_inspections_and_requested_extensions: str | None = Field(None, description="Mention of attachments, inspections, and any requested extensions")
