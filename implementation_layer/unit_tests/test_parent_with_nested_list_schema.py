"""Tests for parent object + repeated child collection schema support."""

from __future__ import annotations

from pathlib import Path

import pytest

from gaik.software_components.extractor.schema import (
    CompositeExtractionRequirements,
    ExtractionRequirements,
    FieldSpec,
    _build_parse_requirements_prompt,
    _create_parent_with_nested_list_model,
    _ensure_no_list_dict_fields,
)
from gaik.software_components.vision_extractor.vision_extractor import (
    VisionExtractor,
    _load_saved_requirements,
    _load_saved_schema,
    _make_schema_strict,
    _save_requirements,
    _save_schema_to_python,
)


def _requirements(use_case_name: str, fields: list[FieldSpec]) -> ExtractionRequirements:
    return ExtractionRequirements(use_case_name=use_case_name, fields=fields)


@pytest.fixture()
def parent_requirements() -> ExtractionRequirements:
    return _requirements(
        "document_parent",
        [
            FieldSpec(
                field_name="document_number",
                field_type="str",
                description="Document number",
            ),
            FieldSpec(field_name="date", field_type="date", description="Document date"),
        ],
    )


@pytest.fixture()
def child_requirements() -> ExtractionRequirements:
    return _requirements(
        "document_row",
        [
            FieldSpec(field_name="item_number", field_type="str", description="Item number"),
            FieldSpec(field_name="quantity", field_type="int", description="Quantity"),
            FieldSpec(field_name="price", field_type="decimal", description="Price"),
        ],
    )


def test_combined_model_has_parent_fields_and_typed_child_rows(
    parent_requirements: ExtractionRequirements,
    child_requirements: ExtractionRequirements,
):
    model = _create_parent_with_nested_list_model(
        parent_requirements=parent_requirements,
        child_requirements=child_requirements,
        child_container_name="line_items",
        child_container_description="Line item rows",
    )

    result = model.model_validate(
        {
            "document_number": "PO-1",
            "date": "2026-05-11",
            "line_items": [{"item_number": "10", "quantity": 2, "price": "12.50"}],
        }
    )

    assert set(model.model_fields) == {"document_number", "date", "line_items"}
    assert result.line_items[0].quantity == 2
    assert str(result.line_items[0].price) == "12.50"


def test_openai_strict_schema_keeps_child_model_constrained(
    parent_requirements: ExtractionRequirements,
    child_requirements: ExtractionRequirements,
):
    model = _create_parent_with_nested_list_model(
        parent_requirements=parent_requirements,
        child_requirements=child_requirements,
        child_container_name="line_items",
        child_container_description="Line item rows",
    )

    schema = _make_schema_strict(model.model_json_schema())
    child_ref = schema["properties"]["line_items"]["items"]["$ref"]
    child_schema = schema["$defs"][child_ref.rsplit("/", 1)[-1]]

    assert schema["additionalProperties"] is False
    assert child_schema["additionalProperties"] is False
    assert child_schema["required"] == ["item_number", "quantity", "price"]


def test_composite_post_process_applies_parent_and_child_requirements(
    parent_requirements: ExtractionRequirements,
    child_requirements: ExtractionRequirements,
):
    requirements = CompositeExtractionRequirements(
        parent_requirements=parent_requirements,
        child_container_name="line_items",
        child_requirements=child_requirements,
    )

    result = VisionExtractor._post_process(
        None,
        {
            "document_number": "PO-1",
            "date": "11/05/2026",
            "line_items": [{"item_number": "10", "quantity": 2, "price": "12.50"}],
        },
        requirements,
    )

    assert result == {
        "document_number": "PO-1",
        "date": "2026-05-11",
        "line_items": [{"item_number": "10", "quantity": 2, "price": "12.50"}],
    }


def test_blank_numeric_child_value_is_repaired_before_validation(
    parent_requirements: ExtractionRequirements,
    child_requirements: ExtractionRequirements,
):
    requirements = CompositeExtractionRequirements(
        parent_requirements=parent_requirements,
        child_container_name="line_items",
        child_requirements=child_requirements,
    )
    model = _create_parent_with_nested_list_model(
        parent_requirements=parent_requirements,
        child_requirements=child_requirements,
        child_container_name="line_items",
        child_container_description="Line item rows",
    )
    raw = {
        "document_number": "PO-1",
        "date": "2026-05-11",
        "line_items": [{"item_number": "10", "quantity": 2, "price": ""}],
    }

    repaired = VisionExtractor._normalize_numeric_placeholders(raw, requirements)
    validated = model.model_validate(repaired).model_dump()

    assert validated["line_items"][0]["price"] is None


def test_composite_requirements_and_schema_save_load_round_trip(
    tmp_path: Path,
    parent_requirements: ExtractionRequirements,
    child_requirements: ExtractionRequirements,
):
    requirements = CompositeExtractionRequirements(
        parent_requirements=parent_requirements,
        child_container_name="line_items",
        child_requirements=child_requirements,
    )
    model = _create_parent_with_nested_list_model(
        parent_requirements=parent_requirements,
        child_requirements=child_requirements,
        child_container_name="line_items",
        child_container_description="Line item rows",
    )

    schema_path = tmp_path / "schema.py"
    requirements_path = tmp_path / "requirements.json"
    _save_schema_to_python(model, schema_path)
    _save_requirements(requirements, model.__name__, requirements_path)

    model_name, loaded_requirements = _load_saved_requirements(requirements_path)
    loaded_model = _load_saved_schema(schema_path, model_name)

    assert isinstance(loaded_requirements, CompositeExtractionRequirements)
    loaded_model.model_validate(
        {
            "document_number": "PO-1",
            "date": "2026-05-11",
            "line_items": [{"item_number": "10", "quantity": 2, "price": "12.50"}],
        }
    )


def test_nested_item_requirements_reject_unconstrained_dict_rows():
    requirements = _requirements(
        "bad_child",
        [
            FieldSpec(
                field_name="line_items",
                field_type="list[dict]",
                description="Unconstrained nested objects",
            )
        ],
    )

    with pytest.raises(ValueError, match=r"list\[dict\]"):
        _ensure_no_list_dict_fields(requirements, context="Child requirements")


def test_repeated_item_prompt_forbids_list_dict_for_line_item_text():
    prompt = _build_parse_requirements_prompt(
        "For each line item, extract: item number, complete description, "
        "quantity, price, and material number.",
        parse_mode="repeated_item",
    )

    assert "ONE repeated child row/item/record" in prompt
    assert "Do not use field_type='list[dict]'" in prompt
    assert "return scalar fields like name, date, and status" in prompt


def test_vision_extractor_stores_use_azure_flag():
    extractor = VisionExtractor(api_config={"model": "test-model"}, use_azure=False)

    assert extractor.use_azure is False
