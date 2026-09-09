"""
Auto-generated schema module (do not edit manually).
"""

from gaik.software_components.extractor import OptionalDecimalField
from pydantic import BaseModel, ConfigDict, Field


class invoice_extraction_ExtractionNormalized(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_number: str | None = Field(default=None, description="Invoice identifier")
    sender_name: str | None = Field(default=None, description="Name of the invoice sender")
    receiver_name: str | None = Field(default=None, description="Name of the invoice receiver")
    purchase_order_number: str | None = Field(
        default=None, description="Related purchase order identifier"
    )
    date_of_invoice: str | None = Field(
        default=None, description="Date when the invoice was issued"
    )
    subtotal: OptionalDecimalField = Field(
        default=None, description="Invoice subtotal amount before discounts and taxes"
    )
    discount: OptionalDecimalField = Field(
        default=None, description="Discount amount applied to the invoice"
    )
    tax: OptionalDecimalField = Field(default=None, description="Tax amount applied to the invoice")
    grand_total: OptionalDecimalField = Field(
        default=None, description="Final total amount payable on the invoice"
    )
