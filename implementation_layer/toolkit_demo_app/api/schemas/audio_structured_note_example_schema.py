"""
Auto-generated schema module (do not edit manually).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class safety_observation_Extraction(BaseModel):
    """Extraction model for safety_observation"""

    model_config = ConfigDict(extra="forbid")

    reporter_name: str = Field(
        description="Name of the person who reported the safety observation."
    )
    date: str = Field(description="Date of the safety observation.")
    place: str = Field(description="Place of the safety observation.")
    problem: str = Field(description="Problem identified in the safety observation.")
    effect_on_workers: str = Field(description="How the observed problem affects the workers.")
    needs_repair: Literal["", "yes", "no"] = Field(
        default="", description="Whether the observed problem needs a repair; use yes or no."
    )
