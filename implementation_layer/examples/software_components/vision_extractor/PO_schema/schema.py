"""Auto-generated schema — do not edit manually."""

import decimal
from decimal import Decimal
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class purchase_order_line_item_Extraction(BaseModel):
    """Extraction model for purchase_order_line_item"""

    model_config = ConfigDict(extra="forbid")

    item_number: str = Field(description="Item number")
    article_code: str = Field(description="Article code (internal supplier code)")
    dimensions: str = Field(description="Dimensions (cross-section as stated)")
    product_form: Literal["", "Flat", "round", "rectangular bar"] = Field(
        description="Product form", default=""
    )
    material_grade: str = Field(description="Material grade")
    standard_designation: str = Field(description="Standard designation (alloy/standard code)")
    cut_length: str = Field(description="Cut length including the unit")
    temper_or_condition: str = Field(description="Temper or condition")
    hardness_hv: Optional[float] = Field(description="Hardness HV", default=None)
    min_bend_radius: Optional[float] = Field(description="Minimum bend radius", default=None)
    delivery_length_note: Optional[str] = Field(description="Delivery length note", default=None)
    applicable_standard: Optional[str] = Field(description="Applicable standard", default=None)
    special_flags: Optional[str] = Field(
        description="Special flags (any remaining codes)", default=None
    )
    quantity: str = Field(description="Quantity including the unit")


class purchase_order_header_extraction_Extraction(BaseModel):
    """Extraction model for purchase_order_header_extraction with repeated line_items"""

    model_config = ConfigDict(extra="forbid")

    purchase_order_number: str = Field(description="Purchase order number")
    delivery_date: str = Field(description="Delivery date (format: DD/MM/YYYY)")
    delivery_address: str = Field(
        description="Delivery address (Format: company name, street, postal code, city, country)"
    )
    vendor_number: str = Field(description="Vendor number")
    line_items: list[purchase_order_line_item_Extraction] = Field(
        description="Repeated purchase order line items listed in the document."
    )
