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


def _has_use_case_name(requirements) -> bool:
    """Distinguish ExtractionRequirements (has fields) from CompositeExtractionRequirements."""
    return hasattr(requirements, "fields") and hasattr(requirements, "use_case_name")


def _field_descriptors(requirements) -> list[dict]:
    """Flatten requirements (flat OR composite parent+child) into a display list."""
    if _has_use_case_name(requirements):
        return [
            {
                "name": field.field_name,
                "type": field.field_type,
                "description": field.description,
                "required": field.required,
            }
            for field in requirements.fields
        ]

    # CompositeExtractionRequirements: parent scalar fields + one repeated child collection.
    parent = requirements.parent_requirements
    child = requirements.child_requirements
    container = requirements.child_container_name
    descriptors = [
        {
            "name": field.field_name,
            "type": field.field_type,
            "description": field.description,
            "required": field.required,
        }
        for field in parent.fields
    ]
    descriptors.append(
        {
            "name": container,
            "type": f"list[{child.use_case_name}]",
            "description": f"Repeated {container} (one entry per row in the source)",
            "required": True,
        }
    )
    return descriptors


def _format_field_line(field) -> str:
    field_type = field.field_type
    if field_type not in _KNOWN_TYPES and not field_type.startswith("Literal["):
        field_type = "str"
    if not field.required:
        field_type = f"{field_type} | None"
    default_value = "None" if not field.required else "..."
    desc = field.description.replace('"', '\\"')
    return f'    {field.field_name}: {field_type} = Field({default_value}, description="{desc}")'


def _flat_schema_lines(schema_name: str, use_case_name: str, requirements) -> list[str]:
    lines = [
        f"class {schema_name}(BaseModel):",
        f'    """Extraction model for {use_case_name}"""',
        "",
    ]
    lines.extend(_format_field_line(field) for field in requirements.fields)
    return lines


def _schema_code_from_requirements(schema: type[BaseModel], requirements) -> str:
    """Render Pydantic schema source — supports both flat and composite layouts."""
    header = [
        "from pydantic import BaseModel, Field",
        "from typing import Literal",
        "import decimal",
        "",
    ]

    if _has_use_case_name(requirements):
        return "\n".join(
            header + _flat_schema_lines(schema.__name__, requirements.use_case_name, requirements)
        )

    # Composite: emit child model first, then parent model with the list[Child] container.
    parent = requirements.parent_requirements
    child = requirements.child_requirements
    container = requirements.child_container_name
    child_class = child.use_case_name

    body: list[str] = []
    body.extend(_flat_schema_lines(child_class, child.use_case_name, child))
    body.append("")
    body.append(f"class {schema.__name__}(BaseModel):")
    body.append(f'    """Extraction model for {parent.use_case_name}"""')
    body.append("")
    body.extend(_format_field_line(field) for field in parent.fields)
    body.append(
        f"    {container}: list[{child_class}] = Field("
        f'..., description="Repeated {container} (one entry per row in the source)")'
    )
    return "\n".join(header + body)


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


_USAGE_FIELDS = (
    "provider",
    "model",
    "input_tokens",
    "output_tokens",
    "thinking_tokens",
    "total_tokens",
    "cost_usd",
)


def _usage_from(usage: Any) -> "UsageMetadata | None":
    if usage is None:
        return None
    return UsageMetadata(**{name: getattr(usage, name, None) for name in _USAGE_FIELDS})


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

        structure_type = (
            "object"
            if _has_use_case_name(requirements)
            else getattr(requirements, "structure_type", "parent_with_nested_list")
        )
        return GenerateSchemaResponse(
            schema_code=_schema_code_from_requirements(schema, requirements),
            schema_name=schema.__name__,
            structure_type=structure_type,
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
    model_provider: Literal["azure", "claude", "google"] = Form("azure"),
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
        _validate_suffix(f.filename)

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

        # "azure" on demo-UI:n valinta Azure OpenAI:lle — muunnetaan kirjaston "openai"+use_azure=True-yhdistelmäksi
        lib_provider = "openai" if model_provider == "azure" else model_provider
        use_azure = model_provider == "azure"

        try:
            extractor = VisionExtractor(
                model_provider=lib_provider,
                use_azure=use_azure,
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
