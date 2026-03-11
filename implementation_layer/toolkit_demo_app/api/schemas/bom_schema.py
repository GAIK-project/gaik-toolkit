"""
Auto-generated schema module (do not edit manually).
"""

import decimal
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, ConfigDict

class material_extraction_Extraction(BaseModel):
    """Extraction model for material_extraction"""
    model_config = ConfigDict(extra='forbid')

    material_id: str | None = Field(None, description="Identifier of the material")
    product_type_designation: str | None = Field(None, description="Product type designation of the material")
    dimensions: str | None = Field(None, description="Dimensions of the material")
    material_grade: str | None = Field(None, description="Material grade specification")
    cutting_required: bool | None = Field(None, description="Whether cutting is required")
    testing_required: bool | None = Field(None, description="Whether testing is required")
    certificates_required: bool | None = Field(None, description="Whether certificates are required")
