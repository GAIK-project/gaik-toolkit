"""Extractor router - Data extraction endpoints"""

try:
    from utils import (
        get_api_config,
        load_schema,
        save_schema,
        schema_id_from_requirements,
        wrap_schema_with_numeric_normalizers,
    )
except ImportError:
    from api.utils import (
        get_api_config,
        load_schema,
        save_schema,
        schema_id_from_requirements,
        wrap_schema_with_numeric_normalizers,
    )

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory cache for temporary/generated schemas.
# Key: hash of user_requirements, Value: (schema_class, item_requirements)
_schema_cache: dict[str, tuple[Any, Any]] = {}


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


_KNOWN_TYPES = {"decimal.Decimal", "int", "float", "bool"}


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


def _schema_key_for(user_requirements: str) -> str:
    """Return the schema key used for persistence (prefixed for the extractor)."""
    return f"extractor_{schema_id_from_requirements(user_requirements)}"


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
        sid = schema_id_from_requirements(request.user_requirements)
        schema_key = _schema_key_for(request.user_requirements)

        loaded = load_schema(schema_key, request.user_requirements)
        if loaded is not None:
            schema, requirements = loaded
            logger.info("Loaded persisted extractor schema for requirements hash %s", sid)
        elif sid in _schema_cache:
            schema, requirements = _schema_cache[sid]
        else:
            generator = SchemaGenerator(config)
            schema = wrap_schema_with_numeric_normalizers(
                generator.generate_schema(user_requirements=request.user_requirements)
            )
            requirements = generator.item_requirements
            _schema_cache[sid] = (schema, requirements)
            logger.info("Generated temporary extractor schema for requirements hash %s", sid)

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
        schema_key = _schema_key_for(request.user_requirements)

        if request.schema_id and request.schema_id in _schema_cache:
            schema, item_requirements = _schema_cache[request.schema_id]
        else:
            loaded = load_schema(schema_key, request.user_requirements)
            if loaded is not None:
                schema, item_requirements = loaded
            else:
                generator = SchemaGenerator(config)
                schema = wrap_schema_with_numeric_normalizers(
                    generator.generate_schema(user_requirements=request.user_requirements)
                )
                item_requirements = generator.item_requirements
                save_schema(schema, item_requirements, schema_key, request.user_requirements)
                logger.info(
                    "Saved persisted extractor schema for requirements hash %s",
                    schema_id_from_requirements(request.user_requirements),
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
