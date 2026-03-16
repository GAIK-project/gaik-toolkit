"""
Auto-generated schema module (do not edit manually).
"""

import decimal
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, ConfigDict

class incident_details_extraction_Extraction(BaseModel):
    """Extraction model for incident_details_extraction"""
    model_config = ConfigDict(extra='forbid')

    date: str | None = Field(None, description="Date of the incident")
    time: str | None = Field(None, description="Time of the incident")
    location: str | None = Field(None, description="Location where the incident occurred")
    description: str | None = Field(None, description="Narrative description of the incident")
    people_involved: list[str] | None = Field(None, description="List of people involved in the incident")
    injuries: list[str] | None = Field(None, description="List or description of injuries related to the incident")
    damages: list[str] | None = Field(None, description="List or description of damages resulting from the incident")
    actions_taken: list[str] | None = Field(None, description="Actions taken in response to the incident")
