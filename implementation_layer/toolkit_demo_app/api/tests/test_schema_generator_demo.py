"""Tests for the standalone Schema Generator website demo."""

from __future__ import annotations

import base64
import io
import json
import zipfile
from types import SimpleNamespace

import pytest
from api.routers import schema_generator as route
from fastapi import HTTPException
from gaik.software_components.extractor import ExtractionRequirements, FieldSpec
from gaik.software_components.extractor.schema import create_extraction_model


@pytest.mark.asyncio
async def test_generate_schema_returns_preview_and_downloadable_artifacts(monkeypatch) -> None:
    assert route.MODEL == "gpt-5.4"
    assert route.MODEL_OPTIONS == {
        "temperature": 0.0,
        "reasoning_effort": None,
    }

    requirements = ExtractionRequirements(
        use_case_name="invoice",
        fields=[
            FieldSpec(
                field_name="invoice_number",
                field_type="str",
                description="Invoice number",
            )
        ],
    )
    schema = create_extraction_model(requirements)
    captured: dict = {}

    class FakeSchemaGenerator:
        def __init__(self, **kwargs):
            captured["constructor"] = kwargs
            self.item_requirements = requirements
            self.structure_analysis = SimpleNamespace(structure_type="flat")
            self.last_usage = SimpleNamespace(
                provider="openai",
                model=route.MODEL,
                input_tokens=100,
                output_tokens=50,
                thinking_tokens=0,
                total_tokens=150,
                cost_usd=0.01,
            )
            self.last_duration_s = 0.25
            self.model = route.MODEL

        def generate_schema(self, user_requirements):
            captured["task"] = user_requirements
            return schema

        def get_schema_info(self):
            return {"field_count": 1}

    monkeypatch.setattr(route, "SchemaGenerator", FakeSchemaGenerator)
    monkeypatch.setattr(route, "get_api_config", lambda: {"api_key": "test"})

    response = await route.generate_schema(
        route.GenerateSchemaRequest(user_requirements="  Extract invoice number.  ")
    )

    assert captured["constructor"] == {
        "config": {"api_key": "test"},
        "model": route.MODEL,
        **route.MODEL_OPTIONS,
    }
    assert captured["task"] == "Extract invoice number."
    assert response.structure_type == "flat"
    assert response.field_count == 1
    assert f"class {schema.__name__}(BaseModel):" in response.schema_code

    requirements_payload = json.loads(response.requirements_json)
    assert requirements_payload["schema_format_version"] == route.SCHEMA_FORMAT_VERSION
    assert requirements_payload["model_name"] == schema.__name__
    assert requirements_payload["requirements_type"] == "extraction"
    assert requirements_payload["user_requirements"] == "Extract invoice number."
    assert requirements_payload["requirements"] == requirements.model_dump(mode="json")

    with zipfile.ZipFile(io.BytesIO(base64.b64decode(response.archive_base64))) as bundle:
        folder = schema.__name__
        assert set(bundle.namelist()) == {
            f"{folder}/schema.py",
            f"{folder}/requirements.json",
        }
        assert bundle.read(f"{folder}/schema.py").decode() == response.schema_code
        assert bundle.read(f"{folder}/requirements.json").decode() == response.requirements_json


@pytest.mark.asyncio
async def test_generate_schema_rejects_whitespace_only_task() -> None:
    with pytest.raises(HTTPException, match="No extraction task provided"):
        await route.generate_schema(route.GenerateSchemaRequest(user_requirements="   "))
