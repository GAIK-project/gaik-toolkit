"""Auto-generated schema — do not edit manually."""

import decimal
from decimal import Decimal
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class Site_survey_Extraction(BaseModel):
    "Extraction model for Site survey"

    model_config = ConfigDict(extra="forbid")

    rating: Optional[Literal["", "1", "2", "3", "4", "5"]] = Field(
        description="Overall rating from 1 to 5", default=None
    )
    moisture_level: Optional[Literal["", "0.5", "1"]] = Field(
        description="Moisture level: 0.5 or 1", default=None
    )
    hazard_types: Literal["", "fire", "chemical", "electrical"] = Field(
        description="Hazards seen: fire, chemical or electrical", default_factory=list
    )
    inspector: str = Field(description="Inspector's name")
