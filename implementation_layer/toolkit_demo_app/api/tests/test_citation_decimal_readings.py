"""A decimal number in a quote is not also read with its separator removed (#144)."""

from __future__ import annotations

import pytest
from api.utils.citations import value_status


@pytest.mark.parametrize(
    ("value", "quote", "expected"),
    [
        (125, "Paino: 12,5 kg", "mismatch"),
        (1250, "Hinta 12,50 EUR", "mismatch"),
        (12.5, "Paino: 12,5 kg", "match"),
        (3000, "Paino 3.000 kg", "match"),
        (1234567, "Total 1,234,567", "match"),
        (100000, "Summa 1,00,000", "match"),
    ],
)
def test_a_decimal_separator_is_not_dropped(value, quote, expected) -> None:
    assert value_status(value, quote) == expected
