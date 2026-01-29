"""
Auto-generated schema module (do not edit manually).
"""

import decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class project_information_from_research_grant_documents_Extraction(BaseModel):
    """Extraction model for project_information_from_research_grant_documents"""

    model_config = ConfigDict(extra="forbid")

    project_title: str | None = Field(None, description="Title of the research project")
    project_acronym: str | None = Field(None, description="Acronym of the research project")
    lead_institution: str | None = Field(None, description="Lead institution of the project")
    total_funding_in_eur: decimal.Decimal | None = Field(
        None, description="Total funding amount in EUR"
    )
    start_date: str | None = Field(None, description="Project start date")
    project_status: Literal["ongoing", "completed"] | None = Field(
        None, description="Current status of the project"
    )
