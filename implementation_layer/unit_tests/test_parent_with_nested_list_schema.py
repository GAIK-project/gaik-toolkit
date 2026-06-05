"""Tests for parent object + repeated child collection schema support."""

from __future__ import annotations

from pathlib import Path

import pytest

from gaik.software_components.extractor import (
    ChildRequirements,
    CompositeExtractionRequirements,
    ExtractionRequirements,
    FieldSpec,
)
from gaik.software_components.extractor.schema import (
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


@pytest.fixture()
def child_spec(child_requirements: ExtractionRequirements) -> ChildRequirements:
    return ChildRequirements(
        container_name="line_items",
        container_description="Line item rows",
        requirements=child_requirements,
    )


def test_combined_model_has_parent_fields_and_typed_child_rows(
    parent_requirements: ExtractionRequirements,
    child_spec: ChildRequirements,
):
    model = _create_parent_with_nested_list_model(
        parent_requirements=parent_requirements,
        children=[child_spec],
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


def test_combined_model_with_multiple_children(
    parent_requirements: ExtractionRequirements,
    child_requirements: ExtractionRequirements,
):
    second_child = ChildRequirements(
        container_name="notes",
        container_description="Notes",
        requirements=_requirements(
            "note",
            [
                FieldSpec(field_name="note_text", field_type="str", description="Note text"),
            ],
        ),
    )
    model = _create_parent_with_nested_list_model(
        parent_requirements=parent_requirements,
        children=[
            ChildRequirements(
                container_name="line_items",
                container_description="Line item rows",
                requirements=child_requirements,
            ),
            second_child,
        ],
    )

    assert "line_items" in model.model_fields
    assert "notes" in model.model_fields
    assert "document_number" in model.model_fields


def test_openai_strict_schema_keeps_child_model_constrained(
    parent_requirements: ExtractionRequirements,
    child_spec: ChildRequirements,
):
    model = _create_parent_with_nested_list_model(
        parent_requirements=parent_requirements,
        children=[child_spec],
    )

    schema = _make_schema_strict(model.model_json_schema())
    child_ref = schema["properties"]["line_items"]["items"]["$ref"]
    child_schema = schema["$defs"][child_ref.rsplit("/", 1)[-1]]

    assert schema["additionalProperties"] is False
    assert child_schema["additionalProperties"] is False
    assert child_schema["required"] == ["item_number", "quantity", "price"]


def test_composite_post_process_applies_parent_and_child_requirements(
    parent_requirements: ExtractionRequirements,
    child_spec: ChildRequirements,
):
    requirements = CompositeExtractionRequirements(
        parent_requirements=parent_requirements,
        children=[child_spec],
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


def test_composite_post_process_handles_multiple_children(
    parent_requirements: ExtractionRequirements,
    child_requirements: ExtractionRequirements,
):
    note_req = _requirements(
        "note",
        [
            FieldSpec(field_name="note_text", field_type="str", description="Note text"),
        ],
    )
    requirements = CompositeExtractionRequirements(
        parent_requirements=parent_requirements,
        children=[
            ChildRequirements(
                container_name="line_items",
                container_description="Lines",
                requirements=child_requirements,
            ),
            ChildRequirements(
                container_name="notes",
                container_description="Notes",
                requirements=note_req,
            ),
        ],
    )

    result = VisionExtractor._post_process(
        None,
        {
            "document_number": "PO-1",
            "date": "2026-05-11",
            "line_items": [{"item_number": "10", "quantity": 2, "price": "12.50"}],
            "notes": [{"note_text": "Handle with care"}],
        },
        requirements,
    )

    assert "line_items" in result
    assert "notes" in result
    assert result["notes"][0]["note_text"] == "Handle with care"
    assert result["document_number"] == "PO-1"


def test_blank_numeric_child_value_is_repaired_before_validation(
    parent_requirements: ExtractionRequirements,
    child_spec: ChildRequirements,
):
    requirements = CompositeExtractionRequirements(
        parent_requirements=parent_requirements,
        children=[child_spec],
    )
    model = _create_parent_with_nested_list_model(
        parent_requirements=parent_requirements,
        children=[child_spec],
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
    child_spec: ChildRequirements,
):
    requirements = CompositeExtractionRequirements(
        parent_requirements=parent_requirements,
        children=[child_spec],
    )
    model = _create_parent_with_nested_list_model(
        parent_requirements=parent_requirements,
        children=[child_spec],
    )

    schema_path = tmp_path / "schema.py"
    requirements_path = tmp_path / "requirements.json"
    _save_schema_to_python(model, schema_path)
    _save_requirements(requirements, model.__name__, requirements_path)

    model_name, loaded_requirements = _load_saved_requirements(requirements_path)
    loaded_model = _load_saved_schema(schema_path, model_name)

    assert isinstance(loaded_requirements, CompositeExtractionRequirements)
    assert len(loaded_requirements.children) == 1
    assert loaded_requirements.children[0].container_name == "line_items"
    loaded_model.model_validate(
        {
            "document_number": "PO-1",
            "date": "2026-05-11",
            "line_items": [{"item_number": "10", "quantity": 2, "price": "12.50"}],
        }
    )


def test_backward_compat_shims_return_first_child(
    parent_requirements: ExtractionRequirements,
    child_spec: ChildRequirements,
):
    requirements = CompositeExtractionRequirements(
        parent_requirements=parent_requirements,
        children=[child_spec],
    )

    assert requirements.child_container_name == "line_items"
    assert requirements.child_requirements is child_spec.requirements


def test_load_old_format_requirements_json(
    tmp_path: Path,
    parent_requirements: ExtractionRequirements,
    child_requirements: ExtractionRequirements,
):
    """Old requirements.json with child_container_name / child_requirements is migrated."""
    import json

    old_payload = {
        "model_name": "OldModel_Extraction",
        "requirements_type": "parent_with_nested_list",
        "requirements": {
            "structure_type": "parent_with_nested_list",
            "parent_requirements": parent_requirements.model_dump(),
            "child_container_name": "line_items",
            "child_requirements": child_requirements.model_dump(),
        },
    }
    req_path = tmp_path / "requirements.json"
    req_path.write_text(json.dumps(old_payload), encoding="utf-8")

    model_name, loaded = _load_saved_requirements(req_path)
    assert model_name == "OldModel_Extraction"
    assert isinstance(loaded, CompositeExtractionRequirements)
    assert len(loaded.children) == 1
    assert loaded.children[0].container_name == "line_items"


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
