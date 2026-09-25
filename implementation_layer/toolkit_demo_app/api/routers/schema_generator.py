"""Schema Generator demo endpoints."""

from __future__ import annotations

import base64
import io
import json
import logging
import re
import time
import zipfile
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

try:
    from utils.model_settings import provider_error_detail
except ImportError:
    from api.utils.model_settings import provider_error_detail

try:
    from utils import (
        MODEL,
        SCHEMA_FORMAT_VERSION,
        get_api_config,
        get_model_options,
        schema_to_python_source,
    )
except ImportError:
    from api.utils import (
        MODEL,
        SCHEMA_FORMAT_VERSION,
        get_api_config,
        get_model_options,
        schema_to_python_source,
    )

try:
    from gaik.software_components.schema_generator import SchemaGenerator
except ImportError:  # Compatibility with gaik releases predating the alias package.
    from gaik.software_components.extractor import SchemaGenerator

router = APIRouter()
logger = logging.getLogger(__name__)


class GenerateSchemaRequest(BaseModel):
    user_requirements: str = Field(min_length=1, max_length=20_000)


class UsageMetadata(BaseModel):
    provider: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    thinking_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None


class GenerateSchemaResponse(BaseModel):
    schema_name: str
    structure_type: str
    field_count: int
    schema_code: str
    requirements_json: str
    archive_filename: str
    archive_base64: str
    model: str
    duration_s: float
    usage: UsageMetadata | None = None


_USAGE_FIELDS = (
    "provider",
    "model",
    "input_tokens",
    "output_tokens",
    "thinking_tokens",
    "total_tokens",
    "cost_usd",
)


def _requirements_type(requirements: Any) -> str:
    if getattr(requirements, "structure_type", None) == "parent_with_nested_list":
        return "parent_with_nested_list"
    return "extraction"


def _requirements_payload(
    requirements: Any,
    schema_name: str,
    user_requirements: str,
) -> dict[str, Any]:
    """Build the portable metadata consumed alongside a generated model."""
    return {
        "schema_format_version": SCHEMA_FORMAT_VERSION,
        "model_name": schema_name,
        "requirements_type": _requirements_type(requirements),
        "user_requirements": user_requirements,
        "requirements": requirements.model_dump(mode="json"),
    }


def _archive_artifacts(
    schema_name: str,
    schema_code: str,
    requirements_json: str,
) -> tuple[str, str]:
    """Return a safe filename and base64-encoded ZIP containing both artifacts."""
    folder_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", schema_name).strip("_") or "schema"
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, mode="w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(f"{folder_name}/schema.py", schema_code)
        bundle.writestr(f"{folder_name}/requirements.json", requirements_json)
    return f"{folder_name}.zip", base64.b64encode(archive.getvalue()).decode("ascii")


def _usage_from(usage: Any) -> UsageMetadata | None:
    if usage is None:
        return None
    return UsageMetadata(**{name: getattr(usage, name, None) for name in _USAGE_FIELDS})


@router.post("", response_model=GenerateSchemaResponse)
async def generate_schema(request: GenerateSchemaRequest) -> GenerateSchemaResponse:
    """Generate and package a Pydantic schema without persisting user input."""
    user_requirements = request.user_requirements.strip()
    if not user_requirements:
        raise HTTPException(status_code=400, detail="No extraction task provided")

    try:
        config = get_api_config()
        generator = SchemaGenerator(
            config=config,
            model=config.get("model", MODEL),
            **get_model_options(config, schema=True),
        )
        started_at = time.perf_counter()
        schema = await run_in_threadpool(generator.generate_schema, user_requirements)
        elapsed_s = time.perf_counter() - started_at
        requirements = generator.item_requirements

        schema_code = schema_to_python_source(schema)
        requirements_payload = _requirements_payload(
            requirements,
            schema.__name__,
            user_requirements,
        )
        requirements_json = json.dumps(requirements_payload, indent=2, ensure_ascii=False) + "\n"
        archive_filename, archive_base64 = _archive_artifacts(
            schema.__name__,
            schema_code,
            requirements_json,
        )
        schema_info = generator.get_schema_info()

        logger.info(
            "Generated temporary schema-generator artifacts for %s",
            schema.__name__,
        )
        return GenerateSchemaResponse(
            schema_name=schema.__name__,
            structure_type=generator.structure_analysis.structure_type,
            field_count=int(schema_info.get("field_count", 0)),
            schema_code=schema_code,
            requirements_json=requirements_json,
            archive_filename=archive_filename,
            archive_base64=archive_base64,
            model=generator.model,
            duration_s=getattr(generator, "last_duration_s", 0.0) or elapsed_s,
            usage=_usage_from(getattr(generator, "last_usage", None)),
        )
    except HTTPException:
        raise
    except ImportError as exc:
        raise HTTPException(
            status_code=500, detail=f"Schema Generator not installed: {exc}"
        ) from exc
    except Exception as exc:
        logger.exception("Schema generation failed")
        raise HTTPException(status_code=500, detail=provider_error_detail(exc)) from exc
