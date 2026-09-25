"""Tests for the website's true-form VisionExtractor workflow."""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from api.routers import vision_extractor as route
from fastapi import HTTPException, UploadFile
from gaik.software_components.extractor import ExtractionRequirements, FieldSpec
from gaik.software_components.extractor.schema import create_extraction_model


def test_committed_example_schema_loads_and_renders_exact_runtime_types() -> None:
    task, schema, requirements = route._load_example_schema()
    response = route._schema_response(
        schema,
        requirements,
        route.EXAMPLE_SCHEMA_ID,
        "example",
        task,
    )

    assert response.schema_source == "example"
    assert response.user_requirements == task
    assert "quantity: int | None = Field(default=None" in response.schema_code
    assert "list[purchase_order_item_Extraction]" in response.schema_code
    assert "purchase_order_header_extraction_Extraction.purchase_order_item" not in (
        response.schema_code
    )
    compile(response.schema_code, "<vision-example-schema>", "exec")

    delivery_date = requirements.children[0].requirements.fields[3]
    assert delivery_date.field_name == "delivery_date"
    assert delivery_date.format == "%d/%m/%Y"


def test_temporary_schema_is_process_local_and_bound_to_its_task() -> None:
    requirements = ExtractionRequirements(
        use_case_name="temporary_demo",
        fields=[FieldSpec(field_name="name", field_type="str", description="Name")],
    )
    schema = create_extraction_model(requirements)
    before = set(route.EXAMPLE_SCHEMA_DIR.iterdir())

    schema_id = route._remember_temporary_schema("Extract name", schema, requirements)

    assert route._resolve_requested_schema(schema_id, "Extract name") == (schema, requirements)
    assert set(route.EXAMPLE_SCHEMA_DIR.iterdir()) == before
    with pytest.raises(HTTPException, match="task changed"):
        route._resolve_requested_schema(schema_id, "Extract a different field")


def test_temporary_schema_task_matching_normalizes_multipart_newlines() -> None:
    requirements = ExtractionRequirements(
        use_case_name="multiline_demo",
        fields=[FieldSpec(field_name="name", field_type="str", description="Name")],
    )
    schema = create_extraction_model(requirements)
    schema_id = route._remember_temporary_schema(
        "Extract fields:\n- name\n- address",
        schema,
        requirements,
    )

    assert route._resolve_requested_schema(
        schema_id,
        "Extract fields:\r\n- name\r\n- address",
    ) == (schema, requirements)


def test_provider_model_allowlists(monkeypatch) -> None:
    assert route.PROVIDER_MODELS == {
        "openai": (
            "gpt-6-luna",
            "gpt-6-sol",
            "gpt-6-astra",
            "gpt-5.6-terra",
        ),
        "azure": (
            "gpt-6-luna",
            "gpt-6-sol",
            "gpt-6-astra",
            "gpt-5.6-terra",
        ),
        "claude": ("claude-sonnet-4.6", "claude-sonnet-5"),
        "google": ("gemini-3.1-flash-lite",),
    }

    monkeypatch.setenv("AZURE_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_RESOURCE", "test-resource")
    assert route._provider_settings("openai", "gpt-6-sol") == ("openai", True, False)
    assert route._provider_settings("claude", "claude-sonnet-5") == (
        "claude",
        True,
        False,
    )

    with pytest.raises(HTTPException, match="not available"):
        route._provider_settings("google", "gpt-6-sol")


@pytest.mark.asyncio
async def test_extract_passes_reviewed_schema_and_all_options(monkeypatch) -> None:
    captured: dict = {}

    class FakeVisionExtractor:
        def __init__(self, **kwargs):
            captured["constructor"] = kwargs

        def extract(self, **kwargs):
            captured["extract"] = kwargs
            return SimpleNamespace(
                data={"ok": True},
                verification=None,
                model="claude-sonnet-5",
                documents_processed=1,
                duration_s=0.1,
                usage=None,
            )

    import gaik.software_components.vision_extractor as component

    monkeypatch.setattr(component, "VisionExtractor", FakeVisionExtractor)
    monkeypatch.setenv("AZURE_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_RESOURCE", "test-resource")

    task, expected_schema, expected_requirements = route._load_example_schema()
    upload = UploadFile(filename="sample.pdf", file=io.BytesIO(b"%PDF-test"))

    response = await route.extract_vision(
        files=[upload],
        user_requirements=task,
        schema_id=route.EXAMPLE_SCHEMA_ID,
        model_provider="claude",
        model="claude-sonnet-5",
        reasoning_effort="high",
        merge_table=True,
        additional_instructions="Prefer the final table.",
        include_verification=True,
    )

    assert response.data == {"ok": True}
    assert captured["constructor"] == {
        "model_provider": "claude",
        "model": "claude-sonnet-5",
        "reasoning_effort": "high",
        "merge_table": True,
        "use_azure": True,
        "vertex_ai": False,
        "additional_instructions": "Prefer the final table.",
        "include_verification": True,
    }
    assert captured["extract"]["extraction_model"] is expected_schema
    assert captured["extract"]["requirements"] is expected_requirements
    assert "schema_dir" not in captured["extract"]
    assert all(not Path(path).exists() for path in captured["extract"]["file_paths"])
