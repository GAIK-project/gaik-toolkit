"""
Auto-generated schema module (do not edit manually).
"""

import decimal

from pydantic import BaseModel, ConfigDict, Field


class invoice_extraction_ExtractionNormalized(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_number: str | None = Field(None, description="Invoice identifier")
    sender_name: str | None = Field(None, description="Name of the invoice sender")
    receiver_name: str | None = Field(None, description="Name of the invoice receiver")
    purchase_order_number: str | None = Field(None, description="Related purchase order identifier")
    date_of_invoice: str | None = Field(None, description="Date when the invoice was issued")
    subtotal: decimal.Decimal | None = Field(
        None, description="Invoice subtotal amount before discounts and taxes"
    )
    discount: decimal.Decimal | None = Field(
        None, description="Discount amount applied to the invoice"
    )
    tax: decimal.Decimal | None = Field(None, description="Tax amount applied to the invoice")
    grand_total: decimal.Decimal | None = Field(
        None, description="Final total amount payable on the invoice"
    )
