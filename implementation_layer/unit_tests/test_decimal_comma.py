"""A decimal written with a decimal comma keeps its value.

A model copies an amount as the document writes it. On a Finnish invoice that is
"150,00" or "551,57 EUR"; the Decimal cleaner used to turn every such string into
None, so invoice line prices came back null from the extractor and the vision
extractor alike (found by the component-check skill).
"""

from decimal import Decimal

import pytest
from gaik.software_components.extractor.schema import (
    DECIMAL_PERSISTED_HELPER_SOURCE,
    ChildRequirements,
    ExtractionRequirements,
    FieldSpec,
    _clean_decimal_string,
    _create_parent_with_nested_list_model,
)
from gaik.software_components.vision_extractor.vision_extractor import (
    _wrap_model_for_verification,
)

COMMA_DECIMALS = [
    ("150,00", "150.00"),
    ("18,9", "18.9"),
    ("551,57 EUR", "551.57"),
    ("€ 45,00", "45.00"),
    ("1 234,56 EUR", "1234.56"),
    ("1\u00a0234,56", "1234.56"),  # no-break space, as locale formatting writes it
    ("1\u202f234,56", "1234.56"),  # narrow no-break space
    ("1.234,56", "1234.56"),
    ("12 345 678,90", "12345678.90"),
    ("-1 234,50", "-1234.50"),
]
# One comma or dot before exactly three digits keeps the reading it had before.
UNCHANGED = [("1,234", "1234"), ("12,345", "12345"), ("1.234", "1.234"), ("1,234.56", "1234.56")]
REJECTED = [
    "1 234",  # space grouping without a fraction could be two numbers
    "1.234.567",
    "1 234.567,89",  # mixed group separators
    "1 23,45",  # a group that is not three digits
    "12 3456,7",
    "1,234,56",
    "1,",
    ",5",
    "1 234,56 7",
]
# A currency marker between digits separates two amounts. Stripping it first would
# join them: "2€ 550,00" into "2 550,00", read as 2550.00.
CURRENCY_BETWEEN_DIGITS = ["2€ 550,00", "2 EUR 550,00", "2€550", "12,40 € 3,50", "5 $ 1.20"]


@pytest.mark.parametrize(("raw", "expected"), COMMA_DECIMALS)
def test_comma_decimal_is_read(raw, expected):
    assert _clean_decimal_string(raw) == expected


@pytest.mark.parametrize(("raw", "expected"), UNCHANGED)
def test_dot_notation_readings_stay(raw, expected):
    assert _clean_decimal_string(raw) == expected


@pytest.mark.parametrize("raw", REJECTED)
def test_malformed_or_ambiguous_is_still_rejected(raw):
    assert _clean_decimal_string(raw) is None


@pytest.mark.parametrize("raw", CURRENCY_BETWEEN_DIGITS)
def test_currency_marker_between_digits_is_rejected(raw):
    assert _clean_decimal_string(raw) is None


def test_saved_schema_helper_reads_the_same_values():
    # A saved schema.py carries its own copy of the cleaner; it must agree.
    namespace: dict = {}
    exec(compile(DECIMAL_PERSISTED_HELPER_SOURCE, "<schema.py>", "exec"), namespace)  # noqa: S102
    saved = namespace["_clean_decimal_string"]

    for raw in [r for r, _ in COMMA_DECIMALS + UNCHANGED] + REJECTED + CURRENCY_BETWEEN_DIGITS:
        assert saved(raw) == _clean_decimal_string(raw), raw


def _invoice_model():
    parent = ExtractionRequirements(
        use_case_name="Invoice",
        fields=[
            FieldSpec(field_name="invoice_number", field_type="str", description="Number"),
            FieldSpec(field_name="total_amount", field_type="decimal", description="Total"),
        ],
    )
    rows = ExtractionRequirements(
        use_case_name="Invoice row",
        fields=[
            FieldSpec(field_name="description", field_type="str", description="Row"),
            FieldSpec(field_name="quantity", field_type="int", description="Quantity"),
            FieldSpec(field_name="unit_price", field_type="decimal", description="Unit price"),
            FieldSpec(field_name="line_total", field_type="decimal", description="Row total"),
        ],
    )
    child = ChildRequirements(
        container_name="line_items", container_description="Invoice rows", requirements=rows
    )
    return _create_parent_with_nested_list_model(parent_requirements=parent, children=[child])


# The shape of the raw answers Azure gpt-6-luna gave for the component-check invoice.
RAW_ANSWER = {
    "invoice_number": "INV-2026-0042",
    "total_amount": "551,57 EUR",
    "line_items": [
        {
            "description": "Pumpun huolto",
            "quantity": 2,
            "unit_price": "150,00",
            "line_total": "300,00",
        },
        {
            "description": "Tiivistesarja",
            "quantity": 5,
            "unit_price": "18,90",
            "line_total": "94,50",
        },
    ],
}


def test_nested_line_item_decimals_survive_validation():
    data = _invoice_model().model_validate(RAW_ANSWER)

    assert data.total_amount == Decimal("551.57")
    assert [(r.unit_price, r.line_total) for r in data.line_items] == [
        (Decimal("150.00"), Decimal("300.00")),
        (Decimal("18.90"), Decimal("94.50")),
    ]


def test_verification_wrapped_rows_read_comma_decimal():
    # VisionExtractor(include_verification=True) validates this wrapped model first.
    def wrap(value):
        return {"value": value, "confidence_score": 0.9, "confidence_reason": "on the page"}

    raw = {
        "invoice_number": wrap("INV-2026-0042"),
        "total_amount": wrap("551,57"),
        "line_items": [
            {key: wrap(value) for key, value in row.items()} for row in RAW_ANSWER["line_items"]
        ],
    }
    data = _wrap_model_for_verification(_invoice_model()).model_validate(raw)

    assert data.total_amount.value == Decimal("551.57")
    assert data.line_items[0].unit_price.value == Decimal("150.00")
    assert data.line_items[1].line_total.value == Decimal("94.50")
