"""Extractor router - Data extraction endpoints"""

try:
    from utils import get_api_config
except ImportError:
    from api.utils import get_api_config
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import hashlib
from typing import Any

router = APIRouter()

# In-memory cache for generated schemas
# Key: hash of user_requirements, Value: (schema_class, item_requirements)
_schema_cache: dict[str, tuple[Any, Any]] = {}


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
    schema_id: str  # Hash to identify cached schema


@router.post("/generate-schema", response_model=GenerateSchemaResponse)
async def generate_schema(request: GenerateSchemaRequest):
    """
    Generate a Pydantic schema from natural language requirements.

    - **user_requirements**: Natural language description of what to extract
    """
    if not request.user_requirements:
        raise HTTPException(status_code=400, detail="No requirements provided")

    try:
        from gaik.software_components.extractor import SchemaGenerator

        config = get_api_config()
        generator = SchemaGenerator(config)

        # Generate schema
        schema = generator.generate_schema(user_requirements=request.user_requirements)

        # Extract field information
        fields = [
            {
                "name": field.field_name,
                "type": field.field_type,
                "description": field.description,
                "required": field.required,
            }
            for field in generator.item_requirements.fields
        ]

        # Construct schema code string manually
        schema_lines = [
            "from pydantic import BaseModel, Field",
            "from typing import Literal",
            "import decimal",
            "",
            f"class {schema.__name__}(BaseModel):",
            f'    """Extraction model for {generator.item_requirements.use_case_name}"""',
            "",
        ]

        # Add fields
        for field in generator.item_requirements.fields:
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
            desc = field.description.replace('"', '\\"')
            schema_lines.append(
                f'    {field.field_name}: {field_type} = Field({default_value}, description="{desc}")'
            )

        schema_code = "\n".join(schema_lines)

        # Cache the schema for later use
        schema_id = hashlib.sha256(request.user_requirements.encode()).hexdigest()[:16]
        _schema_cache[schema_id] = (schema, generator.item_requirements)

        return GenerateSchemaResponse(
            schema_code=schema_code,
            schema_name=schema.__name__,
            structure_type=generator.structure_analysis.structure_type,
            fields=fields,
            schema_id=schema_id,
        )

    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Extractor not installed: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


class PlainLanguageExtractRequest(BaseModel):
    documents: list[str]
    user_requirements: str
    schema_id: str | None = None  # Optional: use cached schema if provided


@router.post("/plain-language", response_model=ExtractResponse)
async def extract_data_plain_language(request: PlainLanguageExtractRequest):
    """
    Extract structured data from documents using plain language requirements.
    Uses SchemaGenerator to automatically create the extraction schema.

    - **documents**: List of document texts to extract from
    - **user_requirements**: Natural language description of what to extract and structure
    """
    if not request.documents:
        raise HTTPException(status_code=400, detail="No documents provided")

    if not request.user_requirements:
        raise HTTPException(status_code=400, detail="No requirements provided")

    try:
        from gaik.software_components.extractor import (
            DataExtractor,
            SchemaGenerator,
        )

        config = get_api_config()

        # Check if we have a cached schema
        if request.schema_id and request.schema_id in _schema_cache:
            # Use cached schema
            schema, item_requirements = _schema_cache[request.schema_id]
        else:
            # Generate schema from plain language requirements
            generator = SchemaGenerator(config)
            schema = generator.generate_schema(user_requirements=request.user_requirements)
            item_requirements = generator.item_requirements

            # Cache for future use
            schema_id = hashlib.sha256(request.user_requirements.encode()).hexdigest()[:16]
            _schema_cache[schema_id] = (schema, item_requirements)

        # Extract data using generated schema
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

        # Create dynamic extraction model if fields provided
        if request.fields:
            field_definitions = {name: (str | None, None) for name in request.fields.keys()}
            ExtractionModel = create_model("DynamicExtraction", **field_definitions)  # noqa: N806

            # Create proper FieldSpec objects
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
            # Use a simple generic model
            ExtractionModel = create_model(  # noqa: N806
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
