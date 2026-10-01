"""Tests for reading the single extraction of the priced example."""

from decimal import Decimal

import pytest
from api.utils.order_extraction import split_order, to_number

EXTRACTION = {
    "po_number": "PO-2025-15903",
    "customer": "AutoTech Manufacturing Corp.",
    "order_date": "12/10/2025",
    "buyer": "Patricia Henderson",
    "sales_person": None,
    "shipping_address": "2750 Industrial Parkway, Detroit, MI 48201",
    "payment_terms": "Net 30",
    "shipping_cost": Decimal("450.00"),
    "tax_rate": 6.0,
    "po_items": [
        {"material_number": "MAT-2401", "quantity": 200, "description": "Aluminum Angle Bar"},
        {"material_number": "MAT-3567", "quantity": 50, "description": "Stainless Steel Sheet"},
    ],
    "additional_fees": [
        {"material_number": "MAT-2401", "fee_name": "Cutting Fee", "quantity": 200},
    ],
}


def test_the_extraction_is_split_into_header_lines_and_fees():
    parts = split_order(EXTRACTION)

    assert list(parts.header)[:3] == ["po_number", "customer", "order_date"]
    assert "po_items" not in parts.header
    assert [line["material_number"] for line in parts.lines] == ["MAT-2401", "MAT-3567"]
    assert [fee["fee_name"] for fee in parts.fees] == ["Cutting Fee"]


def test_the_header_values_the_totals_need_are_found_by_meaning():
    parts = split_order(EXTRACTION)

    assert parts.po_number == "PO-2025-15903"
    assert parts.customer == "AutoTech Manufacturing Corp."
    assert parts.shipping == 450.0
    assert parts.tax_rate == 6.0
    assert parts.shipping_address.startswith("2750 Industrial Parkway")


def test_other_field_names_work_too():
    parts = split_order(
        {
            "order_number": "KIS-1",
            "Customer_Name": "Kestilä Oy",
            "shipping_charge": "$1,200.50",
            "tax_rate_percent": "8.5 %",
            "items": [{"material_number": "M1"}],
            "fees": [{"material_number": "M1", "fee": "Cutting Fee"}],
        }
    )

    assert (parts.po_number, parts.customer) == ("KIS-1", "Kestilä Oy")
    assert (parts.shipping, parts.tax_rate) == (1200.5, 8.5)
    assert len(parts.lines) == 1
    assert len(parts.fees) == 1


def test_a_missing_shipping_or_tax_is_zero_or_none():
    parts = split_order({"po_number": "P", "po_items": []})

    assert parts.shipping == 0.0
    assert parts.tax_rate is None
    assert parts.lines == []
    assert parts.fees == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (450, 450.0),
        (Decimal("450.50"), 450.5),
        ("$1,234.50", 1234.5),
        ("6 %", 6.0),
        ("200 cuts", 200.0),
        ("", None),
        (None, None),
        ("n/a", None),
        (True, None),
    ],
)
def test_numbers_are_read_from_values_and_text(value, expected):
    assert to_number(value) == expected
