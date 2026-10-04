"""
Auto-generated schema module (do not edit manually).
"""

from pydantic import BaseModel, ConfigDict, Field


class Construction_site_diary_Extraction(BaseModel):
    """Extraction model for Construction site diary"""

    model_config = ConfigDict(extra="forbid")

    site_address: str = Field(description="The construction site address.")
    date: str = Field(description="The date as said, as text; it may have no month or year.")
    number_of_subcontractors: int | None = Field(
        default=None, description="The number of subcontractors on site."
    )
    number_of_own_machine_operators: int | None = Field(
        default=None, description="The number of own machine operators on site."
    )
    work_in_progress: str = Field(description="The work in progress at the construction site.")
    upper_floor_interior_demolition_progress: float | None = Field(
        default=None,
        description="The progress of the interior demolition on the upper floor, expressed as percent done, as a number.",
    )
    lower_floor_interior_demolition_progress: float | None = Field(
        default=None,
        description="The progress of the interior demolition on the lower floor, expressed as percent done, as a number.",
    )
    utilities_cut_off: list[str] = Field(
        default=[], description="The utilities cut off at the construction site."
    )
    calls_made: list[str] = Field(default=[], description="The calls made.")
