"""Offline regression tests for #105: field names keep non-ASCII letters, camelCase
is split, and the field's label is still found in the task text."""

import pytest

from gaik.software_components.extractor.schema import (
    ExtractionRequirements,
    FieldSpec,
    _apply_type_overrides,
    _sanitize_field_name,
)


def _name(raw: str) -> str:
    return FieldSpec(field_name=raw, field_type="str", description="x").field_name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("toimituspäivämäärä", "toimituspäivämäärä"),
        ("työmaan_sää", "työmaan_sää"),
        ("sää", "sää"),
        ("größe", "größe"),
        ("dueDate", "due_date"),
        ("dateOfBirth", "date_of_birth"),
        ("Order Date", "order_date"),
        ("order_date", "order_date"),
        ("invoice_number_2", "invoice_number_2"),
        ("VAT number", "vat_number"),
    ],
)
def test_field_name_is_readable_snake_case(raw, expected):
    assert _name(raw) == expected


def test_list_container_name_keeps_its_letters():
    assert _sanitize_field_name("työmaan_sää") == "työmaan_sää"


def test_names_that_used_to_fold_together_stay_apart():
    requirements = ExtractionRequirements(
        use_case_name="case",
        fields=[
            FieldSpec(field_name="sää", field_type="str", description="Weather"),
            FieldSpec(field_name="s", field_type="str", description="Something"),
        ],
    )

    assert [f.field_name for f in requirements.fields] == ["sää", "s"]


@pytest.mark.parametrize(
    ("raw", "task_line", "expected_format"),
    [
        ("dueDate", "- dueDate (DD.MM.YYYY)", "%d.%m.%Y"),
        ("toimituspäivämäärä", "- Toimituspäivämäärä (DD.MM.YYYY)", "%d.%m.%Y"),
    ],
)
def test_format_on_the_fields_own_line_is_found(raw, task_line, expected_format):
    requirements = ExtractionRequirements(
        use_case_name="case",
        fields=[FieldSpec(field_name=raw, field_type="str", description="See the task")],
    )

    _apply_type_overrides(requirements, original_text=task_line)

    field = requirements.fields[0]
    assert (field.field_type, field.format) == ("date", expected_format)
