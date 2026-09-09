"""Deterministic guards for LLM-generated field metadata."""

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
