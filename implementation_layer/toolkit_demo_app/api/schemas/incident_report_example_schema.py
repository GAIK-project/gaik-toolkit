"""
Auto-generated schema module (do not edit manually).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class incident_Extraction(BaseModel):
    """Extraction model for incident"""

    model_config = ConfigDict(extra="forbid")

    date: str | None = Field(
        default=None, description="Date of the incident, as written in the report."
    )
    time: str | None = Field(
        default=None, description="Time of the incident, as written in the report."
    )
    location: str | None = Field(default=None, description="Where the incident happened.")
    description: str | None = Field(default=None, description="Brief description of what happened.")
    people_involved: list[str] | None = Field(
        default=None, description="People involved, one entry each, with their role if mentioned."
    )
    injuries: str | None = Field(
        default=None,
        description="Injuries reported, including medical treatment or sick leave. Empty if none.",
    )
    damages: str | None = Field(
        default=None, description="Property, goods or equipment damage. Empty if none."
    )
    immediate_actions: list[str] | None = Field(
        default=None, description="Immediate actions taken, one entry each."
    )
    witnesses: list[str] | None = Field(
        default=None, description="Names of witnesses, one entry each."
    )
    severity: Literal["low", "medium", "high", "critical"] | None = Field(
        default=None, description="Severity judged from the report: low, medium, high or critical."
    )
    incident_type: str | None = Field(
        default=None,
        description="Type of incident, such as slip or fall, near miss, equipment failure, vehicle, fire or spill.",
    )
    root_cause: str | None = Field(
        default=None,
        description="The likely cause of the incident, as stated or evident from the report.",
    )
    corrective_actions: list[str] | None = Field(
        default=None,
        description="Corrective or preventive actions, stated or recommended, one entry each.",
    )
    reported_by: str | None = Field(
        default=None,
        description="Who wrote or reported the incident, with their role if mentioned.",
    )
    equipment_involved: list[str] | None = Field(
        default=None, description="Machines, vehicles or tools involved, one entry each."
    )


class incident_Collection(BaseModel):
    """Collection of incident items"""

    model_config = ConfigDict(extra="forbid")

    incidents: list[incident_Extraction] = Field(
        description="One entry for each incident described in the text."
    )
