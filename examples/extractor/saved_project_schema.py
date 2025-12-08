"""
Auto-generated schema module (do not edit manually).
"""

import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Research_Grant_Project_Extraction(BaseModel):
    """Extraction model for Research Grant Project Extraction"""

    model_config = ConfigDict(extra="forbid")

    project_title: str | None = Field(None, description="Title of the research project.")
    project_acronym: str | None = Field(None, description="Acronym of the research project.")
    lead_institution: str | None = Field(
        None, description="Name of the lead institution for the project."
    )
    total_funding_in_eur: Decimal | None = Field(
        None, description="Total funding amount in EUR for the project."
    )
    start_date: datetime.date | None = Field(None, description="Start date of the project.")
    project_status: Optional[Literal["ongoing", "completed"]] = Field(
        None, description="Current status of the project."
    )
    project_status: Optional[Literal["ongoing", "completed"]] = Field(
        None, description="Current status of the project."
    )
