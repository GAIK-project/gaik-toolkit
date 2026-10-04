"""
Auto-generated schema module (do not edit manually).
"""

from gaik.software_components.extractor import OptionalDecimalField
from pydantic import BaseModel, ConfigDict, Field


class finnish_shop_receipt_items_Extraction(BaseModel):
    """Extraction model for finnish_shop_receipt_items"""

    model_config = ConfigDict(extra="forbid")

    product_name: str = Field(
        description="Product name exactly as printed on the receipt. Include discount lines (such as ETU JUUSTOT) and deposit lines (PANTTI) as items."
    )
    quantity: float | None = Field(
        default=None,
        description="Numeric number of pieces (for example 2 KPL) or weight in kg printed in the small line under the product name. When there is no such line, the quantity is 1. Never take the package size in the name (500G, 1L, 4RL) as the quantity. Read a decimal comma as a decimal point.",
    )
    unit_price: OptionalDecimalField = Field(
        default=None,
        description="Numeric price after the x in the small line under the product name (for example 1,89 EUR/kg). Return null when there is no such line. Read a decimal comma as a decimal point.",
    )
    line_amount: OptionalDecimalField = Field(
        default=None,
        description="Numeric price at the right of the line. A discount line (such as ETU JUUSTOT) has a negative line amount. Read a decimal comma as a decimal point.",
    )


class Finnish_shop_receipt_header_extraction_Extraction(BaseModel):
    """Extraction model for Finnish shop receipt header extraction with repeated items"""

    model_config = ConfigDict(extra="forbid")

    store_name: str = Field(description="The store name on the receipt.")
    store_address: str = Field(description="The store address on the receipt.")
    date: str = Field(description="The receipt date.")
    time: str = Field(description="The receipt time.")
    receipt_number: str = Field(description="The receipt number (Kuitti).")
    till_number: str = Field(description="The till number (Kassa).")
    payment_method: str = Field(description="The payment method, for example the card type.")
    total_amount: OptionalDecimalField = Field(
        default=None,
        description="The total amount (Yhteensä), extracted together with its currency. The amount must be numeric; read a decimal comma as a decimal point.",
    )
    currency: str = Field(description="The currency of the total amount (Yhteensä).")
    items: list[finnish_shop_receipt_items_Extraction] = Field(
        description="Receipt line records with product name, quantity, unit price, and line amount, including discounts and deposits."
    )
