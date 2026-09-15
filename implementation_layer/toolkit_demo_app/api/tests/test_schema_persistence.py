"""Regression tests for the demo API's shared schema persistence."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from api.utils.schema import (
    SCHEMA_FORMAT_VERSION,
    load_saved_requirements,
    load_saved_schema,
    save_requirements,
    save_schema_to_python,
    schema_to_python_source,
    wrap_schema_with_numeric_normalizers,
)
from gaik.software_components.extractor import ExtractionRequirements, FieldSpec
from gaik.software_components.extractor.schema import create_extraction_model


def _decimal_model():
    requirements = ExtractionRequirements(
        use_case_name="decimal_safety",
        fields=[
            FieldSpec(
                field_name="price",
                field_type="decimal",
                description="Price",
            )
        ],
    )
    return create_extraction_model(requirements), requirements


def test_website_wrapper_preserves_core_decimal_policy():
    model, _ = _decimal_model()
    wrapped = wrap_schema_with_numeric_normalizers(model)

    assert model.model_validate({"price": "1 234,56 EUR"}).price is None
    assert wrapped.model_validate({"price": "1 234,56 EUR"}).price is None
    assert wrapped.model_validate({"price": "EUR 1,234.56"}).price == Decimal("1234.56")


def test_decimal_schema_round_trip_is_provider_safe(tmp_path: Path):
    model, requirements = _decimal_model()
    schema_path = tmp_path / "schema.py"
    requirements_path = tmp_path / "requirements.json"

    save_schema_to_python(model, schema_path)
    save_requirements(requirements, model.__name__, requirements_path)
    loaded_requirements = load_saved_requirements(requirements_path)
    assert loaded_requirements is not None
    model_name, _ = loaded_requirements
    loaded = load_saved_schema(schema_path, model_name)

    assert '"pattern"' not in json.dumps(loaded.model_json_schema())
    assert loaded.model_validate({"price": "12.40 EUR"}).price == Decimal("12.40")
    assert loaded.model_validate({"price": "1 234,56 EUR"}).price is None


def test_nullable_enum_schema_imports_required_typing_names(tmp_path: Path):
    requirements = ExtractionRequirements(
        use_case_name="nullable_enum",
        fields=[
            FieldSpec(
                field_name="status",
                field_type="str",
                description="Status",
                nullable=True,
                enum=["open", "closed"],
            )
        ],
    )
    model = create_extraction_model(requirements)
    schema_path = tmp_path / "schema.py"

    source = schema_to_python_source(model)
    save_schema_to_python(model, schema_path)
    loaded = load_saved_schema(schema_path, model.__name__)

    assert "from typing import Literal, Optional" in source
    assert loaded.model_validate({"status": None}).status is None
    assert loaded.model_validate({"status": "open"}).status == "open"


def test_legacy_requirements_invalidate_cache(tmp_path: Path):
    _, requirements = _decimal_model()
    path = tmp_path / "requirements.json"
    path.write_text(
        json.dumps(
            {
                "model_name": "Legacy",
                "requirements": requirements.model_dump(),
            }
        ),
        encoding="utf-8",
    )

    assert load_saved_requirements(path) is None


@pytest.mark.parametrize(
    ("schema_file", "requirements_file"),
    [
        (
            "document_structured_business_default_schema.py",
            "document_structured_business_default_requirements.json",
        ),
        (
            "extractor_e1f98f627acc8960_schema.py",
            "extractor_e1f98f627acc8960_requirements.json",
        ),
    ],
)
def test_committed_decimal_schemas_are_provider_safe(schema_file: str, requirements_file: str):
    schema_dir = Path(__file__).parents[1] / "schemas"
    loaded_requirements = load_saved_requirements(schema_dir / requirements_file)
    assert loaded_requirements is not None
    model_name, _ = loaded_requirements
    model = load_saved_schema(schema_dir / schema_file, model_name)

    assert '"pattern"' not in json.dumps(model.model_json_schema())


def test_saved_requirements_include_current_format_version(tmp_path: Path):
    model, requirements = _decimal_model()
    path = tmp_path / "requirements.json"

    save_requirements(requirements, model.__name__, path)

    assert json.loads(path.read_text(encoding="utf-8"))["schema_format_version"] == (
        SCHEMA_FORMAT_VERSION
    )
