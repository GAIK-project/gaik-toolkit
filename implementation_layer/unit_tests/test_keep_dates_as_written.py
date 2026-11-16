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


def _two_dates(task: str) -> dict[str, str]:
    requirements = ExtractionRequirements(
        use_case_name="drawings",
        fields=[
            FieldSpec(field_name="drawing_date", field_type="date", description="Date"),
            FieldSpec(field_name="invoice_date", field_type="date", description="Date"),
        ],
    )
    _apply_type_overrides(requirements, original_text=task)
    return {field.field_name: field.field_type for field in requirements.fields}


@pytest.mark.parametrize(
    "line",
    [
        "- Drawing date (preserve format in string)",
        "- Drawing date: keep exactly as written",
        "- Drawing date (preserve as written)",
        "- Drawing date\n  Keep the date as written on the drawing.",
    ],
)
def test_a_rule_on_one_fields_line_keeps_only_that_field_as_text(line):
    assert _two_dates(f"{line}\n- Invoice date") == {
        "drawing_date": "str",
        "invoice_date": "date",
    }


def test_a_date_field_named_after_a_keep_word_is_no_rule():
    requirements = ExtractionRequirements(
        use_case_name="archive",
        fields=[
            FieldSpec(field_name="preservation_date", field_type="date", description="Date"),
            FieldSpec(field_name="invoice_date", field_type="date", description="Date"),
        ],
    )
    _apply_type_overrides(requirements, original_text="- Preservation date\n- Invoice date")

    assert [field.field_type for field in requirements.fields] == ["date", "date"]


@pytest.mark.parametrize(
    "rule",
    [
        "Preserve dates as written, do not convert to ISO.",
        "Keep every date exactly as written.",
    ],
)
def test_a_task_rule_still_reaches_every_date_field(rule):
    assert _two_dates(f"- Drawing date\n- Invoice date\n\n{rule}") == {
        "drawing_date": "str",
        "invoice_date": "str",
    }


def test_a_negated_keep_rule_leaves_dates_dates():
    task = "- Drawing date\n- Invoice date\n\nDo not keep dates as written; convert them to ISO."

    assert _two_dates(task) == {"drawing_date": "date", "invoice_date": "date"}


def test_a_field_called_date_does_not_hide_a_rule_for_all_dates():
    requirements = ExtractionRequirements(
        use_case_name="diary",
        fields=[
            FieldSpec(field_name="date", field_type="date", description="Entry date"),
            FieldSpec(field_name="due_date", field_type="date", description="Due date"),
        ],
    )
    task = "- Date\n- Due date\n\nPreserve dates exactly if the format cannot be inferred."
    _apply_type_overrides(requirements, original_text=task)

    assert [field.field_type for field in requirements.fields] == ["str", "str"]
