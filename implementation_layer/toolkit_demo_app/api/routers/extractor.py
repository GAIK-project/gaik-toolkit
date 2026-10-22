"""Extractor router - Data extraction endpoints"""

try:
    from utils import (
        SCHEMA_FORMAT_VERSION,
        get_api_config,
        get_model_options,
        load_schema,
        schema_id_from_requirements,
        schema_to_python_source,
        wrap_schema_with_numeric_normalizers,
    )
except ImportError:
    from api.utils import (
        SCHEMA_FORMAT_VERSION,
        get_api_config,
        get_model_options,
        load_schema,
        schema_id_from_requirements,
        schema_to_python_source,
        wrap_schema_with_numeric_normalizers,
    )

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

try:
    from utils import validate_file_size
    from utils.citations import (
        SOURCES_FIELD,
        TEXT_SOURCE_INSTRUCTION,
        UploadedDocument,
        check_sources,
        check_text_sources,
        with_sources,
    )
    from utils.model_settings import provider_error_detail
    from utils.schema_view import describe_fields, specs_by_name, structure_of
except ImportError:
    from api.utils import validate_file_size
    from api.utils.citations import (
        SOURCES_FIELD,
        TEXT_SOURCE_INSTRUCTION,
        UploadedDocument,
        check_sources,
        check_text_sources,
        with_sources,
    )
    from api.utils.model_settings import provider_error_detail
    from api.utils.schema_view import describe_fields, specs_by_name, structure_of

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory cache for temporary/generated schemas.
# Key: hash of user_requirements, Value: (schema_class, item_requirements)
_schema_cache: dict[str, tuple[Any, Any]] = {}


def _schema_key_for(user_requirements: str) -> str:
    """Return the schema key used for persistence (prefixed for the extractor)."""
    return f"extractor_{schema_id_from_requirements(user_requirements)}"


class ExtractRequest(BaseModel):
    documents: list[str]
    user_requirements: str
    fields: dict[str, str] | None = None
    include_sources: bool = False


class ExtractResponse(BaseModel):
    results: list[dict]
    document_count: int
    # include_sources: each quote checked against the text it was read from. For a PDF
    # the page boxes come from POST /extract/trace, which takes raw_sources back.
    sources: dict | None = None
    raw_sources: list | None = None


async def _run_extraction(
    extractor: Any,
    extraction_model: Any,
    requirements: Any,
    user_requirements: str,
    documents: list[str],
    include_sources: bool,
) -> ExtractResponse:
    """Extract, and with ``include_sources`` also ask for and check a quote per value.

    Tracing is the demo's own step around the extractor: the citations are one more
    field of the schema and one more instruction, and the check is plain code.
    """
    if include_sources:
        extraction_model = with_sources(extraction_model, wrapped=True)
        user_requirements = f"{user_requirements}\n\n{TEXT_SOURCE_INSTRUCTION}"
    results = await run_in_threadpool(
        extractor.extract,
        extraction_model=extraction_model,
        requirements=requirements,
        user_requirements=user_requirements,
        documents=documents,
    )
    if not include_sources:
        return ExtractResponse(results=results, document_count=len(documents))

    raw_sources = [
        result.pop(SOURCES_FIELD, None) if isinstance(result, dict) else None for result in results
    ]
    first = results[0] if results and isinstance(results[0], dict) else {}
    return ExtractResponse(
        results=results,
        document_count=len(documents),
        sources=check_text_sources(raw_sources[0] if raw_sources else None, first, documents[0]),
        raw_sources=raw_sources,
    )


class GenerateSchemaRequest(BaseModel):
    user_requirements: str


class GenerateSchemaResponse(BaseModel):
    schema_code: str
    schema_name: str
    structure_type: str
    fields: list[dict]
    schema_id: str
    # The schema for people: every field with its plain type, rule and nested records.
    field_table: list[dict] = []
    # "saved": the ready-made schema of an example. "reused": made earlier in this session.
    # "generated": made just now. Only the saved ones are on disk.
    schema_source: str = "generated"
    # The requirements the schema was built from, as the file the demo would save.
    requirements_json: str | None = None


def _requirements_json(schema, requirements, structure_type: str, user_requirements: str) -> str:
    payload = {
        "schema_format_version": SCHEMA_FORMAT_VERSION,
        "model_name": schema.__name__,
        "requirements_type": structure_type,
        "user_requirements": user_requirements,
        "requirements": requirements.model_dump(mode="json"),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


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
        schema_source = "generated"
        if loaded is not None:
            schema, requirements = loaded
            schema_source = "saved"
            logger.info("Loaded persisted extractor schema for requirements hash %s", sid)
        elif sid in _schema_cache:
            schema, requirements = _schema_cache[sid]
            schema_source = "reused"
        else:
            generator = SchemaGenerator(config, model=config["model"], **get_model_options(config))
            # Provider calls run in a worker thread: an own Aitta key may wait minutes
            # for a cold start, which must not stall the event loop and health probe.
            schema = wrap_schema_with_numeric_normalizers(
                await run_in_threadpool(
                    generator.generate_schema, user_requirements=request.user_requirements
                )
            )
            requirements = generator.item_requirements
            _schema_cache[sid] = (schema, requirements)
            logger.info("Generated temporary extractor schema for requirements hash %s", sid)

        # Read the schema itself: it also holds nested lists, which a flat list of
        # requirements cannot show.
        table = describe_fields(schema, specs_by_name(requirements.model_dump(mode="json")))
        return GenerateSchemaResponse(
            schema_code=schema_to_python_source(schema),
            schema_name=schema.__name__,
            structure_type=structure_of(table),
            requirements_json=_requirements_json(
                schema, requirements, structure_of(table), request.user_requirements
            ),
            fields=[
                {key: field[key] for key in ("name", "type", "description", "required")}
                for field in table
            ],
            schema_id=sid,
            field_table=table,
            schema_source=schema_source,
        )

    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Extractor not installed: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=provider_error_detail(e)) from e


class PlainLanguageExtractRequest(BaseModel):
    documents: list[str]
    user_requirements: str
    schema_id: str | None = None
    include_sources: bool = False


@router.post("/plain-language", response_model=ExtractResponse)
async def extract_data_plain_language(request: PlainLanguageExtractRequest):
    """
    Extract structured data from documents using plain language requirements.

    Behavior:
    - if a schema_id is provided and cached in memory, use that temporary schema
    - else, try loading the ready-made schema of an example for the exact requirements
    - else, make a schema for the session only: nothing a user types is ever saved
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
                generator = SchemaGenerator(
                    config, model=config["model"], **get_model_options(config)
                )
                schema = wrap_schema_with_numeric_normalizers(
                    await run_in_threadpool(
                        generator.generate_schema, user_requirements=request.user_requirements
                    )
                )
                item_requirements = generator.item_requirements
                _schema_cache[schema_id_from_requirements(request.user_requirements)] = (
                    schema,
                    item_requirements,
                )

        extractor = DataExtractor(config, model=config["model"], **get_model_options(config))
        return await _run_extraction(
            extractor,
            schema,
            item_requirements,
            request.user_requirements,
            request.documents,
            request.include_sources,
        )

    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Extractor not installed: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=provider_error_detail(e)) from e


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
        extractor = DataExtractor(config, model=config["model"], **get_model_options(config))

        if request.fields:
            field_definitions = {name: (str | None, None) for name in request.fields.keys()}
            extraction_model = create_model("DynamicExtraction", **field_definitions)

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
            extraction_model = create_model(
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

        return await _run_extraction(
            extractor,
            extraction_model,
            requirements,
            request.user_requirements,
            request.documents,
            request.include_sources,
        )

    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Extractor not installed: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=provider_error_detail(e)) from e


@router.post("/trace")
async def trace_sources(
    file: UploadFile = File(..., description="The PDF the text was parsed from"),
    sources: str = Form(..., description="raw_sources[0] of the extraction, as JSON"),
    data: str = Form(..., description="results[0] of the extraction, as JSON"),
):
    """Locate the quotes of a text extraction in the PDF the text was read from."""
    if Path(file.filename or "").suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Sources can be traced in a PDF only")
    try:
        raw = json.loads(sources)
        record = json.loads(data)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="sources and data must be JSON") from exc

    content = await validate_file_size(file)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "document.pdf"
        path.write_bytes(content)
        return await run_in_threadpool(
            check_sources,
            raw,
            record if isinstance(record, dict) else {},
            [UploadedDocument(file.filename or "document.pdf", path)],
            cited_pages=False,
        )
