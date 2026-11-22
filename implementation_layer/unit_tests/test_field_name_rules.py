"""FieldSpec's field names: readable ASCII snake_case (issue #105).

Every letter outside a-z used to become an underscore (``sää`` was ``s``) and a
camelCase name was lowercased whole (``dueDate`` was ``duedate``). Offline.
"""

from __future__ import annotations

import re

import pytest
from gaik.software_components.extractor import (
    ExtractionRequirements,
    FieldSpec,
    create_extraction_model,
)
from gaik.software_components.extractor.saved_schema import build_model, describe_model
from gaik.software_components.extractor.schema import (
    _apply_type_overrides,
    _sanitize_field_name,
)
from pydantic import ValidationError

# Anthropic's rule for a property key in a tool's input schema.
ANTHROPIC_KEY = re.compile(r"^[a-zA-Z0-9_.-]{1,64}$")


def _name(raw: str) -> str:
    return FieldSpec(field_name=raw, field_type="str", description="d").field_name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # The issue's table.
        ("toimituspäivämäärä", "toimituspaivamaara"),
        ("työmaan_sää", "tyomaan_saa"),
        ("sää", "saa"),
        ("größe", "grosse"),
        ("dueDate", "due_date"),
        ("dateOfBirth", "date_of_birth"),
        ("Order Date", "order_date"),
        # More of the same.
        ("VATNumber", "vat_number"),
        ("invoiceNumber2", "invoice_number2"),
        ("Lieferstraße", "lieferstrasse"),
        ("Ægir", "aegir"),
        ("Łódź", "lodz"),
        ("doğum_tarihi", "dogum_tarihi"),
        ("İstanbul", "istanbul"),
        ("ﬁle_name", "file_name"),
        ("Toimitus­päivä", "toimituspaiva"),  # soft hyphen
    ],
)
def test_letters_are_transliterated_and_camel_case_is_split(raw, expected):
    assert _name(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # PR #204 review: main cleans these; the PR refused them.
        ("Pinta-ala (m²)", "pinta_ala_m"),
        ("area_m²", "area_m"),
        ("volume_m³", "volume_m"),
        ("Tilavuus m³", "tilavuus_m"),
        ("pituus ½", "pituus"),
        ("x₁", "x"),
        ("Ⅳ_quarter", "quarter"),
        ("pinta_ala_m²", "pinta_ala_m"),
    ],
)
def test_numbers_that_are_not_ascii_digits_are_cleaned_as_before(raw, expected):
    assert _name(raw) == expected


@pytest.mark.parametrize(
    "name",
    [
        "invoice_number",
        "due_date",
        "a1_b2",
        "x",
        # Names main wrote; saved schemas and requirements files hold them.
        "toimitusp_iv_m_r",
        "ty_maan_s",
        "duedate",
        "gr_e",
    ],
)
def test_a_name_that_is_already_snake_case_ascii_is_unchanged(name):
    assert _name(name) == name


@pytest.mark.parametrize(
    "raw",
    [
        "toimituspäivämäärä",
        "dueDate",
        "HTTPServerError",
        "Pinta-ala (m²)",
        "ǅungla",
        "ﬁle",
        "İİ",
        "ẞTRASSE",
        "a__b",
        "_x_",
        "дата_поставки",
        "Ημερομηνία",
        "日付",
        "ΣΑΣ_value",
    ],
)
def test_the_rule_gives_the_same_name_when_applied_again(raw):
    once = _name(raw)

    assert _name(once) == once
    assert ANTHROPIC_KEY.match(once)


@pytest.mark.parametrize("raw", ["дата", "日付", "Ημερομηνία", "дата_2025"])
def test_a_name_without_an_ascii_form_gets_a_stable_fallback(raw):
    name = _name(raw)

    assert re.fullmatch(r"field_[0-9a-f]{8}", name)
    assert _name(raw) == name  # the same name every time, on every machine


def test_different_names_without_an_ascii_form_get_different_fallbacks():
    assert len({_name("дата"), _name("сумма"), _name("номер")}) == 3


@pytest.mark.parametrize("raw", ["", "2025", "²", "!!!", "2nd_date"])
def test_a_name_without_letters_or_starting_with_a_digit_is_still_refused(raw):
    with pytest.raises(ValidationError):
        _name(raw)


def test_two_names_that_used_to_fold_to_the_same_key_now_stay_apart():
    # On main both were "gr_e", and the requirements failed as a duplicate.
    requirements = ExtractionRequirements(
        use_case_name="Brief",
        fields=[
            FieldSpec(field_name="größe", field_type="str", description="Size"),
            FieldSpec(field_name="grüße", field_type="str", description="Greetings"),
        ],
    )

    assert [f.field_name for f in requirements.fields] == ["grosse", "grusse"]


def test_every_property_key_reaching_a_provider_is_ascii():
    requirements = ExtractionRequirements(
        use_case_name="Työmaapäiväkirja",
        fields=[
            FieldSpec(field_name="toimituspäivämäärä", field_type="date", description="Päivä"),
            FieldSpec(field_name="työmaan_sää", field_type="str", description="Sää"),
            FieldSpec(field_name="дата", field_type="str", description="Дата"),
            FieldSpec(field_name="Pinta-ala (m²)", field_type="float", description="Ala"),
        ],
    )
    model = create_extraction_model(requirements)
    keys = list(model.model_json_schema()["properties"])

    assert keys[:2] == ["toimituspaivamaara", "tyomaan_saa"]
    assert all(ANTHROPIC_KEY.match(key) for key in keys), keys
    # Saved schemas take these names as they are.
    assert build_model(describe_model(model)).model_json_schema() == model.model_json_schema()


def test_the_date_checks_see_the_transliterated_name_and_its_line_in_the_task():
    requirements = ExtractionRequirements(
        use_case_name="Tilaus",
        fields=[
            FieldSpec(field_name="toimituspäivämäärä", field_type="str", description="Toimitus")
        ],
    )

    _apply_type_overrides(requirements, original_text="- Toimituspäivämäärä (pp.kk.vvvv)")

    field = requirements.fields[0]
    assert field.field_type == "date"
    assert field.format == "%d.%m.%Y"


def test_container_names_follow_the_same_rule():
    assert _sanitize_field_name("lineItems") == "line_items"
    assert _sanitize_field_name("Rivit ääkkösillä") == "rivit_aakkosilla"
    assert _sanitize_field_name("") == "records"
    assert _sanitize_field_name("2026 events") == "records_2026_events"
    assert _sanitize_field_name("события") == "records"
