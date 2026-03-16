"""Extractor router - Data extraction endpoints"""

try:
    from utils import get_api_config
except ImportError:
    from api.utils import get_api_config

import hashlib
import importlib.util
import io
import json
import logging
from contextlib import redirect_stdout
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, get_args, get_origin

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

router = APIRouter()
logger = logging.getLogger(__name__)
SCHEMA_DIR = Path(__file__).parent.parent / "schemas"
SCHEMA_DIR.mkdir(exist_ok=True)

# In-memory cache for temporary/generated schemas.
# Key: hash of user_requirements, Value: (schema_class, item_requirements)
_schema_cache: dict[str, tuple[Any, Any]] = {}


def _annotation_contains(annotation, target_type: type) -> bool:
    if annotation is target_type:
        return True

    origin = get_origin(annotation)
    if origin is None:
        return False

    return any(
        arg is not type(None) and _annotation_contains(arg, target_type)
        for arg in get_args(annotation)
    )


def _clean_numeric_string(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return cleaned

    negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        negative = True
        cleaned = cleaned[1:-1].strip()

    cleaned = cleaned.replace("$", "").replace("EUR", "").replace("eur", "")
    cleaned = cleaned.replace(" ", "").replace(",", "")
    cleaned = cleaned.replace("%", "")

    if negative and cleaned and not cleaned.startswith("-"):
        cleaned = f"-{cleaned}"
    return cleaned


def _normalize_decimal_value(value):
    if value is None or isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = _clean_numeric_string(value)
        if cleaned in {"", "-", "N/A", "n/a", "none", "null"}:
            return None
        try:
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return value
    return value


def _normalize_float_value(value):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    if isinstance(value, str):
        cleaned = _clean_numeric_string(value)
        if cleaned in {"", "-", "N/A", "n/a", "none", "null"}:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return value
    return value


def _normalize_int_value(value):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, (float, Decimal)):
        return int(value)
    if isinstance(value, str):
        cleaned = _clean_numeric_string(value)
        if cleaned in {"", "-", "N/A", "n/a", "none", "null"}:
            return None
        try:
            return int(float(cleaned))
        except ValueError:
            return value
    return value


def _wrap_schema_with_numeric_normalizers(schema: type[BaseModel]) -> type[BaseModel]:
    decimal_fields = [
        name for name, field in schema.model_fields.items()
        if _annotation_contains(field.annotation, Decimal)
    ]
    float_fields = [
        name for name, field in schema.model_fields.items()
        if _annotation_contains(field.annotation, float)
    ]
    int_fields = [
        name for name, field in schema.model_fields.items()
        if _annotation_contains(field.annotation, int)
    ]

    if not any((decimal_fields, float_fields, int_fields)):
        return schema

    namespace: dict[str, object] = {}

    if decimal_fields:
        @field_validator(*decimal_fields, mode="before", check_fields=False)
        @classmethod
        def _normalize_decimal_fields(cls, value):
            return _normalize_decimal_value(value)

        namespace["_normalize_decimal_fields"] = _normalize_decimal_fields

    if float_fields:
        @field_validator(*float_fields, mode="before", check_fields=False)
        @classmethod
        def _normalize_float_fields(cls, value):
            return _normalize_float_value(value)

        namespace["_normalize_float_fields"] = _normalize_float_fields

    if int_fields:
        @field_validator(*int_fields, mode="before", check_fields=False)
        @classmethod
        def _normalize_int_fields(cls, value):
            return _normalize_int_value(value)

        namespace["_normalize_int_fields"] = _normalize_int_fields

    wrapped_schema = type(f"{schema.__name__}Normalized", (schema,), namespace)
    wrapped_schema.model_rebuild(force=True)
    return wrapped_schema


def _schema_id(user_requirements: str) -> str:
    return hashlib.sha256(user_requirements.encode()).hexdigest()[:16]


def _schema_paths(schema_id: str) -> tuple[Path, Path]:
    return SCHEMA_DIR / f"extractor_{schema_id}_schema.py", SCHEMA_DIR / f"extractor_{schema_id}_requirements.json"


def _clean_schema_dump(raw_dump: str) -> str:
    lines = raw_dump.splitlines()
    start_idx = 0
    for i, line in enumerate(lines):
        if line.startswith("class "):
            start_idx = i
            break
    body = lines[start_idx:]
    while body and (set(body[-1].strip()) == {"="} or not body[-1].strip()):
        body.pop()
    return "\n".join(body).strip()


def _sanitize_schema_code(schema_code: str) -> str:
    return schema_code.replace("gaik.software_components.extractor.schema.", "")


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
        if field_type == "decimal.Decimal":
            field_type = "decimal.Decimal"
        elif field_type == "int":
            field_type = "int"
        elif field_type == "float":
            field_type = "float"
        elif field_type == "bool":
            field_type = "bool"
        elif field_type == "date":
            field_type = "str"
        elif field_type.startswith("Literal["):
            field_type = field_type
        else:
            field_type = "str"

        if not field.required:
            field_type = f"{field_type} | None"

        default_value = "None" if not field.required else "..."
        desc = field.description.replace('"', '\"')
        schema_lines.append(
            f"    {field.field_name}: {field_type} = "
            f'Field({default_value}, description="{desc}")'
        )

    return "\n".join(schema_lines)


def _save_persisted_schema(schema: type[BaseModel], requirements, user_requirements: str) -> None:
    from gaik.software_components.extractor.schema import print_pydantic_schema

    schema_id = _schema_id(user_requirements)
    schema_path, req_path = _schema_paths(schema_id)

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        print_pydantic_schema(schema, title="Saved Schema")

    schema_code = _sanitize_schema_code(_clean_schema_dump(buffer.getvalue()))
    template = f'''"""
Auto-generated schema module (do not edit manually).
"""

import decimal
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, ConfigDict

{schema_code}
'''
    schema_path.write_text(template, encoding="utf-8")

    payload = {
        "model_name": schema.__name__,
        "requirements": requirements.model_dump(),
        "user_requirements": user_requirements,
    }
    req_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_persisted_schema(user_requirements: str):
    from gaik.software_components.extractor import ExtractionRequirements

    schema_id = _schema_id(user_requirements)
    schema_path, req_path = _schema_paths(schema_id)
    if not (schema_path.exists() and req_path.exists()):
        return None

    data = json.loads(req_path.read_text(encoding="utf-8"))
    if data.get("user_requirements") != user_requirements:
        return None

    source = schema_path.read_text(encoding="utf-8")
    sanitized = _sanitize_schema_code(source)
    if sanitized != source:
        schema_path.write_text(sanitized, encoding="utf-8")
        logger.info("Sanitized cached schema module: %s", schema_path)

    model_name = data["model_name"]
    requirements = ExtractionRequirements(**data["requirements"])
    spec = importlib.util.spec_from_file_location(model_name, schema_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader is not None
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    schema = getattr(module, model_name)
    return _wrap_schema_with_numeric_normalizers(schema), requirements


class ExtractRequest(BaseModel):
    documents: list[str]
    user_requirements: str
    fields: dict[str, str] | None = None


class ExtractResponse(BaseModel):
    results: list[dict]
    document_count: int


class GenerateSchemaRequest(BaseModel):
    user_requirements: str


class GenerateSchemaResponse(BaseModel):
    schema_code: str
    schema_name: str
    structure_type: str
    fields: list[dict]
    schema_id: str


@router.post("/generate-schema", response_model=GenerateSchemaResponse)
async def generate_schema(request: GenerateSchemaRequest):
    """
    Generate a Pydantic schema from natural language requirements.

    This path is intentionally in-memory only. It is used for explicit schema
    regeneration/testing and should not overwrite or persist the baseline schema.
    """
    if not request.user_requirements:
        raise HTTPException(status_code=400, detail="No requirements provided")

    try:
        from gaik.software_components.extractor import SchemaGenerator

        config = get_api_config()
        schema_id = _schema_id(request.user_requirements)

        loaded = _load_persisted_schema(request.user_requirements)
        if loaded is not None:
            schema, requirements = loaded
            logger.info("Loaded persisted extractor schema for requirements hash %s", schema_id)
        elif schema_id in _schema_cache:
            schema, requirements = _schema_cache[schema_id]
        else:
            generator = SchemaGenerator(config)
            schema = _wrap_schema_with_numeric_normalizers(
                generator.generate_schema(user_requirements=request.user_requirements)
            )
            requirements = generator.item_requirements
            _schema_cache[schema_id] = (schema, requirements)
            logger.info("Generated temporary extractor schema for requirements hash %s", schema_id)

        return GenerateSchemaResponse(
            schema_code=_schema_code_from_requirements(schema, requirements),
            schema_name=schema.__name__,
            structure_type="object",
            fields=_field_descriptors(requirements),
            schema_id=schema_id,
        )

    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Extractor not installed: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


class PlainLanguageExtractRequest(BaseModel):
    documents: list[str]
    user_requirements: str
    schema_id: str | None = None


@router.post("/plain-language", response_model=ExtractResponse)
async def extract_data_plain_language(request: PlainLanguageExtractRequest):
    """
    Extract structured data from documents using plain language requirements.

    Behavior:
    - if a schema_id is provided and cached in memory, use that temporary schema
    - else, try loading a persisted schema for the exact requirements
    - else, create and persist the first baseline schema for those requirements
    """
    if not request.documents:
        raise HTTPException(status_code=400, detail="No documents provided")

    if not request.user_requirements:
        raise HTTPException(status_code=400, detail="No requirements provided")

    try:
        from gaik.software_components.extractor import DataExtractor, SchemaGenerator

        config = get_api_config()

        if request.schema_id and request.schema_id in _schema_cache:
            schema, item_requirements = _schema_cache[request.schema_id]
        else:
            loaded = _load_persisted_schema(request.user_requirements)
            if loaded is not None:
                schema, item_requirements = loaded
            else:
                generator = SchemaGenerator(config)
                schema = _wrap_schema_with_numeric_normalizers(
                    generator.generate_schema(user_requirements=request.user_requirements)
                )
                item_requirements = generator.item_requirements
                _save_persisted_schema(schema, item_requirements, request.user_requirements)
                logger.info(
                    "Saved persisted extractor schema for requirements hash %s",
                    _schema_id(request.user_requirements),
                )

        extractor = DataExtractor(config)
        results = extractor.extract(
            extraction_model=schema,
            requirements=item_requirements,
            user_requirements=request.user_requirements,
            documents=request.documents,
        )

        return ExtractResponse(
            results=results,
            document_count=len(request.documents),
        )

    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Extractor not installed: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("", response_model=ExtractResponse)
async def extract_data(request: ExtractRequest):
    """
    Extract structured data from documents using natural language requirements.

    - **documents**: List of document texts to extract from
    - **user_requirements**: Natural language description of what to extract
    - **fields**: Optional field definitions (name -> description)
    """
    if not request.documents:
        raise HTTPException(status_code=400, detail="No documents provided")

    if not request.user_requirements:
        raise HTTPException(status_code=400, detail="No requirements provided")

    try:
        from gaik.software_components.extractor import (
            DataExtractor,
            ExtractionRequirements,
            FieldSpec,
        )
        from pydantic import create_model

        config = get_api_config()
        extractor = DataExtractor(config)

        if request.fields:
            field_definitions = {name: (str | None, None) for name in request.fields.keys()}
            ExtractionModel = create_model("DynamicExtraction", **field_definitions)

            field_specs = [
                FieldSpec(
                    field_name=name,
                    field_type="str",
                    description=desc,
                    required=False,
                )
                for name, desc in request.fields.items()
            ]
            requirements = ExtractionRequirements(
                use_case_name="DynamicExtraction",
                fields=field_specs,
            )
        else:
            ExtractionModel = create_model(
                "GenericExtraction",
                extracted_data=(str | None, None),
            )
            requirements = ExtractionRequirements(
                use_case_name="GenericExtraction",
                fields=[
                    FieldSpec(
                        field_name="extracted_data",
                        field_type="str",
                        description=request.user_requirements,
                        required=False,
                    )
                ],
            )

        results = extractor.extract(
            extraction_model=ExtractionModel,
            requirements=requirements,
            user_requirements=request.user_requirements,
            documents=request.documents,
        )

        return ExtractResponse(
            results=results,
            document_count=len(request.documents),
        )

    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Extractor not installed: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
