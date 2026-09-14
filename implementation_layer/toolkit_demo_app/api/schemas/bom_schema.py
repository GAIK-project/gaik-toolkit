"""
Auto-generated schema module (do not edit manually).
"""

from pydantic import BaseModel, ConfigDict, Field


class material_extraction_Extraction(BaseModel):  # noqa: N801
    """Extraction model for material_extraction"""

    model_config = ConfigDict(extra="forbid")

    material_id: str | None = Field(default=None, description="Identifier of the material")
    product_type_designation: str | None = Field(
        default=None, description="Product type designation of the material"
    )
    dimensions: str | None = Field(default=None, description="Dimensions of the material")
    material_grade: str | None = Field(default=None, description="Material grade specification")
    cutting_required: bool | None = Field(default=None, description="Whether cutting is required")
    testing_required: bool | None = Field(default=None, description="Whether testing is required")
    certificates_required: bool | None = Field(
        default=None, description="Whether certificates are required"
    )
