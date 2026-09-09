"""Auto-generated schema — do not edit manually."""

import decimal
from decimal import Decimal
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

import re as _re
from decimal import Decimal
from typing import Annotated

from pydantic import BeforeValidator, WithJsonSchema

_CURRENCY_NOISE_RE = _re.compile(
    r"(?i)\b(EUR|USD|GBP|JPY|CHF|SEK|NOK|DKK|CAD|AUD|INR)\b|[€$£¥₹]"
)
_SINGLE_AMOUNT_RE = _re.compile(r"^[-+]?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$")


def _clean_decimal_string(v):
    """Strip currency/unit noise before Decimal parsing; reject (return None)
    ambiguous or multi-number input rather than fabricating a value. See
    gaik.software_components.extractor.schema._clean_decimal_string for the
    full policy this mirrors."""
    if not isinstance(v, str):
        return v
    s = v.strip()
    if not s:
        return None
    s = _CURRENCY_NOISE_RE.sub("", s).strip()
    if not s:
        return None
    if not _SINGLE_AMOUNT_RE.match(s):
        return None
    return s.replace(",", "")


DecimalField = Annotated[
    Decimal, WithJsonSchema({"type": "string"}), BeforeValidator(_clean_decimal_string)
]
OptionalDecimalField = Annotated[
    Decimal | None,
    WithJsonSchema({"anyOf": [{"type": "string"}, {"type": "null"}]}),
    BeforeValidator(_clean_decimal_string),
]


class purchase_order_line_item_Extraction(BaseModel):
    """Extraction model for purchase_order_line_item"""
    model_config = ConfigDict(extra='forbid')

    item_number: str = Field(description='Item number (e.g., 010, 020)')
    complete_description: str = Field(description='Complete description')
    quantity: str = Field(description='Quantity (text string including the unit, e.g., "8.600 LB")')
    price_per_currency: OptionalDecimalField = Field(description='Price per currency', default=None)
    material_number: str = Field(description='Material number')

class purchase_order_header_extraction_Extraction(BaseModel):
    """Extraction model for purchase_order_header_extraction with repeated line_items"""
    model_config = ConfigDict(extra='forbid')

    purchase_order_date: str = Field(description='Purchase order date (DD/MM/YYYY format when unambiguous)')
    delivery_date: str = Field(description='Delivery date (DD/MM/YYYY format when unambiguous)')
    purchase_order_number: str = Field(description='Purchase order number (separated by a dash after every 4 digits)')
    supplier_number: str = Field(description='Supplier number')
    shipping_address: str = Field(description='Shipping address (Format: company name, street number, postal code, city, country)')
    line_items: list[purchase_order_line_item_Extraction] = Field(description='Repeated structured line items in the purchase order.')
