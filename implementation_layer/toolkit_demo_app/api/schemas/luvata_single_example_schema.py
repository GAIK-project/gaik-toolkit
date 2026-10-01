"""
Auto-generated schema module (do not edit manually).
"""

from gaik.software_components.extractor import OptionalDecimalField
from pydantic import BaseModel, ConfigDict, Field


class purchase_order_line_item_Extraction(BaseModel):
    """Extraction model for purchase_order_line_item"""

    model_config = ConfigDict(extra="forbid")

    item_number: str = Field(
        description="Item number (e.g., 010, 020). Preserve leading zeros if present."
    )
    description: str = Field(
        description="Description (the item's name, not its technical specification)."
    )
    quantity: str = Field(
        description='Quantity as a text string including the unit, e.g., "8.600 LB".'
    )
    price_per_currency: OptionalDecimalField = Field(
        default=None, description="Price per currency."
    )
    material_number: str = Field(description="Material number.")


class purchase_order_header_fields_Extraction(BaseModel):
    """Extraction model for purchase_order_header_fields with repeated line_items"""

    model_config = ConfigDict(extra="forbid")

    purchase_order_date: str = Field(
        description="Purchase order date (DD/MM/YYYY format when unambiguous)"
    )
    delivery_date: str = Field(description="Delivery date (DD/MM/YYYY format when unambiguous)")
    purchase_order_number: str = Field(
        description="Purchase order number (separated by a dash after every 4 digits)"
    )
    supplier_number: str = Field(description="Supplier number")
    shipping_address: str = Field(
        description="Shipping address (Format: company name, street number, postal code, city, country)"
    )
    line_items: list[purchase_order_line_item_Extraction] = Field(
        description="Repeated structured line item records in the purchase order."
    )
