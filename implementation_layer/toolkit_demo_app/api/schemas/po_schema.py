"""
Auto-generated schema module (do not edit manually).
"""

import decimal
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, ConfigDict

class line_item_and_document_extraction_Extraction(BaseModel):
    """Extraction model for line_item_and_document_extraction"""
    model_config = ConfigDict(extra='forbid')

    material_number: str | None = Field(None, description="Material number for the line item")
    description: str | None = Field(None, description="Description of the line item material")
    quantity: int | None = Field(None, description="Quantity of the line item as an integer")
    delivery_date: str | None = Field(None, description="Delivery date for the line item, if available")
    purchase_order_number: str | None = Field(None, description="Shared purchase order number at the document level")
    customer_name: str | None = Field(None, description="Customer name at the document level")

class line_item_and_document_extraction_Collection(BaseModel):
    """Collection of line_item_and_document_extraction items"""
    model_config = ConfigDict(extra='forbid')

    line_items: list[line_item_and_document_extraction_Extraction] = Field(description="List of line items contained in the purchase order document")
