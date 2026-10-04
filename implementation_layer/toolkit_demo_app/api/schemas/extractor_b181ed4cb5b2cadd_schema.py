"""
Auto-generated schema module (do not edit manually).
"""

from gaik.software_components.extractor import OptionalDecimalField
from pydantic import BaseModel, ConfigDict, Field


class invoice_lines_Extraction(BaseModel):
    """Extraction model for invoice_lines"""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(description="Description of the invoice line.")
    quantity: float | None = Field(
        default=None, description="Quantity of the invoice line, expressed as a numeric value."
    )
    unit: str = Field(description="Unit of the invoice line.")
    unit_price: OptionalDecimalField = Field(
        default=None, description="Unit price of the invoice line, expressed as a numeric value."
    )
    line_amount: OptionalDecimalField = Field(
        default=None, description="Amount of the invoice line, expressed as a numeric value."
    )


class invoice_details_Extraction(BaseModel):
    """Extraction model for invoice_details with repeated invoice_lines"""

    model_config = ConfigDict(extra="forbid")

    invoice_number: str = Field(description="Invoice number.")
    sender_name: str = Field(description="Sender name.")
    receiver_name: str = Field(description="Receiver name.")
    purchase_order_number: str = Field(description="Purchase order number.")
    date_of_invoice: str = Field(description="Date of invoice.")
    due_date: str = Field(description="Invoice due date.")
    payment_terms: str = Field(description="Invoice payment terms.")
    currency: str = Field(description="Invoice currency.")
    subtotal: OptionalDecimalField = Field(
        default=None, description="Invoice subtotal, as a numeric amount."
    )
    discount: OptionalDecimalField = Field(
        default=None,
        description="Invoice discount, as a numeric amount; can be null if the invoice has none.",
    )
    tax: OptionalDecimalField = Field(default=None, description="Invoice tax, as a numeric amount.")
    grand_total: OptionalDecimalField = Field(
        default=None, description="Invoice grand total, as a numeric amount."
    )
    invoice_lines: list[invoice_lines_Extraction] = Field(
        description="Repeated invoice line records containing description, quantity, unit, unit price, and line amount."
    )
