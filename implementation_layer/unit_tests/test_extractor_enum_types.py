"""An enum keeps the field's type where its choices fit it (issue #141 item 2).

A ``list[str]`` field with choices is a list of those choices, and a number field
whose choices are numbers stays a number. Offline: no model call.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from gaik.software_components.extractor import (
    ExtractionRequirements,
    FieldSpec,
    compare_requirements,
    create_extraction_model,
)
from gaik.software_components.extractor.saved_schema import build_model, describe_model
from gaik.software_components.extractor.schema import apply_field_policies
from gaik.software_components.vision_extractor import VisionExtractor
from gaik.software_components.vision_extractor.vision_extractor import (
    _make_schema_strict,
    _prepare_google_schema,
)
from pydantic import ValidationError


def _requirements(*fields: FieldSpec) -> ExtractionRequirements:
    return ExtractionRequirements(use_case_name="safety report", fields=list(fields))


HAZARDS = FieldSpec(
    field_name="hazard_types",
    field_type="list[str]",
    description="Hazards",
    enum=["fire", "chemical", "electrical"],
)
RATING = FieldSpec(
    field_name="rating", field_type="int", description="Rating", enum=["1", "2", "3", "4", "5"]
)


@pytest.fixture
def report() -> ExtractionRequirements:
    return _requirements(HAZARDS, RATING)


def _property(model, name: str) -> dict:
    return model.model_json_schema()["properties"][name]


def test_an_enum_on_a_list_field_gives_a_list_of_the_choices(report):
    model = create_extraction_model(report)

    assert _property(model, "hazard_types")["type"] == "array"
    assert _property(model, "hazard_types")["items"] == {
        "enum": ["fire", "chemical", "electrical"],
        "type": "string",
    }
    assert model.model_validate({"hazard_types": ["fire", "chemical"], "rating": 3}).hazard_types
    assert model.model_validate({"rating": 3}).hazard_types == []
    with pytest.raises(ValidationError):
        model.model_validate({"hazard_types": ["water"], "rating": 3})


def test_an_enum_of_numbers_on_a_number_field_keeps_the_number_type(report):
    model = create_extraction_model(report)

    assert _property(model, "rating") == {
        "anyOf": [{"enum": [1, 2, 3, 4, 5], "type": "integer"}, {"type": "null"}],
        "default": None,
        "description": "Rating",
        "title": "Rating",
    }
    assert model.model_validate({"rating": 3}).rating == 3
    assert model.model_validate({}).rating is None
    with pytest.raises(ValidationError):
        model.model_validate({"rating": 7})


def test_float_and_decimal_choices_stay_numbers():
    requirements = _requirements(
        FieldSpec(field_name="ratio", field_type="float", description="r", enum=["0.5", "1"]),
        FieldSpec(field_name="fee", field_type="decimal", description="f", enum=["9.90", "19.90"]),
    )
    model = create_extraction_model(requirements)

    assert _property(model, "ratio")["anyOf"][0] == {"enum": [0.5, 1.0], "type": "number"}
    # A decimal keeps the Decimal field's string schema and cleaner.
    assert _property(model, "fee")["anyOf"][0] == {"type": "string"}
    assert model.model_validate({"fee": "19,90 EUR"}).fee == Decimal("19.90")

    kept = apply_field_policies({"ratio": 0.5, "fee": Decimal("19.9")}, requirements)
    assert kept == {"ratio": 0.5, "fee": Decimal("19.9")}
    dropped = apply_field_policies({"ratio": 0.7, "fee": Decimal("5")}, requirements)
    assert dropped == {"ratio": None, "fee": None}


def test_the_policies_keep_values_to_the_choices_with_their_types(report):
    assert apply_field_policies(
        {"hazard_types": ["fire", "water", " chemical "], "rating": 3}, report
    ) == {"hazard_types": ["fire", "chemical"], "rating": 3}
    # A choice written as text stays text: a model saved by gaik 0.11.1 has the
    # choices as texts (review of #317). VisionExtractor matches it to its model.
    assert apply_field_policies({"hazard_types": [], "rating": "3"}, report) == {
        "hazard_types": [],
        "rating": "3",
    }
    assert apply_field_policies({"hazard_types": "fire, water", "rating": 7}, report) == {
        "hazard_types": ["fire"],
        "rating": None,
    }
    assert apply_field_policies({"hazard_types": [], "rating": 5.0}, report) == {
        "hazard_types": [],
        "rating": 5,
    }


def test_choices_that_are_not_numbers_still_replace_a_number_type():
    requirements = _requirements(
        FieldSpec(field_name="level", field_type="int", description="l", enum=["low", "high"]),
        FieldSpec(field_name="score", field_type="int", description="s", enum=["1", "1.5"]),
    )
    model = create_extraction_model(requirements)

    # As on main: the choices are labels, and the value is one of them.
    assert _property(model, "level")["anyOf"][0] == {
        "enum": ["", "low", "high"],
        "type": "string",
    }
    assert _property(model, "score")["anyOf"][0]["type"] == "string"
    assert apply_field_policies({"level": "high", "score": "2"}, requirements) == {
        "level": "high",
        "score": None,
    }


def test_text_choices_on_a_decimal_field_replace_its_type_as_on_int():
    requirements = _requirements(
        FieldSpec(field_name="tier", field_type="decimal", description="t", enum=["low", "high"])
    )
    model = create_extraction_model(requirements)

    # The choices are labels, as on an int or float field: not a DecimalField that
    # refuses every label while the policies refuse every number.
    assert _property(model, "tier")["anyOf"][0] == {
        "enum": ["", "low", "high"],
        "type": "string",
    }
    assert model.model_validate({"tier": "high"}).tier == "high"
    assert model.model_validate({}).tier is None
    with pytest.raises(ValidationError):
        model.model_validate({"tier": "12.50"})
    assert apply_field_policies({"tier": "high"}, requirements) == {"tier": "high"}
    assert apply_field_policies({"tier": "medium"}, requirements) == {"tier": None}
    rebuilt = build_model(describe_model(model))
    assert rebuilt.model_json_schema() == model.model_json_schema()


def test_a_number_default_on_a_decimal_field_with_labels_is_one_of_its_texts():
    requirements = _requirements(
        FieldSpec(
            field_name="tier",
            field_type="decimal",
            description="t",
            enum=["low", "high"],
            default="1.5",
            has_explicit_default=True,
        )
    )
    model = create_extraction_model(requirements)

    assert model.model_validate({"tier": "1.5"}).tier == "1.5"
    assert model.model_validate({}).tier == "1.5"
    # The model reads back what it writes.
    written = model.model_validate({"tier": "low"}).model_dump_json()
    assert model.model_validate_json(written).tier == "low"
    assert model.model_validate_json(model.model_validate({}).model_dump_json()).tier == "1.5"


def test_building_a_model_leaves_the_field_specs_as_they_were():
    level = FieldSpec(
        field_name="level",
        field_type="int",
        description="l",
        enum=["low", "high"],
        default="1",
        has_explicit_default=True,
    )
    label = FieldSpec(
        field_name="label",
        field_type="str",
        description="s",
        enum=["a", "b"],
        default="c",
        has_explicit_default=True,
    )
    requirements = _requirements(level, label)

    model = create_extraction_model(requirements)
    create_extraction_model(requirements)

    assert level.enum == ["low", "high"] and label.enum == ["a", "b"]
    # The default is still one of the values the model takes.
    assert model.model_validate({}).level == 1
    assert model.model_validate({"label": "c"}).label == "c"
    # A mixed list of a number and texts once broke the comparison's sorting.
    assert compare_requirements(requirements, requirements).changed == []


def test_a_number_field_whose_only_choice_is_empty_has_no_choices():
    requirements = _requirements(
        FieldSpec(field_name="count", field_type="int", description="c", enum=[""])
    )
    model = create_extraction_model(requirements)

    assert _property(model, "count")["anyOf"][0] == {"type": "integer"}
    assert model.model_validate({"count": 12}).count == 12
    assert apply_field_policies({"count": 12}, requirements) == {"count": 12}


@pytest.mark.parametrize(
    "enum",
    [["Kyllä", "Ei"], ["true", "false"]],
)
def test_yes_no_choices_on_a_bool_field_are_kept_as_on_main(enum):
    requirements = _requirements(
        FieldSpec(field_name="injured", field_type="bool", description="i", enum=enum)
    )
    model = create_extraction_model(requirements)

    assert _property(model, "injured")["anyOf"][0] == {"enum": ["", *enum], "type": "string"}
    assert model.model_validate({"injured": enum[0]}).injured == enum[0]
    assert apply_field_policies({"injured": enum[1]}, requirements) == {"injured": enum[1]}
    assert apply_field_policies({"injured": "maybe"}, requirements) == {"injured": None}


def test_an_explicit_default_counts_as_a_choice():
    requirements = _requirements(
        FieldSpec(
            field_name="priority",
            field_type="int",
            description="p",
            enum=["1", "2"],
            default="3",
            has_explicit_default=True,
        )
    )
    model = create_extraction_model(requirements)

    assert _property(model, "priority")["enum"] == [1, 2, 3]
    assert model.model_validate({}).priority == 3
    assert apply_field_policies({"priority": 9}, requirements) == {"priority": 3}


def test_gemini_gets_the_number_type_without_number_enum_entries(report):
    model = create_extraction_model(report)
    google = _prepare_google_schema(model.model_json_schema())

    # Gemini's Schema takes enum entries as strings only.
    assert google["properties"]["rating"] == {
        "type": "integer",
        "nullable": True,
        "description": "Rating",
    }
    assert google["properties"]["hazard_types"]["items"]["enum"] == [
        "fire",
        "chemical",
        "electrical",
    ]
    strict = _make_schema_strict(model.model_json_schema())
    assert strict["properties"]["rating"]["anyOf"][0]["enum"] == [1, 2, 3, 4, 5]


def test_vision_extractor_validates_typed_choices(report, monkeypatch):
    model = create_extraction_model(report)
    extractor = VisionExtractor(api_config={"api_key": "unused", "model": "test-model"})
    # What Gemini, without the number enum, may answer: a number outside the
    # choices and a list with one item that is not a choice.
    canned = {"hazard_types": ["fire", "flood"], "rating": 9}
    monkeypatch.setattr(extractor, "_extract", lambda *args, **kwargs: (canned, None))
    monkeypatch.setattr(extractor, "_check_input_limits", lambda paths: None)

    result = extractor.extract(
        file_paths=["report.png"],
        user_requirements="hazards and rating",
        extraction_model=model,
        requirements=report,
    )

    assert result.data == {"hazard_types": ["fire"], "rating": None}

    canned.update(hazard_types=["chemical"], rating=4)
    result = extractor.extract(
        file_paths=["report.png"],
        user_requirements="hazards and rating",
        extraction_model=model,
        requirements=report,
    )
    assert result.data == {"hazard_types": ["chemical"], "rating": 4}

    # A provider that writes the number as text still gets a number here.
    canned.update(rating="4")
    result = extractor.extract(
        file_paths=["report.png"],
        user_requirements="hazards and rating",
        extraction_model=model,
        requirements=report,
    )
    assert result.data == {"hazard_types": ["chemical"], "rating": 4}


def test_typed_choices_are_saved_as_data(report):
    model = create_extraction_model(report)

    rebuilt = build_model(describe_model(model))

    assert rebuilt.model_json_schema() == model.model_json_schema()
