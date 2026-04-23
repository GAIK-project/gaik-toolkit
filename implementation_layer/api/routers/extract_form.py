"""Form-extraction endpoint for the GAIK Form Filler Chrome extension.

Accepts a list of FieldDescriptor-style field definitions + a free-form
source text, runs them through ``gaik.software_components.extractor.DataExtractor``,
and returns a mapping of field id → extracted value.

The field ids as they arrive from the browser (e.g. ASP.NET
``FieldInput:FieldRepeater:_ctl1:InputTextRow``) are not valid Python
identifiers, so we map them to ``field_0``, ``field_1`` … before building
the dynamic Pydantic model, and remap back to the original ids in the
response.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from gaik.software_components.extractor import (
    DataExtractor,
    ExtractionRequirements,
    FieldSpec,
    create_extraction_model,
)
from pydantic import BaseModel, Field

from implementation_layer.api.config import get_openai_config
from implementation_layer.api.dependencies import verify_api_key

router = APIRouter()


class IncomingField(BaseModel):
    """Mirror of ``FieldDescriptor`` from the TypeScript extension."""

    id: str
    label: str
    type: str = Field(description="FieldType: text, textarea, select, date, checkbox, radio, file")
    htmlType: str | None = None
    options: list[str] | None = None
    required: bool = False
    maxLength: int | None = None


class ExtractFormRequest(BaseModel):
    fields: list[IncomingField]
    sourceText: str = Field(..., description="Free-form text the AI should extract values from")


class ExtractFormResponse(BaseModel):
    values: dict[str, Any]


# FieldType (from extension) -> FieldSpec.field_type (AllowedTypes string).
TYPE_MAP: dict[str, str] = {
    "text": "str",
    "textarea": "str",
    "select": "str",  # enum comes from options
    "date": "date",
    "checkbox": "bool",
    "radio": "str",  # enum comes from options
    "file": "str",  # extension won't actually fill file inputs
}

# HTML input type overrides that should win when set.
HTML_INPUT_OVERRIDES: dict[str, str] = {
    "number": "float",
}


def _safe_name(index: int) -> str:
    return f"field_{index}"


def _build_requirements(
    fields: list[IncomingField],
) -> tuple[ExtractionRequirements, dict[str, str]]:
    """Build ``ExtractionRequirements`` and a safe-name → original-id map."""
    specs: list[FieldSpec] = []
    name_to_id: dict[str, str] = {}

    for i, f in enumerate(fields):
        safe = _safe_name(i)
        name_to_id[safe] = f.id

        field_type_key = TYPE_MAP.get(f.type, "str")
        if f.htmlType and f.htmlType in HTML_INPUT_OVERRIDES:
            field_type_key = HTML_INPUT_OVERRIDES[f.htmlType]

        enum_values = None
        if field_type_key == "str" and f.options and f.type in {"select", "radio"}:
            enum_values = [o for o in f.options if o]

        description_parts = [f.label or f.id]
        if f.htmlType:
            description_parts.append(f"(html type: {f.htmlType})")
        if f.required:
            description_parts.append("(required)")

        spec = FieldSpec(
            field_name=safe,
            field_type=field_type_key,  # type: ignore[arg-type]
            description=" ".join(description_parts),
            required=False,  # always False; let the LLM return null for unknown
            enum=enum_values,
        )
        specs.append(spec)

    reqs = ExtractionRequirements(use_case_name="form_filler", fields=specs)
    return reqs, name_to_id


def _user_prompt(fields: list[IncomingField], source_text: str) -> str:
    """Compose a form-filler-specific instruction for the LLM."""
    lines = [
        "Fill the following web form using the user's text as source material.",
        "Return one value per field. Use null when the text does not contain",
        "a value for a field. Do not invent data. Respect the schema types:",
        "strings for text/textarea/select/radio, numbers for number inputs,",
        "booleans for checkboxes, ISO dates (YYYY-MM-DD) for date inputs.",
        "When an enum (select/radio) is given, choose the closest matching option.",
        "",
        "User text:",
        source_text,
    ]
    return "\n".join(lines)


@router.post(
    "/",
    response_model=ExtractFormResponse,
    dependencies=[Depends(verify_api_key)],
    summary="Extract structured form values from free-form text",
    description=(
        "Takes a list of form field descriptors (as produced by the GAIK "
        "Form Filler Chrome extension's inspector) and a free-form text "
        "source, and returns extracted values keyed by original field id."
    ),
)
async def extract_form(payload: ExtractFormRequest):
    if not payload.fields:
        raise HTTPException(status_code=400, detail="fields must not be empty")
    if not payload.sourceText.strip():
        raise HTTPException(status_code=400, detail="sourceText must not be empty")

    try:
        requirements, name_to_id = _build_requirements(payload.fields)
    except Exception as exc:  # pragma: no cover — defensive
        raise HTTPException(status_code=400, detail=f"Invalid field spec: {exc}") from exc

    try:
        extraction_model = create_extraction_model(requirements)
        config = get_openai_config()
        extractor = DataExtractor(config=config)
        results = extractor.extract(
            extraction_model=extraction_model,
            requirements=requirements,
            user_requirements=_user_prompt(payload.fields, payload.sourceText),
            documents=[payload.sourceText],
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}") from exc

    if not results:
        return ExtractFormResponse(values={})

    first = results[0] if isinstance(results[0], dict) else {}
    remapped: dict[str, Any] = {}
    for safe_name, value in first.items():
        original = name_to_id.get(safe_name)
        if original is None:
            continue
        if value is None:
            continue
        remapped[original] = value
    return ExtractFormResponse(values=remapped)
