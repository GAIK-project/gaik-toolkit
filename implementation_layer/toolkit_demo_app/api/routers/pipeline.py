"""Pipeline router - End-to-end pipeline endpoints for demos."""

import asyncio
import importlib.util
import io
import json
import logging
import os
import tempfile
import uuid
from collections.abc import AsyncGenerator
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal, get_args, get_origin

try:
    from utils import (
        MAX_FILE_SIZE_BYTES,
        MAX_FILE_SIZE_MB,
        get_api_config,
        sse_event,
        validate_file_size,
        validate_vision_page_limit,
    )
except ImportError:
    from api.utils import (
        MAX_FILE_SIZE_BYTES,
        MAX_FILE_SIZE_MB,
        get_api_config,
        sse_event,
        validate_file_size,
        validate_vision_page_limit,
    )
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)
router = APIRouter()

PDF_CLEANUP_AFTER_HOURS = 1

# Temporary storage for generated PDFs (path and creation time)
PDF_STORAGE: dict[str, Path] = {}
PDF_TIMESTAMPS: dict[str, datetime] = {}
SCHEMA_DIR = Path(__file__).parent.parent / "schemas"
SCHEMA_DIR.mkdir(exist_ok=True)


def _parse_document_content(tmp_path: str, suffix: str, parser_type: str, config: dict):
    validate_vision_page_limit(tmp_path, suffix, parser_type)

    if parser_type == "vision":
        from gaik.software_components.parsers import VisionParser

        parser = VisionParser(openai_config=config)
        parsed_content = parser.convert_pdf(tmp_path)
        if isinstance(parsed_content, list):
            parsed_content = "\n\n".join(parsed_content)
        return parsed_content

    if parser_type == "vision_plus":
        from gaik.software_components.RAG.rag_parser_vision import VisionRagParser

        parser = VisionRagParser(
            vision_config=config,
            verbose=False,
            save_markdown=False,
            enable_ocr=False,
            enable_table_structure=True,
            enable_formula_enrichment=False,
        )
        markdown, _chunks = parser.convert_doc_to_chunks_with_vision(tmp_path, return_markdown=True)
        return markdown

    if parser_type == "docling_api":
        api_base = os.getenv("DOCLING_API_BASE")
        password = os.getenv("DOCLING_API_PASSWORD")
        if api_base and password:
            try:
                from gaik.software_components.parsers.docling_api_client import DoclingApiClientParser

                parser = DoclingApiClientParser(api_base=api_base, password=password)
                result = parser.parse_document(tmp_path)
                parsed_markdown = result.get("parsed_markdown", "")
                if parsed_markdown:
                    return parsed_markdown
                logger.warning("HH Parser returned empty markdown; falling back to PyMuPDF")
            except Exception as exc:
                logger.warning("HH Parser unavailable; falling back to PyMuPDF: %s", exc)
        else:
            logger.info("HH Parser not configured; falling back to PyMuPDF")

    if parser_type == "docx":
        from gaik.software_components.parsers import DocxParser

        parser = DocxParser()
        return parser.parse_docx(tmp_path)

    from gaik.software_components.parsers import PyMuPDFParser

    parser = PyMuPDFParser()
    return parser.parse_pdf(tmp_path)


def _clean_schema_dump(raw_dump: str) -> str:
    """Strip header/footer lines from print_pydantic_schema output."""
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
    """Remove fully qualified extractor-schema references from cached modules."""
    return schema_code.replace("gaik.software_components.extractor.schema.", "")


def _schema_paths(schema_key: str) -> tuple[Path, Path]:
    safe_key = "".join(c if c.isalnum() or c in {"_", "-"} else "_" for c in schema_key).strip("_") or "schema"
    return SCHEMA_DIR / f"{safe_key}_schema.py", SCHEMA_DIR / f"{safe_key}_requirements.json"


def _save_schema(schema: type, requirements, schema_key: str, user_requirements: str) -> None:
    from gaik.software_components.extractor.schema import print_pydantic_schema

    schema_path, req_path = _schema_paths(schema_key)

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


def _load_schema(schema_key: str, user_requirements: str):
    from gaik.software_components.extractor import ExtractionRequirements

    schema_path, req_path = _schema_paths(schema_key)
    if not (schema_path.exists() and req_path.exists()):
        return None

    data = json.loads(req_path.read_text(encoding="utf-8"))
    if data.get("user_requirements") != user_requirements:
        return None

    model_name = data["model_name"]
    requirements = ExtractionRequirements(**data["requirements"])

    source = schema_path.read_text(encoding="utf-8")
    sanitized = _sanitize_schema_code(source)
    if sanitized != source:
        schema_path.write_text(sanitized, encoding="utf-8")
        logger.info("Sanitized cached schema module: %s", schema_path)

    spec = importlib.util.spec_from_file_location(model_name, schema_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader is not None
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    schema = getattr(module, model_name)
    return schema, requirements


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


def _get_or_create_schema(config, user_requirements: str, schema_key: str | None, regenerate_schema: bool):
    from gaik.software_components.extractor.schema import SchemaGenerator

    loaded = None
    if schema_key:
        loaded = _load_schema(schema_key, user_requirements)
        if loaded is not None and not regenerate_schema:
            logger.info("Loaded existing schema for key %s", schema_key)
            schema, requirements = loaded
            return _wrap_schema_with_numeric_normalizers(schema), requirements, False

    generator = SchemaGenerator(config=config)
    schema = generator.generate_schema(user_requirements)
    requirements = generator.item_requirements

    if schema_key and loaded is None and not regenerate_schema:
        _save_schema(schema, requirements, schema_key, user_requirements)
        logger.info("Saved schema for key %s", schema_key)

    return _wrap_schema_with_numeric_normalizers(schema), requirements, True


async def cleanup_old_pdfs():
    """Background task to clean up old PDFs."""
    while True:
        await asyncio.sleep(3600)  # Check every hour
        cutoff = datetime.now() - timedelta(hours=PDF_CLEANUP_AFTER_HOURS)
        jobs_to_delete = []
        for job_id, timestamp in list(PDF_TIMESTAMPS.items()):
            if timestamp < cutoff:
                jobs_to_delete.append(job_id)
        for job_id in jobs_to_delete:
            if job_id in PDF_STORAGE:
                path = PDF_STORAGE[job_id]
                path.unlink(missing_ok=True)
                del PDF_STORAGE[job_id]
            if job_id in PDF_TIMESTAMPS:
                del PDF_TIMESTAMPS[job_id]


# Logo path for PDF generation (letter-only logo works better for PDF headers)
LOGO_PATH = Path(__file__).parent.parent.parent / "public" / "logos" / "gaik-logo-letter-only.png"


class PipelineStep(BaseModel):
    """A single step in the pipeline."""

    step: int
    name: str
    status: Literal["pending", "in_progress", "completed", "error"]
    message: str | None = None


class AudioPipelineResponse(BaseModel):
    """Response from audio pipeline."""

    job_id: str
    steps: list[PipelineStep]
    raw_transcript: str | None = None
    enhanced_transcript: str | None = None
    extracted_data: list[dict] | None = None
    pdf_available: bool = False
    error: str | None = None


class DocumentPipelineResponse(BaseModel):
    """Response from document pipeline."""

    job_id: str
    steps: list[PipelineStep]
    parsed_content: str | None = None
    extracted_data: list[dict] | None = None
    pdf_available: bool = False
    error: str | None = None


class TextPipelineResponse(BaseModel):
    """Response from text pipeline."""

    job_id: str
    steps: list[PipelineStep]
    input_text: str | None = None
    extracted_data: list[dict] | None = None
    pdf_available: bool = False
    error: str | None = None


@router.post("/audio", response_model=AudioPipelineResponse)
async def audio_pipeline(
    file: UploadFile = File(...),
    user_requirements: str = Form(...),
    generate_pdf: bool = Form(False),
    pdf_title: str = Form("Extracted Data Report"),
    enhanced: bool = Form(False),
    compress_audio: bool = Form(True),
    schema_key: str | None = Form(None),
    regenerate_schema: bool = Form(False),
):
    """
    Run the complete audio pipeline: Transcribe -> Extract -> (PDF).

    - **file**: Audio/video file (mp3, wav, mp4, m4a, etc.)
    - **user_requirements**: What data to extract from the transcript
    - **generate_pdf**: Whether to generate a PDF report
    - **pdf_title**: Title for the generated PDF report
    - **enhanced**: Whether to enhance transcript with LLM
    - **compress_audio**: Whether to compress audio before sending
    """
    job_id = str(uuid.uuid4())

    # Initialize steps
    steps = [
        PipelineStep(step=1, name="Upload", status="completed"),
        PipelineStep(step=2, name="Transcribe", status="pending"),
        PipelineStep(step=3, name="Extract", status="pending"),
    ]
    if generate_pdf:
        steps.append(PipelineStep(step=4, name="Generate PDF", status="pending"))

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    suffix = Path(file.filename).suffix.lower()
    supported = [".mp3", ".wav", ".m4a", ".mp4", ".webm", ".ogg", ".flac"]
    if suffix not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}. Supported: {', '.join(supported)}",
        )

    # Validate file size and save temporarily
    content = await validate_file_size(file)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        config = get_api_config()

        # Step 2: Transcribe
        steps[1].status = "in_progress"

        from gaik.software_modules.audio_to_structured_data import AudioToStructuredData

        pipeline = AudioToStructuredData(api_config=config)

        schema = requirements = None
        if schema_key:
            schema, requirements, _generated_new_schema = _get_or_create_schema(
                config=config,
                user_requirements=user_requirements,
                schema_key=schema_key,
                regenerate_schema=regenerate_schema,
            )

        result = pipeline.run(
            file_path=tmp_path,
            user_requirements=user_requirements,
            transcriber_ctor={
                "enhanced_transcript": enhanced,
                "compress_audio": compress_audio,
            },
            schema=schema,
            requirements=requirements,
        )

        steps[1].status = "completed"
        steps[1].message = "Transcription complete"

        # Step 3: Extract (already done by pipeline.run)
        steps[2].status = "completed"
        steps[2].message = f"Extracted {len(result.extracted_fields)} items"

        response = AudioPipelineResponse(
            job_id=job_id,
            steps=steps,
            raw_transcript=result.transcription.raw_transcript,
            enhanced_transcript=result.transcription.enhanced_transcript,
            extracted_data=result.extracted_fields,
        )

        # Step 4: Generate PDF if requested
        if generate_pdf:
            try:
                steps[3].status = "in_progress"

                from utils.pdf_generator import StructuredDataToPDF

                logo = LOGO_PATH if LOGO_PATH.exists() else None
                pdf_generator = StructuredDataToPDF(title=pdf_title, logo_path=logo)
                pdf_path = Path(tempfile.gettempdir()) / f"{job_id}.pdf"

                # Use extracted_fields if available, otherwise create from transcript
                if result.extracted_fields:
                    pdf_data = result.extracted_fields
                else:
                    transcript = (
                        result.transcription.enhanced_transcript
                        or result.transcription.raw_transcript
                    )
                    pdf_data = [{"transcript": transcript}]
                pdf_generator.run(pdf_data, pdf_path)

                PDF_STORAGE[job_id] = pdf_path
                PDF_TIMESTAMPS[job_id] = datetime.now()
                response.pdf_available = True
                steps[3].status = "completed"
                steps[3].message = "PDF generated"
            except Exception as e:
                steps[3].status = "error"
                steps[3].message = f"PDF generation failed: {e}"

        return response

    except ImportError as e:
        raise HTTPException(
            status_code=500, detail=f"Required components not installed: {e}"
        ) from e
    except Exception as e:
        # Mark current step as error
        for step in steps:
            if step.status == "in_progress":
                step.status = "error"
                step.message = str(e)
                break

        return AudioPipelineResponse(
            job_id=job_id,
            steps=steps,
            error=str(e),
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.post("/document", response_model=DocumentPipelineResponse)
async def document_pipeline(
    file: UploadFile = File(...),
    user_requirements: str = Form(...),
    parser_type: Literal["auto", "pymupdf", "docx", "vision", "vision_plus", "docling_api"] = Form("docling_api"),
    generate_pdf: bool = Form(False),
    pdf_title: str = Form("Extracted Data Report"),
    schema_key: str | None = Form(None),
    regenerate_schema: bool = Form(False),
):
    """
    Run the complete document pipeline: Parse -> Extract -> (PDF).

    - **file**: Document file (PDF, DOCX, or image)
    - **user_requirements**: What data to extract from the document
    - **parser_type**: Parser to use (auto, pymupdf, docx, vision, vision_plus, docling_api)
    - **generate_pdf**: Whether to generate a PDF report
    - **pdf_title**: Title for the generated PDF report
    """
    job_id = str(uuid.uuid4())

    # Initialize steps
    steps = [
        PipelineStep(step=1, name="Upload", status="completed"),
        PipelineStep(step=2, name="Parse", status="pending"),
        PipelineStep(step=3, name="Extract", status="pending"),
    ]
    if generate_pdf:
        steps.append(PipelineStep(step=4, name="Generate PDF", status="pending"))

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    suffix = Path(file.filename).suffix.lower()
    supported_docs = [".pdf", ".docx"]
    supported_images = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp"]

    if suffix not in supported_docs + supported_images:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type: {suffix}. "
                f"Supported: {', '.join(supported_docs + supported_images)}"
            ),
        )

    # Auto-detect parser type
    if parser_type == "auto":
        if suffix == ".docx":
            parser_type = "docx"
        elif suffix in supported_images:
            parser_type = "vision"
        else:
            parser_type = "pymupdf"

    # Validate file size and save temporarily
    content = await validate_file_size(file)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        config = get_api_config()

        # Step 2: Parse
        steps[1].status = "in_progress"

        from gaik.software_modules.documents_to_structured_data import (
            DocumentsToStructuredData,
        )

        from gaik.software_components.extractor import DataExtractor

        extraction_model, requirements, _generated_new_schema = _get_or_create_schema(
            config=config,
            user_requirements=user_requirements,
            schema_key=schema_key,
            regenerate_schema=regenerate_schema,
        )

        parsed_content = _parse_document_content(tmp_path, suffix, parser_type, config)

        steps[1].status = "completed"
        steps[1].message = "Document parsed"

        extractor = DataExtractor(config=config)
        extracted_data = extractor.extract(
            extraction_model=extraction_model,
            requirements=requirements,
            user_requirements=user_requirements,
            documents=[parsed_content],
        )

        steps[2].status = "completed"
        steps[2].message = f"Extracted {len(extracted_data)} items"

        response = DocumentPipelineResponse(
            job_id=job_id,
            steps=steps,
            parsed_content=parsed_content,
            extracted_data=extracted_data,
        )

        # Step 4: Generate PDF if requested
        if generate_pdf:
            try:
                steps[3].status = "in_progress"

                from utils.pdf_generator import StructuredDataToPDF

                logo = LOGO_PATH if LOGO_PATH.exists() else None
                pdf_generator = StructuredDataToPDF(title=pdf_title, logo_path=logo)
                pdf_path = Path(tempfile.gettempdir()) / f"{job_id}.pdf"

                # Use extracted_fields if available, otherwise create from parsed content
                pdf_data = (
                    result.extracted_fields
                    if result.extracted_fields
                    else [{"parsed_content": parsed_content or "No content extracted"}]
                )
                pdf_generator.run(pdf_data, pdf_path)

                PDF_STORAGE[job_id] = pdf_path
                PDF_TIMESTAMPS[job_id] = datetime.now()
                response.pdf_available = True
                steps[3].status = "completed"
                steps[3].message = "PDF generated"
            except Exception as e:
                steps[3].status = "error"
                steps[3].message = f"PDF generation failed: {e}"

        return response

    except ImportError as e:
        raise HTTPException(
            status_code=500, detail=f"Required components not installed: {e}"
        ) from e
    except Exception as e:
        # Mark current step as error
        for step in steps:
            if step.status == "in_progress":
                step.status = "error"
                step.message = str(e)
                break

        return DocumentPipelineResponse(
            job_id=job_id,
            steps=steps,
            error=str(e),
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.post("/text", response_model=TextPipelineResponse)
async def text_pipeline(
    text: str = Form(...),
    user_requirements: str = Form(...),
    generate_pdf: bool = Form(False),
    pdf_title: str = Form("Extracted Data Report"),
    schema_key: str | None = Form(None),
    regenerate_schema: bool = Form(False),
):
    """
    Run the text extraction pipeline: Extract structured data from text.

    - **text**: Input text to extract data from
    - **user_requirements**: What data to extract from the text
    - **generate_pdf**: Whether to generate a PDF report
    - **pdf_title**: Title for the generated PDF report
    """
    job_id = str(uuid.uuid4())

    # Initialize steps
    steps = [
        PipelineStep(step=1, name="Input", status="completed"),
        PipelineStep(step=2, name="Extract", status="pending"),
    ]
    if generate_pdf:
        steps.append(PipelineStep(step=3, name="Generate PDF", status="pending"))

    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="No text provided")

    try:
        config = get_api_config()

        # Step 2: Extract structured data
        steps[1].status = "in_progress"

        from gaik.software_components.extractor.extractor import DataExtractor

        # Step 1: Generate or load schema from user requirements
        extraction_model, requirements, _generated_new_schema = _get_or_create_schema(
            config=config,
            user_requirements=user_requirements,
            schema_key=schema_key,
            regenerate_schema=regenerate_schema,
        )

        # Step 2: Extract data using the generated schema
        extractor = DataExtractor(config=config)
        extracted_data = extractor.extract(
            extraction_model=extraction_model,
            requirements=requirements,
            user_requirements=user_requirements,
            documents=[text],
        )

        steps[1].status = "completed"
        steps[1].message = f"Extracted {len(extracted_data)} items"

        response = TextPipelineResponse(
            job_id=job_id,
            steps=steps,
            input_text=text,
            extracted_data=extracted_data,
        )

        # Step 3: Generate PDF if requested
        if generate_pdf:
            try:
                pdf_step_idx = 2
                steps[pdf_step_idx].status = "in_progress"

                from utils.pdf_generator import StructuredDataToPDF

                logo = LOGO_PATH if LOGO_PATH.exists() else None
                pdf_generator = StructuredDataToPDF(title=pdf_title, logo_path=logo)
                pdf_path = Path(tempfile.gettempdir()) / f"{job_id}.pdf"

                # Use extracted_data if available, otherwise create from input text
                pdf_data = extracted_data if extracted_data else [{"input_text": text}]
                pdf_generator.run(pdf_data, pdf_path)

                PDF_STORAGE[job_id] = pdf_path
                PDF_TIMESTAMPS[job_id] = datetime.now()
                response.pdf_available = True
                steps[pdf_step_idx].status = "completed"
                steps[pdf_step_idx].message = "PDF generated"
            except Exception as e:
                steps[pdf_step_idx].status = "error"
                steps[pdf_step_idx].message = f"PDF generation failed: {e}"

        return response

    except ImportError as e:
        raise HTTPException(
            status_code=500, detail=f"Required components not installed: {e}"
        ) from e
    except Exception as e:
        # Mark current step as error
        for step in steps:
            if step.status == "in_progress":
                step.status = "error"
                step.message = str(e)
                break

        return TextPipelineResponse(
            job_id=job_id,
            steps=steps,
            error=str(e),
        )


@router.post("/audio/stream")
async def audio_pipeline_stream(
    file: UploadFile = File(...),
    user_requirements: str = Form(...),
    generate_pdf: bool = Form(False),
    pdf_title: str = Form("Extracted Data Report"),
    enhanced: bool = Form(False),
    compress_audio: bool = Form(True),
    schema_key: str | None = Form(None),
    regenerate_schema: bool = Form(False),
):
    """
    Run the audio pipeline with SSE streaming progress updates.

    Returns Server-Sent Events with progress updates and final result.
    """
    job_id = str(uuid.uuid4())

    # Validate file first
    if not file.filename:

        async def error_gen() -> AsyncGenerator[str, None]:
            yield sse_event("error", {"message": "No filename provided"})

        return StreamingResponse(error_gen(), media_type="text/event-stream")

    suffix = Path(file.filename).suffix.lower()
    supported = [".mp3", ".wav", ".m4a", ".mp4", ".webm", ".ogg", ".flac"]
    if suffix not in supported:

        async def error_gen() -> AsyncGenerator[str, None]:
            yield sse_event("error", {"message": f"Unsupported file type: {suffix}"})

        return StreamingResponse(error_gen(), media_type="text/event-stream")

    # Validate file size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:

        async def error_gen() -> AsyncGenerator[str, None]:
            yield sse_event(
                "error", {"message": f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB"}
            )

        return StreamingResponse(error_gen(), media_type="text/event-stream")

    # Save uploaded file
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    async def event_generator() -> AsyncGenerator[str, None]:
        steps = [
            {"step": 1, "name": "Transcription", "status": "pending"},
            {"step": 2, "name": "Schema Generation", "status": "pending"},
            {"step": 3, "name": "Data Extraction", "status": "pending"},
        ]
        if generate_pdf:
            steps.append({"step": 4, "name": "Report Formatting", "status": "pending"})

        # Send initial steps
        yield sse_event("steps", {"steps": steps})

        try:
            config = get_api_config()

            # Step 1: Transcription
            steps[0]["status"] = "in_progress"
            steps[0]["message"] = "Converting audio to text..."
            yield sse_event("step_update", steps[0])

            from gaik.software_components.transcriber import Transcriber

            transcriber = Transcriber(
                api_config=config,
                enhanced_transcript=enhanced,
                compress_audio=compress_audio,
            )
            transcription = transcriber.transcribe(file_path=tmp_path)

            steps[0]["status"] = "completed"
            steps[0]["message"] = "Transcription complete"
            yield sse_event("step_update", steps[0])

            # Step 2: Schema Generation
            steps[1]["status"] = "in_progress"
            steps[1]["message"] = "Analyzing requirements..."
            yield sse_event("step_update", steps[1])

            from gaik.software_components.extractor import DataExtractor

            extraction_model, requirements, generated_new_schema = _get_or_create_schema(
                config=config,
                user_requirements=user_requirements,
                schema_key=schema_key,
                regenerate_schema=regenerate_schema,
            )

            steps[1]["status"] = "completed"
            steps[1]["message"] = "Generated new schema" if generated_new_schema else "Loaded saved schema"
            yield sse_event("step_update", steps[1])

            # Step 3: Data Extraction
            steps[2]["status"] = "in_progress"
            steps[2]["message"] = "Extracting incident data..."
            yield sse_event("step_update", steps[2])

            documents = [transcription.enhanced_transcript or transcription.raw_transcript]
            extractor = DataExtractor(config=config)
            extracted_data = extractor.extract(
                extraction_model=extraction_model,
                requirements=requirements,
                user_requirements=user_requirements,
                documents=documents,
            )

            steps[2]["status"] = "completed"
            steps[2]["message"] = f"Extracted {len(extracted_data)} items"
            yield sse_event("step_update", steps[2])

            # Step 4: PDF Generation (if requested)
            pdf_available = False
            if generate_pdf:
                steps[3]["status"] = "in_progress"
                steps[3]["message"] = "Generating report..."
                yield sse_event("step_update", steps[3])

                try:
                    try:
                        from utils.pdf_generator import StructuredDataToPDF
                    except ImportError:
                        from api.utils.pdf_generator import StructuredDataToPDF

                    logo = LOGO_PATH if LOGO_PATH.exists() else None
                    pdf_generator = StructuredDataToPDF(title=pdf_title, logo_path=logo)
                    pdf_path = Path(tempfile.gettempdir()) / f"{job_id}.pdf"

                    if extracted_data:
                        pdf_data = extracted_data
                    else:
                        transcript = (
                            transcription.enhanced_transcript or transcription.raw_transcript
                        )
                        pdf_data = [{"transcript": transcript}]
                    pdf_generator.run(pdf_data, pdf_path)

                    PDF_STORAGE[job_id] = pdf_path
                    PDF_TIMESTAMPS[job_id] = datetime.now()
                    pdf_available = True
                    steps[3]["status"] = "completed"
                    steps[3]["message"] = "PDF generated"
                    yield sse_event("step_update", steps[3])
                except Exception as e:
                    steps[3]["status"] = "error"
                    steps[3]["message"] = f"PDF generation failed: {e}"
                    yield sse_event("step_update", steps[3])

            # Send final result
            yield sse_event(
                "result",
                {
                    "job_id": job_id,
                    "raw_transcript": transcription.raw_transcript,
                    "enhanced_transcript": transcription.enhanced_transcript,
                    "extracted_data": extracted_data,
                    "pdf_available": pdf_available,
                },
            )

        except ImportError as e:
            yield sse_event("error", {"message": f"Required components not installed: {e}"})
        except Exception as e:
            for step in steps:
                if step["status"] == "in_progress":
                    step["status"] = "error"
                    step["message"] = str(e)
                    yield sse_event("step_update", step)
                    break
            yield sse_event("error", {"message": str(e)})
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/text/stream")
async def text_pipeline_stream(
    text: str = Form(...),
    user_requirements: str = Form(...),
    generate_pdf: bool = Form(False),
    pdf_title: str = Form("Extracted Data Report"),
    schema_key: str | None = Form(None),
    regenerate_schema: bool = Form(False),
):
    """
    Run the text extraction pipeline with SSE streaming progress updates.

    Returns Server-Sent Events with progress updates and final result.
    """
    job_id = str(uuid.uuid4())

    async def event_generator() -> AsyncGenerator[str, None]:
        steps = [
            {"step": 1, "name": "Analyzing Requirements", "status": "pending"},
            {"step": 2, "name": "Extracting Details", "status": "pending"},
        ]
        if generate_pdf:
            steps.append({"step": 3, "name": "Generate PDF", "status": "pending"})

        # Send initial steps
        yield sse_event("steps", {"steps": steps})

        if not text or not text.strip():
            yield sse_event("error", {"message": "No text provided"})
            return

        try:
            config = get_api_config()

            # Step 1: Generate schema
            steps[0]["status"] = "in_progress"
            yield sse_event("step_update", steps[0])

            from gaik.software_components.extractor.extractor import DataExtractor

            extraction_model, requirements, generated_new_schema = _get_or_create_schema(
                config=config,
                user_requirements=user_requirements,
                schema_key=schema_key,
                regenerate_schema=regenerate_schema,
            )

            steps[0]["status"] = "completed"
            steps[0]["message"] = "Generated new schema" if generated_new_schema else "Loaded saved schema"
            yield sse_event("step_update", steps[0])

            # Step 2: Extract data
            steps[1]["status"] = "in_progress"
            yield sse_event("step_update", steps[1])

            extractor = DataExtractor(config=config)
            extracted_data = extractor.extract(
                extraction_model=extraction_model,
                requirements=requirements,
                user_requirements=user_requirements,
                documents=[text],
            )

            steps[1]["status"] = "completed"
            steps[1]["message"] = f"Extracted {len(extracted_data)} items"
            yield sse_event("step_update", steps[1])

            # Step 3: Generate PDF if requested
            pdf_available = False
            if generate_pdf:
                pdf_step_idx = 2
                steps[pdf_step_idx]["status"] = "in_progress"
                yield sse_event("step_update", steps[pdf_step_idx])

                try:
                    try:
                        from utils.pdf_generator import StructuredDataToPDF
                    except ImportError:
                        from api.utils.pdf_generator import StructuredDataToPDF

                    logo = LOGO_PATH if LOGO_PATH.exists() else None
                    pdf_generator = StructuredDataToPDF(title=pdf_title, logo_path=logo)
                    pdf_path = Path(tempfile.gettempdir()) / f"{job_id}.pdf"

                    # Use extracted_data if available, otherwise create from input text
                    pdf_data = extracted_data if extracted_data else [{"input_text": text}]
                    pdf_generator.run(pdf_data, pdf_path)

                    PDF_STORAGE[job_id] = pdf_path
                    PDF_TIMESTAMPS[job_id] = datetime.now()
                    pdf_available = True
                    steps[pdf_step_idx]["status"] = "completed"
                    steps[pdf_step_idx]["message"] = "PDF generated"
                    yield sse_event("step_update", steps[pdf_step_idx])
                except Exception as e:
                    steps[pdf_step_idx]["status"] = "error"
                    steps[pdf_step_idx]["message"] = f"PDF generation failed: {e}"
                    yield sse_event("step_update", steps[pdf_step_idx])

            # Send final result
            yield sse_event(
                "result",
                {
                    "job_id": job_id,
                    "input_text": text,
                    "extracted_data": extracted_data,
                    "pdf_available": pdf_available,
                },
            )

        except ImportError as e:
            yield sse_event("error", {"message": f"Required components not installed: {e}"})
        except Exception as e:
            # Mark current step as error
            for step in steps:
                if step["status"] == "in_progress":
                    step["status"] = "error"
                    step["message"] = str(e)
                    yield sse_event("step_update", step)
                    break
            yield sse_event("error", {"message": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/document/stream")
async def document_pipeline_stream(
    file: UploadFile = File(...),
    user_requirements: str = Form(...),
    parser_type: Literal["auto", "pymupdf", "docx", "vision", "vision_plus", "docling_api"] = Form("docling_api"),
    generate_pdf: bool = Form(False),
    pdf_title: str = Form("Extracted Data Report"),
    schema_key: str | None = Form(None),
    regenerate_schema: bool = Form(False),
):
    """
    Run the document pipeline with SSE streaming progress updates.

    Returns Server-Sent Events with progress updates and final result.
    """
    job_id = str(uuid.uuid4())

    # Validate file first
    if not file.filename:

        async def error_gen() -> AsyncGenerator[str, None]:
            yield sse_event("error", {"message": "No filename provided"})

        return StreamingResponse(error_gen(), media_type="text/event-stream")

    suffix = Path(file.filename).suffix.lower()
    supported_docs = [".pdf", ".docx"]
    supported_images = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp"]

    if suffix not in supported_docs + supported_images:

        async def error_gen() -> AsyncGenerator[str, None]:
            yield sse_event("error", {"message": f"Unsupported file type: {suffix}"})

        return StreamingResponse(error_gen(), media_type="text/event-stream")

    # Auto-detect parser type
    actual_parser_type = parser_type
    if parser_type == "auto":
        if suffix == ".docx":
            actual_parser_type = "docx"
        elif suffix in supported_images:
            actual_parser_type = "vision"
        else:
            actual_parser_type = "pymupdf"

    # Validate file size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:

        async def error_gen() -> AsyncGenerator[str, None]:
            yield sse_event(
                "error", {"message": f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB"}
            )

        return StreamingResponse(error_gen(), media_type="text/event-stream")

    # Save uploaded file
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    async def event_generator() -> AsyncGenerator[str, None]:
        steps = [
            {"step": 1, "name": "Parsing Document", "status": "pending"},
            {"step": 2, "name": "Schema Generation", "status": "pending"},
            {"step": 3, "name": "Data Extraction", "status": "pending"},
        ]
        if generate_pdf:
            steps.append({"step": 4, "name": "Report Formatting", "status": "pending"})

        # Send initial steps
        yield sse_event("steps", {"steps": steps})

        try:
            config = get_api_config()

            # Step 1: Parse document
            steps[0]["status"] = "in_progress"
            steps[0]["message"] = "Parsing document content..."
            yield sse_event("step_update", steps[0])

            parsed_content = _parse_document_content(tmp_path, suffix, actual_parser_type, config)

            steps[0]["status"] = "completed"
            steps[0]["message"] = "Document parsed"
            yield sse_event("step_update", steps[0])

            # Step 2: Schema Generation
            steps[1]["status"] = "in_progress"
            steps[1]["message"] = "Analyzing requirements..."
            yield sse_event("step_update", steps[1])

            from gaik.software_components.extractor import DataExtractor

            extraction_model, requirements, generated_new_schema = _get_or_create_schema(
                config=config,
                user_requirements=user_requirements,
                schema_key=schema_key,
                regenerate_schema=regenerate_schema,
            )

            steps[1]["status"] = "completed"
            steps[1]["message"] = "Generated new schema" if generated_new_schema else "Loaded saved schema"
            yield sse_event("step_update", steps[1])

            # Step 3: Data Extraction
            steps[2]["status"] = "in_progress"
            steps[2]["message"] = "Extracting structured data..."
            yield sse_event("step_update", steps[2])

            extractor = DataExtractor(config=config)
            extracted_data = extractor.extract(
                extraction_model=extraction_model,
                requirements=requirements,
                user_requirements=user_requirements,
                documents=[parsed_content],
            )

            steps[2]["status"] = "completed"
            steps[2]["message"] = f"Extracted {len(extracted_data)} items"
            yield sse_event("step_update", steps[2])

            # Step 4: PDF Generation (if requested)
            pdf_available = False
            if generate_pdf:
                steps[3]["status"] = "in_progress"
                steps[3]["message"] = "Generating report..."
                yield sse_event("step_update", steps[3])

                try:
                    try:
                        from utils.pdf_generator import StructuredDataToPDF
                    except ImportError:
                        from api.utils.pdf_generator import StructuredDataToPDF

                    logo = LOGO_PATH if LOGO_PATH.exists() else None
                    pdf_generator = StructuredDataToPDF(title=pdf_title, logo_path=logo)
                    pdf_path = Path(tempfile.gettempdir()) / f"{job_id}.pdf"

                    pdf_data = (
                        extracted_data
                        if extracted_data
                        else [{"parsed_content": parsed_content or "No content extracted"}]
                    )
                    pdf_generator.run(pdf_data, pdf_path)

                    PDF_STORAGE[job_id] = pdf_path
                    PDF_TIMESTAMPS[job_id] = datetime.now()
                    pdf_available = True
                    steps[3]["status"] = "completed"
                    steps[3]["message"] = "PDF generated"
                    yield sse_event("step_update", steps[3])
                except Exception as e:
                    steps[3]["status"] = "error"
                    steps[3]["message"] = f"PDF generation failed: {e}"
                    yield sse_event("step_update", steps[3])

            # Send final result
            yield sse_event(
                "result",
                {
                    "job_id": job_id,
                    "parsed_content": parsed_content,
                    "extracted_data": extracted_data,
                    "pdf_available": pdf_available,
                },
            )

        except ImportError as e:
            yield sse_event("error", {"message": f"Required components not installed: {e}"})
        except Exception as e:
            for step in steps:
                if step["status"] == "in_progress":
                    step["status"] = "error"
                    step["message"] = str(e)
                    yield sse_event("step_update", step)
                    break
            yield sse_event("error", {"message": str(e)})
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/pdf/{job_id}")
async def download_pdf(job_id: str):
    """Download a generated PDF by job ID."""
    if job_id not in PDF_STORAGE:
        raise HTTPException(status_code=404, detail="PDF not found")

    pdf_path = PDF_STORAGE[job_id]
    if not pdf_path.exists():
        del PDF_STORAGE[job_id]
        raise HTTPException(status_code=404, detail="PDF file no longer exists")

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"extracted_data_{job_id[:8]}.pdf",
    )
