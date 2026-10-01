"""
Auto-generated schema module (do not edit manually).
"""

from gaik.software_components.extractor import OptionalDecimalField
from pydantic import BaseModel, ConfigDict, Field


class po_item_record_Extraction(BaseModel):
    """Extraction model for po_item_record"""

    model_config = ConfigDict(extra="forbid")

    material_number: str = Field(
        description="Material Number from the PO item; use this value to match the BOM where the same Material Number is represented as 'ID'."
    )
    quantity: int | None = Field(default=None, description="Quantity from the PO item.")
    description: str | None = Field(default=None, description="Description from the PO item.")
    delivery_date: str | None = Field(
        default=None, description="Delivery Date from the PO item (Format: DD/MM/YYYY)."
    )
    type_part_designation: str | None = Field(
        default=None, description="Type/Part Designation from the matching BOM."
    )
    dimensions: str | None = Field(
        default=None,
        description="Dimensions from the matching BOM, exactly as stated, e.g., 50 x 50 x 5 mm x 6000 mm.",
    )
    material_grade: str | None = Field(
        default=None, description="Material Grade from the matching BOM."
    )


class additional_fees_record_Extraction(BaseModel):
    """Extraction model for additional_fees_record"""

    model_config = ConfigDict(extra="forbid")

    material_number: str = Field(
        description="Material Number for the PO item and matching BOM to which this additional fee entry applies."
    )
    fee_name: str = Field(
        description="Fee name as written in the 'Additional Services & Fees' table, e.g., Cutting Fee."
    )
    charge_basis: str = Field(
        description="Charge basis as written in the table, e.g., per cut, per pipe, per crate."
    )
    quantity: int | None = Field(
        default=None,
        description="Quantity for the additional fee as number only, e.g., 200 for '200 cuts'.",
    )


class purchase_order_header_extraction_Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    po_number: str = Field(description="PO Number from the purchase order.")
    customer: str = Field(
        description="Customer from the PO: the company that issues the PO, not the individual buyer."
    )
    order_date: str | None = Field(
        default=None, description="Order Date from the PO (Format: DD/MM/YYYY)."
    )
    buyer: str | None = Field(default=None, description="Buyer from the PO.")
    sales_person: str | None = Field(default=None, description="Sales Person from the PO.")
    shipping_address: str | None = Field(default=None, description="Shipping Address from the PO.")
    payment_terms: str | None = Field(default=None, description="Payment Terms from the PO.")
    shipping_cost: OptionalDecimalField = Field(
        default=None,
        description="Shipping Cost from the PO: amount charged for shipping, number only.",
    )
    tax_rate: float | None = Field(
        default=None, description="Tax Rate from the PO: percent, number only."
    )
    po_items: list[po_item_record_Extraction] = Field(
        description="One entry per PO item, containing PO item fields plus BOM technical details matched by Material Number."
    )
    additional_fees: list[additional_fees_record_Extraction] = Field(
        description="One entry per applicable fee from the matching BOM's Additional Services & Fees table where Applies is Yes, extracting Material Number, Fee name, Charge basis, and Quantity."
    )
