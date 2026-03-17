"""
Auto-generated schema module (do not edit manually).
"""

from pydantic import BaseModel, ConfigDict, Field


class incident_details_extraction_Extraction(BaseModel):
    """Extraction model for incident_details_extraction"""

    model_config = ConfigDict(extra="forbid")

    date: str | None = Field(None, description="Date of the incident")
    time: str | None = Field(None, description="Time of the incident")
    location: str | None = Field(None, description="Location where the incident occurred")
    description: str | None = Field(None, description="Narrative description of the incident")
    people_involved: list[str] | None = Field(None, description="People involved in the incident")
    injuries: str | None = Field(
        None, description="Details of any injuries resulting from the incident"
    )
    damages: str | None = Field(
        None, description="Details of any damages resulting from the incident"
    )
    actions_taken: list[str] | None = Field(
        None, description="Actions taken in response to the incident"
    )
