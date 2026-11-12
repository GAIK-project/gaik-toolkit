"""Deterministic guards for LLM-generated field metadata."""

import pytest
from gaik.software_components.extractor.schema import (
    ExtractionRequirements,
    FieldSpec,
    _apply_type_overrides,
    normalize_extracted_data,
)


def _requirements(*fields: FieldSpec) -> ExtractionRequirements:
    return ExtractionRequirements(use_case_name="test", fields=list(fields))


def test_invalid_llm_date_format_is_cleared_and_normalizes_to_iso():
    requirements = _requirements(
        FieldSpec(
            field_name="order_date",
            field_type="date",
            description="Order Date",
            format="date",
        )
    )

    _apply_type_overrides(requirements, original_text="- Order Date")

    assert requirements.fields[0].format is None
    assert normalize_extracted_data({"order_date": "October 12, 2025"}, requirements) == {
        "order_date": "2025-10-12"
    }


def test_normalizer_rejects_invalid_format_even_without_schema_cleanup():
    requirements = _requirements(
        FieldSpec(
            field_name="delivery_date",
            field_type="date",
            description="Delivery Date",
            format="lowercase_with_underscores",
        )
    )

    assert normalize_extracted_data({"delivery_date": "December 01, 2025"}, requirements) == {
        "delivery_date": "2025-12-01"
    }


def test_date_format_is_scoped_to_its_own_field():
    requirements = _requirements(
        FieldSpec(
            field_name="order_date",
            field_type="date",
            description="Order Date",
            format="date",
        ),
        FieldSpec(
            field_name="delivery_date",
            field_type="date",
            description="Delivery Date",
            format="lowercase_with_underscores",
        ),
    )
    task = """
    - Order Date
    - Delivery Date (Format: DD/MM/YYYY).
    """

    _apply_type_overrides(requirements, original_text=task)

    by_name = {field.field_name: field for field in requirements.fields}
    assert by_name["order_date"].format is None
    assert by_name["delivery_date"].format == "%d/%m/%Y"


def test_explicit_global_date_format_applies_to_every_date():
    requirements = _requirements(
        FieldSpec(field_name="order_date", field_type="date", description="Order Date"),
        FieldSpec(field_name="delivery_date", field_type="date", description="Delivery Date"),
    )
    task = """
    Use DD.MM.YYYY for all dates.
    - Order Date
    - Delivery Date
    """

    _apply_type_overrides(requirements, original_text=task)

    assert [field.format for field in requirements.fields] == ["%d.%m.%Y", "%d.%m.%Y"]


def test_date_preserve_instruction_keeps_string_representation():
    requirements = _requirements(
        FieldSpec(
            field_name="drawing_date",
            field_type="date",
            description="Drawing Date",
            format="date",
        )
    )

    _apply_type_overrides(
        requirements,
        original_text="- Drawing Date (preserve format in string)",
    )

    field = requirements.fields[0]
    assert field.field_type == "str"
    assert field.format is None
    assert normalize_extracted_data({"drawing_date": "12 OCT 25"}, requirements) == {
        "drawing_date": "12 OCT 25"
    }


def test_plain_quantity_is_repaired_to_integer():
    requirements = _requirements(
        FieldSpec(field_name="quantity", field_type="str", description="Quantity")
    )

    _apply_type_overrides(requirements, original_text="- Quantity")

    assert requirements.fields[0].field_type == "int"


def test_unit_bearing_quantity_remains_string():
    requirements = _requirements(
        FieldSpec(field_name="quantity", field_type="str", description="Quantity")
    )

    _apply_type_overrides(
        requirements,
        original_text="- Quantity (text string including the unit, e.g. '4.200 kg')",
    )

    assert requirements.fields[0].field_type == "str"


def test_unrequested_pattern_and_non_date_format_are_cleared():
    requirements = _requirements(
        FieldSpec(
            field_name="buyer",
            field_type="str",
            description="Buyer",
            pattern="^.*$",
            format="string",
        )
    )

    _apply_type_overrides(requirements, original_text="- Buyer")

    field = requirements.fields[0]
    assert field.pattern is None
    assert field.format is None


def test_format_after_a_comma_in_the_fields_own_bullet_is_kept():
    requirements = _requirements(
        FieldSpec(
            field_name="delivery_date",
            field_type="date",
            description="The delivery date, formatted DD/MM/YYYY (for example 05/03/2027).",
        )
    )
    task = (
        "- `po_number`: the purchase order number as written.\n"
        "- `delivery_date`: the delivery date, formatted `DD/MM/YYYY` (for example "
        "`05/03/2027`). Convert from another written form only when day, month and year "
        "are all stated.\n"
    )

    _apply_type_overrides(requirements, original_text=task)

    assert requirements.fields[0].format == "%d/%m/%Y"
    assert normalize_extracted_data({"delivery_date": "10/08/2026"}, requirements) == {
        "delivery_date": "10/08/2026"
    }


def test_snake_case_heading_and_its_paragraph_carry_the_format():
    requirements = _requirements(
        FieldSpec(
            field_name="observation_date",
            field_type="date",
            description="Date the fault was observed, as DD/MM/YYYY (example: 29/09/2026).",
        )
    )
    task = (
        "### observation_date (optional)\n"
        "Date the fault was observed, as `DD/MM/YYYY` (example: `29/09/2026`).\n"
        "\n"
        "### observation_time (optional)\n"
        "Time the fault was observed, as HH:MM.\n"
    )

    _apply_type_overrides(requirements, original_text=task)

    assert requirements.fields[0].format == "%d/%m/%Y"
    assert normalize_extracted_data({"observation_date": "26/07/2026"}, requirements) == {
        "observation_date": "26/07/2026"
    }


def test_description_format_is_the_fallback_when_the_task_text_has_none():
    requirements = _requirements(
        FieldSpec(
            field_name="invoice_date",
            field_type="date",
            description="Invoice date, written as pp.kk.vvvv.",
        )
    )

    _apply_type_overrides(
        requirements, original_text="Extract the invoice number and the invoice date."
    )

    assert requirements.fields[0].format == "%d.%m.%Y"
    assert normalize_extracted_data({"invoice_date": "2026-08-10"}, requirements) == {
        "invoice_date": "10.08.2026"
    }


def test_prose_line_still_scopes_a_format_to_its_own_field():
    requirements = _requirements(
        FieldSpec(field_name="order_date", field_type="date", description="Order date"),
        FieldSpec(field_name="delivery_date", field_type="date", description="Delivery date"),
    )
    task = "Extract the order date, the delivery date (DD/MM/YYYY) and the total.\n"

    _apply_type_overrides(requirements, original_text=task)

    by_name = {field.field_name: field for field in requirements.fields}
    assert by_name["order_date"].format is None
    assert by_name["delivery_date"].format == "%d/%m/%Y"


@pytest.mark.parametrize(
    "task",
    [
        "Order date, delivery date (DD/MM/YYYY) and the total.\n",
        "- Order date, delivery date (DD/MM/YYYY), total amount\n",
        "1. Order date, delivery date (DD/MM/YYYY)\n",
        "- `order_date`, `delivery_date` (DD/MM/YYYY)\n",
    ],
)
def test_first_field_of_a_line_that_lists_several_does_not_take_a_neighbours_format(task):
    requirements = _requirements(
        FieldSpec(field_name="order_date", field_type="date", description="Order date"),
        FieldSpec(field_name="delivery_date", field_type="date", description="Delivery date"),
    )

    _apply_type_overrides(requirements, original_text=task)

    by_name = {field.field_name: field for field in requirements.fields}
    assert by_name["order_date"].format is None
    assert by_name["delivery_date"].format == "%d/%m/%Y"


@pytest.mark.parametrize(
    "task",
    [
        "- **Delivery date** \u2013 when the goods arrive, written DD/MM/YYYY\n",
        "- `delivery_date` (date): when the goods arrive, written DD/MM/YYYY\n",
        "Delivery date = arrival of the goods, written DD/MM/YYYY\n",
    ],
)
def test_field_that_heads_its_own_line_keeps_the_format_after_a_comma(task):
    requirements = _requirements(
        FieldSpec(field_name="delivery_date", field_type="date", description="Delivery date")
    )

    _apply_type_overrides(requirements, original_text=task)

    assert requirements.fields[0].format == "%d/%m/%Y"


def test_all_dates_format_in_the_task_wins_over_a_format_in_the_description():
    requirements = _requirements(
        FieldSpec(
            field_name="order_date",
            field_type="date",
            description="Order date, printed on the form as DD/MM/YYYY",
        ),
        FieldSpec(field_name="delivery_date", field_type="date", description="Delivery date"),
    )
    task = """
    Use YYYY-MM-DD for all dates.
    - Order Date
    - Delivery Date (DD.MM.YYYY)
    """

    _apply_type_overrides(requirements, original_text=task)

    by_name = {field.field_name: field for field in requirements.fields}
    assert by_name["order_date"].format == "%Y-%m-%d"
    # The field's own line still wins over the all-dates format.
    assert by_name["delivery_date"].format == "%d.%m.%Y"
