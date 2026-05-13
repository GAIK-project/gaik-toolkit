"""Vision Extractor router — single-pass PDF/image → structured data."""

import logging
import tempfile
from pathlib import Path
from typing import Any, Literal

try:
    from utils import (
        get_api_config,
        load_schema,
        schema_id_from_requirements,
        validate_file_size,
        wrap_schema_with_numeric_normalizers,
    )
except ImportError:
    from api.utils import (
        get_api_config,
        load_schema,
        schema_id_from_requirements,
        validate_file_size,
        wrap_schema_with_numeric_normalizers,
    )

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory cache for generated schemas (keyed by hash of user_requirements).
_schema_cache: dict[str, tuple[Any, Any]] = {}

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

_KNOWN_TYPES = {"decimal.Decimal", "int", "float", "bool"}


def _schema_key_for(user_requirements: str) -> str:
    """Schema key prefixed for the vision extractor (separate namespace)."""
    return f"vision_extractor_{schema_id_from_requirements(user_requirements)}"


def _field_descriptors(requirements) -> list[dict]:
    return [
        {
            "name": field.field_name,
            "type": field.field_type,
            "description": field.description,
            "required": field.required,
        }
        for field in requirements.fields
    ]


def _schema_code_from_requirements(schema: type[BaseModel], requirements) -> str:
    schema_lines = [
        "from pydantic import BaseModel, Field",
        "from typing import Literal",
        "import decimal",
        "",
        f"class {schema.__name__}(BaseModel):",
        f'    """Extraction model for {requirements.use_case_name}"""',
        "",
    ]

    for field in requirements.fields:
        field_type = field.field_type
        if field_type not in _KNOWN_TYPES and not field_type.startswith("Literal["):
            field_type = "str"

        if not field.required:
            field_type = f"{field_type} | None"

        default_value = "None" if not field.required else "..."
        desc = field.description.replace('"', '\\"')
        schema_lines.append(
            f'    {field.field_name}: {field_type} = Field({default_value}, description="{desc}")'
        )

    return "\n".join(schema_lines)


class GenerateSchemaRequest(BaseModel):
    user_requirements: str


class GenerateSchemaResponse(BaseModel):
    schema_code: str
    schema_name: str
    structure_type: str
    fields: list[dict]
    schema_id: str


class UsageMetadata(BaseModel):
    provider: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    thinking_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None


class VisionExtractResponse(BaseModel):
    data: dict
    verification: dict | None = None
    model: str
    documents_processed: int
    duration_s: float
    usage: UsageMetadata | None = None


@router.post("/generate-schema", response_model=GenerateSchemaResponse)
async def generate_schema(request: GenerateSchemaRequest):
    """Generate a Pydantic schema from natural language requirements.

    Same logic as the regular extractor's /generate-schema, but keyed under
    a separate `vision_extractor_*` namespace so vision and text extractors
    can persist different schemas for the same prompt.
    """
    if not request.user_requirements:
        raise HTTPException(status_code=400, detail="No requirements provided")

    try:
        from gaik.software_components.extractor import SchemaGenerator

        config = get_api_config()
        sid = schema_id_from_requirements(request.user_requirements)
        schema_key = _schema_key_for(request.user_requirements)

        loaded = load_schema(schema_key, request.user_requirements)
        if loaded is not None:
            schema, requirements = loaded
            logger.info("Loaded persisted vision-extractor schema for hash %s", sid)
        elif sid in _schema_cache:
            schema, requirements = _schema_cache[sid]
        else:
            generator = SchemaGenerator(config)
            schema = wrap_schema_with_numeric_normalizers(
                generator.generate_schema(user_requirements=request.user_requirements)
            )
            requirements = generator.item_requirements
            _schema_cache[sid] = (schema, requirements)
            logger.info("Generated temporary vision-extractor schema for hash %s", sid)

        return GenerateSchemaResponse(
            schema_code=_schema_code_from_requirements(schema, requirements),
            schema_name=schema.__name__,
            structure_type="object",
            fields=_field_descriptors(requirements),
            schema_id=sid,
        )

    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Extractor not installed: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("", response_model=VisionExtractResponse)
async def extract_vision(
    files: list[UploadFile] = File(..., description="PDF/image files (multi-doc supported)"),
    user_requirements: str = Form(..., description="Natural-language extraction task"),
    model_provider: Literal["openai", "claude", "google"] = Form("openai"),
    include_verification: bool = Form(False),
):
    """Extract structured data from PDFs/images in a single LLM call.

    Accepts multiple files in one request — the model sees them together,
    enabling cross-document reasoning (e.g. PO + multiple BOMs).
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    if not user_requirements:
        raise HTTPException(status_code=400, detail="No requirements provided")

    for f in files:
        if not f.filename:
            raise HTTPException(status_code=400, detail="One of the files has no filename")
        suffix = Path(f.filename).suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unsupported file type: {suffix}. "
                    f"Supported: {', '.join(sorted(SUPPORTED_SUFFIXES))}"
                ),
            )

    temp_paths: list[Path] = []
    try:
        for f in files:
            content = await validate_file_size(f)
            suffix = Path(f.filename or "").suffix.lower()
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(content)
                temp_paths.append(Path(tmp.name))

        try:
            from gaik.software_components.vision_extractor import VisionExtractor
        except ImportError as e:
            raise HTTPException(
                status_code=500,
                detail=(
                    "VisionExtractor not available. "
                    "Update to gaik>=0.5.10 or install the toolkit from source. "
                    f"({e})"
                ),
            ) from e

        try:
            extractor = VisionExtractor(
                model_provider=model_provider,
                include_verification=include_verification,
            )
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Failed to initialize VisionExtractor for provider "
                    f"'{model_provider}': {e}. "
                    "Check that the relevant API key environment variables are set."
                ),
            ) from e

        try:
            result = extractor.extract(
                file_paths=temp_paths,
                user_requirements=user_requirements,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Vision extraction failed: {e}") from e

        usage_meta: UsageMetadata | None = None
        if result.usage is not None:
            usage_meta = UsageMetadata(
                provider=getattr(result.usage, "provider", None),
                model=getattr(result.usage, "model", None),
                input_tokens=getattr(result.usage, "input_tokens", None),
                output_tokens=getattr(result.usage, "output_tokens", None),
                thinking_tokens=getattr(result.usage, "thinking_tokens", None),
                total_tokens=getattr(result.usage, "total_tokens", None),
                cost_usd=getattr(result.usage, "cost_usd", None),
            )

        return VisionExtractResponse(
            data=result.data,
            verification=result.verification,
            model=result.model,
            documents_processed=result.documents_processed,
            duration_s=result.duration_s,
            usage=usage_meta,
        )

    finally:
        for path in temp_paths:
            path.unlink(missing_ok=True)
