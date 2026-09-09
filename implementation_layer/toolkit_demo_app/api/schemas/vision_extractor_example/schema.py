"""Committed schema for the Vision Extractor PO/BOM website example."""

from pydantic import BaseModel, ConfigDict, Field


class purchase_order_item_Extraction(BaseModel):
    """Extraction model for purchase_order_item."""

    model_config = ConfigDict(extra="forbid")

    material_number: str = Field(
        description="Material Number for the PO item, used to match the BOM ID"
    )
    quantity: int | None = Field(default=None, description="Quantity for the PO item")
    description: str = Field(description="Description of the PO item")
    delivery_date: str = Field(description="Delivery Date for the PO item in DD/MM/YYYY format")
    type_part_designation: str = Field(
        description="Type Part Designation from the matching BOM record"
    )
    dimensions: str = Field(description="Dimensions from the matching BOM record")


class purchase_order_header_extraction_Extraction(BaseModel):
    """Purchase order header with repeated PO items enriched from matching BOMs."""

    model_config = ConfigDict(extra="forbid")

    order_date: str = Field(description="Order date from the PO header")
    buyer: str = Field(description="Buyer from the PO header")
    sales_person: str = Field(description="Sales person from the PO header")
    shipping_address: str = Field(description="Shipping address from the PO header")
    payment_terms: str = Field(description="Payment terms from the PO header")
    po_items: list[purchase_order_item_Extraction] = Field(
        description="Repeated PO items enriched with matching BOM information"
    )
