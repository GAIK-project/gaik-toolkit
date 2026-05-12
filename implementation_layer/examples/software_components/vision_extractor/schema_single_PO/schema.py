"""Auto-generated schema — do not edit manually."""

import decimal
from decimal import Decimal
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

class line_item_Extraction(BaseModel):
    """Extraction model for line_item"""
    model_config = ConfigDict(extra='forbid')

    item_number: str = Field(description='item number')
    complete_description: str = Field(description='complete description')
    quantity: Optional[int] = Field(description='quantity', default=None)
    price: Optional[Decimal] = Field(description='price', default=None)
    material_number: str = Field(description='material number')

class purchase_order_top_level_fields_extraction_Extraction(BaseModel):
    """Extraction model for purchase_order_top_level_fields_extraction with repeated line_items"""
    model_config = ConfigDict(extra='forbid')

    date: str = Field(description='Purchase order date (DD-MM-YYYY)')
    purchase_order_number: str = Field(description='Purchase order number')
    supplier_number: str = Field(description='Supplier number')
    contact: str = Field(description='Contact')
    line_items: list[line_item_Extraction] = Field(description='Repeated collection of purchase order line items.')
