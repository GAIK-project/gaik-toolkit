"""
Auto-generated schema module (do not edit manually).
"""

from gaik.software_components.extractor import OptionalDecimalField
from pydantic import BaseModel, ConfigDict, Field


class finnish_shop_receipt_items_Extraction(BaseModel):
    """Extraction model for finnish_shop_receipt_items"""

    model_config = ConfigDict(extra="forbid")

    product_name: str = Field(
        description="Product name exactly as printed on the receipt. Discount lines (such as ETU JUUSTOT) and the deposit line (PANTTI) are also items."
    )
    quantity: float | None = Field(
        default=None,
        description="Numeric number of pieces (for example 2 KPL) or weight in kg printed in the small line under the product name. When there is no such line, use 1. Never use the package size in the name (500G, 1L, 4RL) as the quantity. Read a decimal comma as a decimal point.",
    )
    unit_price: OptionalDecimalField = Field(
        default=None,
        description="Numeric price after the x in the small line under the product name (for example 1,89 EUR/kg). Return null when there is no such line. Read a decimal comma as a decimal point.",
    )
    line_amount: OptionalDecimalField = Field(
        default=None,
        description="Numeric price at the right of the line. A discount line (such as ETU JUUSTOT) has a negative line amount. Include the deposit line (PANTTI) as an item. Read a decimal comma as a decimal point.",
    )


class Finnish_shop_receipt_header_extraction_Extraction(BaseModel):
    """Extraction model for Finnish shop receipt header extraction with repeated items"""

    model_config = ConfigDict(extra="forbid")

    store_name: str = Field(description="The store name on the receipt.")
    store_address: str = Field(description="The store address on the receipt.")
    date: str = Field(description="The date of the receipt.")
    time: str = Field(description="The time on the receipt.")
    receipt_number: str = Field(description="The receipt number (Kuitti).")
    till_number: str = Field(description="The till number (Kassa).")
    payment_method: str = Field(description="The payment method (for example the card type).")
    total_amount: OptionalDecimalField = Field(
        default=None,
        description="The total amount (Yhteensä), accompanied by its currency. The amount should be numeric: read a decimal comma as a decimal point.",
    )
    currency: str = Field(description="The currency of the total amount (Yhteensä).")
    items: list[finnish_shop_receipt_items_Extraction] = Field(
        description="Receipt line records with product name, quantity, unit price, and line amount, including discounts and deposits."
    )
