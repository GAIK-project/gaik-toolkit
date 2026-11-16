"""Offline regression tests for #96: a task-level rule to keep dates as written
stops date normalisation, without overriding a format the task gives."""

import pytest

from gaik.software_components.extractor.schema import (
    ExtractionRequirements,
    FieldSpec,
    _apply_type_overrides,
    normalize_extracted_data,
)


def _drawing_date(task: str) -> tuple[FieldSpec, ExtractionRequirements]:
    requirements = ExtractionRequirements(
        use_case_name="drawings",
        fields=[FieldSpec(field_name="drawing_date", field_type="date", description="Date")],
    )
    _apply_type_overrides(requirements, original_text=task)
    return requirements.fields[0], requirements


@pytest.mark.parametrize(
    "rule",
    [
        "Preserve original wording, dimensions, dates, and labels.",
        "Rules:\n- Preserve dates exactly if the required format cannot be inferred.",
        "Keep all dates exactly as they appear in the drawing.",
    ],
)
def test_keep_dates_rule_keeps_the_date_as_text(rule):
    field, requirements = _drawing_date(f"Extract from drawings:\n- Drawing date\n\n{rule}")

    assert field.field_type == "str"
    assert field.format is None
    assert normalize_extracted_data({"drawing_date": "12.10.2025"}, requirements) == {
        "drawing_date": "12.10.2025"
    }


def test_a_format_on_the_fields_own_line_still_wins():
    field, _ = _drawing_date(
        "- Drawing date (DD/MM/YYYY)\n\nPreserve dates exactly if the format cannot be inferred."
    )

    assert (field.field_type, field.format) == ("date", "%d/%m/%Y")


@pytest.mark.parametrize(
    "rule",
    [
        "Preserve original wording of the notes.",
        "Keep dates in DD.MM.YYYY.",
        "Convert all dates to ISO and keep the original wording elsewhere.",
    ],
)
def test_other_rules_leave_the_date_a_date(rule):
    field, _ = _drawing_date(f"- Drawing date\n\n{rule}")

    assert field.field_type == "date"
