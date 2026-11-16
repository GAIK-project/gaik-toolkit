"""Offline regression tests for #106: the date keyword fallback retypes only text
fields, and only for names and descriptions that name a date."""

import pytest

from gaik.software_components.extractor.schema import (
    ExtractionRequirements,
    FieldSpec,
    _apply_type_overrides,
)


def _typed(name: str, field_type: str, description: str = "See the task") -> FieldSpec:
    requirements = ExtractionRequirements(
        use_case_name="case",
        fields=[FieldSpec(field_name=name, field_type=field_type, description=description)],
    )
    _apply_type_overrides(requirements, original_text="")
    return requirements.fields[0]


@pytest.mark.parametrize(
    ("name", "field_type", "description"),
    [
        ("data_quality", "float", "Quality score of the data"),
        ("date_entries", "list[dict]", "Entries per date"),
        ("raw_data", "str", "Raw text from the form"),
        ("data", "str", "Everything else"),
        ("history", "str", "Tarihsel bilgi"),
        ("invoice_number", "str", "Number printed next to the invoice date"),
    ],
)
def test_field_that_is_not_a_date_keeps_its_type(name, field_type, description):
    assert _typed(name, field_type, description).field_type == field_type


def test_date_count_stays_an_integer_count():
    assert _typed("date_count", "int").field_type == "int"
    # A count the model typed as text gets the integer repair, not a date type.
    assert _typed("date_count", "str", "How many dates are listed").field_type == "int"


@pytest.mark.parametrize(
    ("name", "description"),
    [
        ("levering", "Leveringsdato for ordren"),
        ("data_consegna", "Consegna"),
        ("teslim", "Teslim tarihi"),
        ("issued", "Date of issue"),
        ("invoice", "Invoice date; printed top right"),
    ],
)
def test_date_the_model_typed_as_text_is_still_a_date(name, description):
    assert _typed(name, "str", description).field_type == "date"
