"""Reading the result of the priced example's single extraction.

One extraction returns the header fields of the purchase order, one entry per order line
(with the details of its BOM) and one entry per additional fee. The schema comes from the
schema generator, so its field names are found by what they mean, not by exact spelling.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any


def to_number(value: Any) -> float | None:
    """A number from 450, Decimal('450.00'), "$1,234.50" or "6 %"; None when there is none."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float | Decimal):
        return float(value)
    match = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(value))
    if not match:
        return None
    try:
        return float(Decimal(match.group().replace(",", "")))
    except InvalidOperation:
        return None


def pick(row: dict[str, Any], pattern: str) -> Any:
    """The value of the first field whose name matches the pattern."""
    for key, value in row.items():
        if re.search(pattern, key, re.IGNORECASE):
            return value
    return None


def text_of(value: Any) -> str | None:
    """A cleaned string, or None for an empty value."""
    cleaned = " ".join(str(value).split()) if value is not None else ""
    return cleaned or None


@dataclass
class OrderParts:
    """The header, order lines and fee entries of one extraction."""

    header: dict[str, Any] = field(default_factory=dict)
    lines: list[dict[str, Any]] = field(default_factory=list)
    fees: list[dict[str, Any]] = field(default_factory=list)

    @property
    def po_number(self) -> str | None:
        return text_of(pick(self.header, r"(po|order).*(number|no)|^po$"))

    @property
    def customer(self) -> str | None:
        return text_of(pick(self.header, r"customer"))

    @property
    def shipping_address(self) -> str | None:
        return text_of(pick(self.header, r"shipping.*address|delivery.*address"))

    @property
    def shipping(self) -> float:
        """The shipping charge; 0 when the PO states none."""
        return to_number(pick(self.header, r"(shipping|freight).*(cost|charge|amount|fee)")) or 0.0

    @property
    def tax_rate(self) -> float | None:
        """The tax rate in percent."""
        return to_number(pick(self.header, r"^tax"))


def split_order(data: dict[str, Any]) -> OrderParts:
    """Separate an extraction into its header fields, order lines and fee entries."""
    parts = OrderParts()
    for key, value in data.items():
        if not isinstance(value, list):
            parts.header[key] = value
            continue
        rows = [row for row in value if isinstance(row, dict)]
        is_fees = "fee" in key.lower() or any("fee" in name.lower() for row in rows for name in row)
        (parts.fees if is_fees else parts.lines).extend(rows)
    return parts
