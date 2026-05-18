"""Auto-generated schema - do not edit manually."""

from decimal import Decimal
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

class purchase_order_line_item_Extraction(BaseModel):
    """Extraction model for purchase_order_line_item"""
    model_config = ConfigDict(extra='forbid')

    item_number: str = Field(description='item number')
    complete_description: str = Field(description='complete description')
    quantity: Optional[int] = Field(description='quantity', default=None)
    price: Optional[Decimal] = Field(description='price', default=None)
    material_number: str = Field(description='material number')

class purchase_order_header_extraction_Extraction(BaseModel):
    """Extraction model for purchase_order_header_extraction with repeated line_items"""
    model_config = ConfigDict(extra='forbid')

    date: str = Field(description='date (DD/MM/YYYY format when unambiguous)')
    purchase_order_number: str = Field(description='purchase order number')
    supplier_number: str = Field(description='supplier number')
    contact: str = Field(description='contact')
    line_items: list[purchase_order_line_item_Extraction] = Field(description='Line items listed in the purchase order.')
