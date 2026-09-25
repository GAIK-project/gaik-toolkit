"""Vision Extractor router - single-pass PDF/image to structured data."""

from __future__ import annotations

import logging
import os
import tempfile
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

try:
    from utils import (
        MODEL,
        get_api_config,
        get_model_options,
        load_saved_requirements,
        load_saved_schema,
        schema_to_python_source,
        validate_file_size,
    )
except ImportError:
    from api.utils import (
        MODEL,
        get_api_config,
        get_model_options,
        load_saved_requirements,
        load_saved_schema,
        schema_to_python_source,
        validate_file_size,
    )

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

try:
    from utils.model_settings import get_request_api_config, provider_error_detail
except ImportError:
    from api.utils.model_settings import get_request_api_config, provider_error_detail

router = APIRouter()
logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".tiff",
    ".tif",
    ".bmp",
}

Provider = Literal["openai", "azure", "claude", "google"]
ReasoningEffort = Literal["low", "medium", "high"]

_OPENAI_MODELS = tuple(
    value.strip()
    for value in os.getenv(
        "DEMO_OPENAI_MODELS", "gpt-6-luna,gpt-6-sol,gpt-6-astra,gpt-5.6-terra"
    ).split(",")
    if value.strip()
)
PROVIDER_MODELS: dict[str, tuple[str, ...]] = {
    "openai": _OPENAI_MODELS,
    "azure": _OPENAI_MODELS,
    "claude": tuple(
        os.getenv("DEMO_CLAUDE_MODELS", "claude-sonnet-4.6,claude-sonnet-5").split(",")
    ),
    "google": tuple(os.getenv("DEMO_GOOGLE_MODELS", "gemini-3.1-flash-lite").split(",")),
}


EXAMPLE_SCHEMA_ID = "example"
EXAMPLE_SCHEMA_DIR = Path(__file__).parent.parent / "schemas" / "vision_extractor_example"
EXAMPLE_TASK_PATH = EXAMPLE_SCHEMA_DIR / "task.txt"
EXAMPLE_SCHEMA_PATH = EXAMPLE_SCHEMA_DIR / "schema.py"
EXAMPLE_REQUIREMENTS_PATH = EXAMPLE_SCHEMA_DIR / "requirements.json"

TEMPORARY_SCHEMA_LIMIT = 32


@dataclass(frozen=True)
class TemporarySchema:
    user_requirements: str
    schema: type[BaseModel]
    requirements: Any
    created_at: float


# Temporary custom schemas are intentionally process-local and never persisted.
_temporary_schemas: OrderedDict[str, TemporarySchema] = OrderedDict()


def _normalize_task_text(value: str) -> str:
    """Normalize transport-specific newlines before task identity checks."""
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


def _validate_suffix(filename: str | None) -> None:
    """Raise 400 if the filename is missing or has an unsupported suffix."""
    if not filename:
        raise HTTPException(status_code=400, detail="One of the files has no filename")
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type: {suffix}. "
                f"Supported: {', '.join(sorted(SUPPORTED_SUFFIXES))}"
            ),
        )


def _annotation_name(annotation: Any) -> str:
    return (
        str(annotation)
        .replace("typing.", "")
        .replace("<class '", "")
        .replace("'>", "")
        .replace("gaik.software_components.extractor.schema.", "")
    )


def _field_descriptors(schema: type[BaseModel]) -> list[dict]:
    """Describe the actual runtime model rather than intermediate LLM fields."""
    return [
        {
            "name": name,
            "type": _annotation_name(field.annotation),
            "description": field.description or "",
            "required": field.is_required(),
        }
        for name, field in schema.model_fields.items()
    ]


class GenerateSchemaRequest(BaseModel):
    user_requirements: str


class GenerateSchemaResponse(BaseModel):
    schema_code: str
    schema_name: str
    structure_type: str
    fields: list[dict]
    schema_id: str
    schema_source: Literal["example", "temporary"]
    user_requirements: str


class UsageMetadata(BaseModel):
    provider: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    thinking_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None


_USAGE_FIELDS = (
    "provider",
    "model",
    "input_tokens",
    "output_tokens",
    "thinking_tokens",
    "total_tokens",
    "cost_usd",
)


class VisionExtractResponse(BaseModel):
    data: dict
    verification: dict | None = None
    model: str
    documents_processed: int
    duration_s: float
    usage: UsageMetadata | None = None


def _usage_from(usage: Any) -> UsageMetadata | None:
    if usage is None:
        return None
    return UsageMetadata(**{name: getattr(usage, name, None) for name in _USAGE_FIELDS})


def _structure_type(requirements: Any) -> str:
    return getattr(requirements, "structure_type", "object")


def _schema_response(
    schema: type[BaseModel],
    requirements: Any,
    schema_id: str,
    schema_source: Literal["example", "temporary"],
    user_requirements: str,
) -> GenerateSchemaResponse:
    return GenerateSchemaResponse(
        schema_code=schema_to_python_source(schema),
        schema_name=schema.__name__,
        structure_type=_structure_type(requirements),
        fields=_field_descriptors(schema),
        schema_id=schema_id,
        schema_source=schema_source,
        user_requirements=user_requirements,
    )


@lru_cache(maxsize=1)
def _load_example_schema() -> tuple[str, type[BaseModel], Any]:
    """Load the immutable schema committed for the built-in PO/BOM example."""
    if not all(
        path.is_file()
        for path in (EXAMPLE_TASK_PATH, EXAMPLE_SCHEMA_PATH, EXAMPLE_REQUIREMENTS_PATH)
    ):
        raise RuntimeError("The built-in Vision Extractor example schema is incomplete")

    user_requirements = _normalize_task_text(EXAMPLE_TASK_PATH.read_text(encoding="utf-8"))
    loaded = load_saved_requirements(
        EXAMPLE_REQUIREMENTS_PATH,
        expected_user_requirements=user_requirements,
    )
    if loaded is None:
        raise RuntimeError("The built-in Vision Extractor example schema is stale")

    model_name, requirements = loaded
    schema = load_saved_schema(EXAMPLE_SCHEMA_PATH, model_name)
    return user_requirements, schema, requirements


def _remember_temporary_schema(
    user_requirements: str,
    schema: type[BaseModel],
    requirements: Any,
) -> str:
    schema_id = uuid.uuid4().hex
    _temporary_schemas[schema_id] = TemporarySchema(
        user_requirements=_normalize_task_text(user_requirements),
        schema=schema,
        requirements=requirements,
        created_at=time.monotonic(),
    )
    _temporary_schemas.move_to_end(schema_id)
    while len(_temporary_schemas) > TEMPORARY_SCHEMA_LIMIT:
        _temporary_schemas.popitem(last=False)
    return schema_id


def _resolve_requested_schema(schema_id: str, user_requirements: str):
    normalized_requirements = _normalize_task_text(user_requirements)
    if schema_id == EXAMPLE_SCHEMA_ID:
        example_task, schema, requirements = _load_example_schema()
        if normalized_requirements != example_task:
            raise HTTPException(
                status_code=409,
                detail=(
                    "The extraction task no longer matches the built-in example schema. "
                    "Generate and preview a new schema first."
                ),
            )
        return schema, requirements

    cached = _temporary_schemas.get(schema_id)
    if cached is None:
        raise HTTPException(
            status_code=410,
            detail="The temporary schema is unavailable. Generate and preview it again.",
        )
    if _normalize_task_text(cached.user_requirements) != normalized_requirements:
        raise HTTPException(
            status_code=409,
            detail="The extraction task changed. Generate and preview a new schema first.",
        )
    _temporary_schemas.move_to_end(schema_id)
    return cached.schema, cached.requirements


def _provider_settings(provider: Provider, model: str) -> tuple[str, bool, bool]:
    if model not in PROVIDER_MODELS[provider]:
        raise HTTPException(
            status_code=422,
            detail=f"Model '{model}' is not available for provider '{provider}'.",
        )

    if provider in {"openai", "azure"}:
        return "openai", bool(os.getenv("AZURE_API_KEY")), False
    if provider == "claude":
        use_foundry = bool(os.getenv("AZURE_API_KEY") and os.getenv("ANTHROPIC_FOUNDRY_RESOURCE"))
        return "claude", use_foundry, False

    use_vertex = bool(os.getenv("GOOGLE_PROJECT_ID"))
    return "google", False, use_vertex


@router.get("/example-schema", response_model=GenerateSchemaResponse)
async def get_example_schema():
    """Return the immutable schema bundled with the PO/BOM demo."""
    try:
        user_requirements, schema, requirements = _load_example_schema()
        return _schema_response(
            schema,
            requirements,
            EXAMPLE_SCHEMA_ID,
            "example",
            user_requirements,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=provider_error_detail(exc)) from exc


@router.post("/generate-schema", response_model=GenerateSchemaResponse)
async def generate_schema(request: GenerateSchemaRequest):
    """Generate an in-memory schema that will never replace the example schema."""
    user_requirements = _normalize_task_text(request.user_requirements)
    if not user_requirements:
        raise HTTPException(status_code=400, detail="No requirements provided")

    try:
        from gaik.software_components.extractor import SchemaGenerator

        config = get_api_config()
        generator = SchemaGenerator(config, model=config["model"], **get_model_options(config))
        schema = await run_in_threadpool(
            generator.generate_schema, user_requirements=user_requirements
        )
        requirements = generator.item_requirements
        schema_id = _remember_temporary_schema(user_requirements, schema, requirements)
        logger.info("Generated temporary vision-extractor schema %s", schema_id)
        return _schema_response(
            schema,
            requirements,
            schema_id,
            "temporary",
            user_requirements,
        )
    except HTTPException:
        raise
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=f"Extractor not installed: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=provider_error_detail(exc)) from exc


@router.post("", response_model=VisionExtractResponse)
async def extract_vision(
    files: list[UploadFile] = File(..., description="PDF/image files (multi-doc supported)"),
    user_requirements: str = Form(..., description="Natural-language extraction task"),
    schema_id: str = Form(..., description="Reviewed example or temporary schema ID"),
    model_provider: Provider = Form("openai"),
    model: str = Form(MODEL),
    reasoning_effort: ReasoningEffort = Form("medium"),
    merge_table: bool = Form(False),
    additional_instructions: str | None = Form(None),
    include_verification: bool = Form(False),
):
    """Extract with the exact pre-built schema selected in the demo UI."""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    normalized_user_requirements = _normalize_task_text(user_requirements)
    if not normalized_user_requirements:
        raise HTTPException(status_code=400, detail="No requirements provided")

    extraction_model, requirements = _resolve_requested_schema(
        schema_id, normalized_user_requirements
    )
    request_config = get_request_api_config()
    if request_config is not None:
        model = request_config["model"]
        lib_provider, use_azure, vertex_ai = "openai", request_config["provider"] == "azure", False
    else:
        lib_provider, use_azure, vertex_ai = _provider_settings(model_provider, model)

    for uploaded_file in files:
        _validate_suffix(uploaded_file.filename)

    temp_paths: list[Path] = []
    try:
        for uploaded_file in files:
            content = await validate_file_size(uploaded_file)
            suffix = Path(uploaded_file.filename or "").suffix.lower()
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(content)
                temp_paths.append(Path(tmp.name))

        try:
            from gaik.software_components.vision_extractor import VisionExtractor
        except ImportError as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    "VisionExtractor not available. "
                    "Update to gaik>=0.5.10 or install the toolkit from source. "
                    f"({exc})"
                ),
            ) from exc

        try:
            extractor = VisionExtractor(
                **({"api_config": request_config} if request_config is not None else {}),
                model_provider=lib_provider,
                model=model,
                reasoning_effort=(
                    get_model_options(request_config)["reasoning_effort"]
                    if request_config
                    else reasoning_effort
                ),
                merge_table=merge_table,
                use_azure=use_azure,
                vertex_ai=vertex_ai,
                additional_instructions=(additional_instructions or "").strip() or None,
                include_verification=include_verification,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Failed to initialize VisionExtractor for provider "
                    f"'{model_provider}': {provider_error_detail(exc)}. "
                    "Check that the relevant provider credentials are configured."
                ),
            ) from exc

        try:
            result = await run_in_threadpool(
                extractor.extract,
                file_paths=temp_paths,
                user_requirements=normalized_user_requirements,
                extraction_model=extraction_model,
                requirements=requirements,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"Vision extraction failed: {provider_error_detail(exc)}"
            ) from exc

        return VisionExtractResponse(
            data=result.data,
            verification=result.verification,
            model=result.model,
            documents_processed=result.documents_processed,
            duration_s=result.duration_s,
            usage=_usage_from(result.usage),
        )
    finally:
        for path in temp_paths:
            path.unlink(missing_ok=True)


@router.get("/models")
async def model_catalogue():
    return {
        "models": {name: list(values) for name, values in PROVIDER_MODELS.items()},
        "default": MODEL,
    }
