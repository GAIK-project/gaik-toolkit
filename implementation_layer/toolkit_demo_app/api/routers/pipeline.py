"""Pipeline router - End-to-end pipeline endpoints for demos."""

import asyncio
import logging
import os
import tempfile
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

try:
    from utils import (
        AUDIO_TOO_LARGE_DETAIL,
        MAX_AUDIO_FILE_SIZE_BYTES,
        MAX_FILE_SIZE_BYTES,
        MAX_FILE_SIZE_MB,
        get_api_config,
        get_model_options,
        load_schema,
        save_schema,
        sse_event,
        validate_audio_file_size,
        validate_file_size,
        validate_vision_page_limit,
        wrap_schema_with_numeric_normalizers,
    )
    from utils.field_names import (
        field_name_mapping,
        rename_described_fields,
        rename_keys,
    )
    from utils.schema_view import schema_summary
    from utils.session_schemas import (
        find_session_schema,
        shorten_schema_name,
        store_session_schema,
    )
except ImportError:
    from api.utils import (
        AUDIO_TOO_LARGE_DETAIL,
        MAX_AUDIO_FILE_SIZE_BYTES,
        MAX_FILE_SIZE_BYTES,
        MAX_FILE_SIZE_MB,
        get_api_config,
        get_model_options,
        load_schema,
        save_schema,
        sse_event,
        validate_audio_file_size,
        validate_file_size,
        validate_vision_page_limit,
        wrap_schema_with_numeric_normalizers,
    )
    from api.utils.field_names import (
        field_name_mapping,
        rename_described_fields,
        rename_keys,
    )
    from api.utils.schema_view import schema_summary
    from api.utils.session_schemas import (
        find_session_schema,
        shorten_schema_name,
        store_session_schema,
    )
try:
    from routers.parser import run_parser
except ImportError:
    from api.routers.parser import run_parser
try:
    from routers.transcriber import (
        _build_diff_chunks,
        _categorize_fallback_reason,
        _summarize_corrections,
    )
except ImportError:
    from api.routers.transcriber import (
        _build_diff_chunks,
        _categorize_fallback_reason,
        _summarize_corrections,
    )
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

PDF_CLEANUP_AFTER_HOURS = 1

# Temporary storage for generated PDFs (path and creation time)
PDF_STORAGE: dict[str, Path] = {}
PDF_TIMESTAMPS: dict[str, datetime] = {}


def _parse_document_content(tmp_path: str, suffix: str, parser_type: str, config: dict):
    validate_vision_page_limit(tmp_path, suffix, parser_type)

    if parser_type == "vision":
        from gaik.software_components.parsers import VisionParser

        parser = VisionParser(openai_config=config, **get_model_options(config))
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
                from gaik.software_components.parsers.docling_api_client import (
                    DoclingApiClientParser,
                )

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


def _get_or_create_schema(
    config,
    user_requirements: str,
    schema_key: str | None,
    regenerate_schema: bool,
    schema_id: str | None = None,
):
    from gaik.software_components.extractor.schema import SchemaGenerator

    if schema_id:
        entry = find_session_schema(schema_id, user_requirements)
        return entry.schema, entry.requirements, False

    loaded = None
    if schema_key:
        loaded = load_schema(schema_key, user_requirements)
        if loaded is not None and not regenerate_schema:
            logger.info("Loaded existing schema for key %s", schema_key)
            schema, requirements = loaded
            return schema, requirements, False

    generator = SchemaGenerator(config=config, model=config["model"], **get_model_options(config))
    schema = generator.generate_schema(user_requirements)
    requirements = generator.item_requirements

    if schema_key and loaded is None and not regenerate_schema:
        save_schema(schema, requirements, schema_key, user_requirements)
        logger.info("Saved schema for key %s", schema_key)

    return wrap_schema_with_numeric_normalizers(schema), requirements, True


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
    content = await validate_audio_file_size(file)
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
    parser_type: Literal["auto", "pymupdf", "docx", "vision", "vision_plus", "docling_api"] = Form(
        "docling_api"
    ),
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

        extractor = DataExtractor(config=config, model=config["model"], **get_model_options(config))
        extracted_data = extractor.extract(
            extraction_model=extraction_model,
            requirements=requirements,
            user_requirements=user_requirements,
            documents=[parsed_content],
        )
        # The generator drops letters such as ä and ö from field names: put them back.
        extracted_data = rename_keys(
            extracted_data, field_name_mapping(extraction_model, user_requirements)
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

                # Use extracted_data if available, otherwise create from parsed content
                pdf_data = (
                    extracted_data
                    if extracted_data
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
        extractor = DataExtractor(config=config, model=config["model"], **get_model_options(config))
        extracted_data = extractor.extract(
            extraction_model=extraction_model,
            requirements=requirements,
            user_requirements=user_requirements,
            documents=[text],
        )
        # The generator drops letters such as ä and ö from field names: put them back.
        extracted_data = rename_keys(
            extracted_data, field_name_mapping(extraction_model, user_requirements)
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
    schema_id: str | None = Form(None),
    # Transcription options, the same as the Transcriber demo's. All optional, so that
    # the other demos that call this endpoint are unchanged.
    language: str = Form("auto"),
    diarization: bool = Form(False),
    speaker_count: int | None = Form(None),
    min_speakers: int | None = Form(None),
    max_speakers: int | None = Form(None),
    custom_context: str = Form(""),
    fix_transcription_errors: bool = Form(False),
    prefer_local_first: bool = Form(True),
):
    """
    Run the audio pipeline with SSE streaming progress updates.

    Returns Server-Sent Events with progress updates and final result.
    """
    enhanced = enhanced or fix_transcription_errors
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
    if len(content) > MAX_AUDIO_FILE_SIZE_BYTES:

        async def error_gen() -> AsyncGenerator[str, None]:
            yield sse_event("error", {"message": AUDIO_TOO_LARGE_DETAIL})

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

            local_api_base = os.getenv("LOCAL_TRANSCRIBER_API_BASE")
            local_api_key = os.getenv("LOCAL_TRANSCRIBER_API_KEY")

            transcriber_kwargs = {
                "api_config": config,
                "output_dir": tempfile.gettempdir(),
                "enhanced_transcript": enhanced,
                "compress_audio": compress_audio,
                "language": language,
                "diarization": diarization,
                "speaker_count": speaker_count,
                "min_speakers": min_speakers,
                "max_speakers": max_speakers,
                "initial_prompt": custom_context.strip() or None,
                "local_api_base": local_api_base,
                "local_api_key": local_api_key,
            }

            # The provider calls run in a worker thread: a long recording must not stall
            # the event loop, and with it every other request.
            def transcribe_with(**extra):
                return Transcriber(**transcriber_kwargs, **extra).transcribe(
                    file_path=tmp_path, custom_context=custom_context
                )

            used_fallback = False
            fallback_reason = None
            cloud_model = config.get("transcription_model", "whisper")
            model_used = cloud_model
            transcribe_started = time.monotonic()
            if prefer_local_first and local_api_base and local_api_key:
                try:
                    transcription = await asyncio.to_thread(
                        transcribe_with, transcription_model="whisper_local"
                    )
                    model_used = "whisper_local"
                except Exception as exc:
                    logger.warning("Local transcription failed: %s — falling back", exc)
                    used_fallback = True
                    fallback_reason = _categorize_fallback_reason(exc)
                    transcription = await asyncio.to_thread(transcribe_with)
            else:
                transcription = await asyncio.to_thread(transcribe_with)
            transcribe_seconds = time.monotonic() - transcribe_started

            corrected_transcript = None
            correction_summary = None
            diff_chunks = None
            if fix_transcription_errors and transcription.enhanced_transcript:
                corrected_transcript = transcription.enhanced_transcript
                correction_summary = _summarize_corrections(
                    transcription.raw_transcript, corrected_transcript
                ).model_dump()
                diff_chunks = [
                    chunk.model_dump()
                    for chunk in _build_diff_chunks(
                        transcription.raw_transcript, corrected_transcript
                    )
                ]

            steps[0]["status"] = "completed"
            steps[0]["message"] = "Transcription complete"
            yield sse_event("step_update", steps[0])

            # Step 2: Schema Generation
            steps[1]["status"] = "in_progress"
            steps[1]["message"] = "Analyzing requirements..."
            yield sse_event("step_update", steps[1])

            from gaik.software_components.extractor import DataExtractor

            # A schema made earlier in this session for exactly this task is reused: the
            # schema is made again only when the task changes (or the server forgot it).
            reuse_id = schema_id
            if reuse_id:
                try:
                    find_session_schema(reuse_id, user_requirements)
                except ValueError:
                    reuse_id = None
            schema_started = time.monotonic()
            extraction_model, requirements, generated_new_schema = await asyncio.to_thread(
                _get_or_create_schema,
                config=config,
                user_requirements=user_requirements,
                schema_key=schema_key,
                regenerate_schema=regenerate_schema,
                schema_id=reuse_id,
            )
            schema_seconds = time.monotonic() - schema_started
            if generated_new_schema:
                schema_source = "generated"
                if not schema_key:
                    reuse_id = store_session_schema(
                        user_requirements, extraction_model, requirements
                    )
            else:
                schema_source = "reused" if reuse_id else "saved"
            # The schema itself, for people: every field with its plain type and rule.
            summary = schema_summary(extraction_model, requirements, user_requirements)

            steps[1]["status"] = "completed"
            steps[1]["message"] = {
                "generated": "Generated new schema",
                "reused": "Reused the schema of the earlier run",
                "saved": "Loaded saved schema",
            }[schema_source]
            yield sse_event("step_update", steps[1])

            # Step 3: Data Extraction
            steps[2]["status"] = "in_progress"
            steps[2]["message"] = "Extracting the data..."
            yield sse_event("step_update", steps[2])

            documents = [transcription.enhanced_transcript or transcription.raw_transcript]
            extractor = DataExtractor(
                config=config, model=config["model"], **get_model_options(config)
            )
            extract_started = time.monotonic()
            extracted_data = await asyncio.to_thread(
                extractor.extract,
                extraction_model=extraction_model,
                requirements=requirements,
                user_requirements=user_requirements,
                documents=documents,
            )
            extract_seconds = time.monotonic() - extract_started
            # The generator drops letters such as ä and ö from field names: put them back.
            extracted_data = rename_keys(
                extracted_data, field_name_mapping(extraction_model, user_requirements)
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
                    # What the Transcriber demo shows, so that its view can be reused.
                    "corrected_transcript": corrected_transcript,
                    "correction_summary": correction_summary,
                    "diff_chunks": diff_chunks,
                    "segments": transcription.segments or None,
                    "used_fallback": used_fallback,
                    "fallback_reason": fallback_reason,
                    "transcription_model": model_used,
                    "audio_duration_s": transcription.audio_duration_s,
                    "duration_s": transcription.duration_s,
                    "srt_content": transcription.srt_content,
                    "vtt_content": transcription.vtt_content,
                    "usage": transcription.usage or None,
                    # The schema, how it was got, and how long each step took.
                    **summary,
                    "schema_source": schema_source,
                    # To send with the next run of the same task, so that it is not made again.
                    "schema_id": reuse_id if schema_source != "saved" else None,
                    "timings": {
                        "transcription_s": round(transcribe_seconds, 1),
                        "schema_s": round(schema_seconds, 1),
                        "extraction_s": round(extract_seconds, 1),
                    },
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
    schema_id: str | None = Form(None),
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
                schema_id=schema_id,
            )

            steps[0]["status"] = "completed"
            steps[0]["message"] = (
                "Generated new schema" if generated_new_schema else "Loaded saved schema"
            )
            yield sse_event("step_update", steps[0])

            # Step 2: Extract data
            steps[1]["status"] = "in_progress"
            yield sse_event("step_update", steps[1])

            extractor = DataExtractor(
                config=config, model=config["model"], **get_model_options(config)
            )
            extracted_data = extractor.extract(
                extraction_model=extraction_model,
                requirements=requirements,
                user_requirements=user_requirements,
                documents=[text],
            )
            # The generator drops letters such as ä and ö from field names: put them back.
            extracted_data = rename_keys(
                extracted_data, field_name_mapping(extraction_model, user_requirements)
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
    parser_type: Literal[
        "auto", "pymupdf", "docx", "vision", "vision_plus", "docling_api", "multimodal"
    ] = Form("docling_api"),
    generate_pdf: bool = Form(False),
    pdf_title: str = Form("Extracted Data Report"),
    schema_key: str | None = Form(None),
    regenerate_schema: bool = Form(False),
    schema_id: str | None = Form(None),
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

    file_name = file.filename

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

            # The same parsers, run the same way, as in the Parser demo. A model or a remote
            # service reads the file in a worker thread, so that it cannot stall the event loop.
            parse_started = time.monotonic()
            parsed = await run_parser(tmp_path, suffix, actual_parser_type)
            parse_seconds = time.monotonic() - parse_started
            temp_name = Path(tmp_path).name
            parsed_content = (parsed.get("text_content") or "").replace(temp_name, file_name)
            if not parsed_content.strip():
                raise ValueError("The parser found no text in the document. Try another parser.")
            parsed_html = parsed.get("html")

            steps[0]["status"] = "completed"
            steps[0]["message"] = "Document parsed"
            yield sse_event("step_update", steps[0])

            # Step 2: Schema Generation
            steps[1]["status"] = "in_progress"
            steps[1]["message"] = "Analyzing requirements..."
            yield sse_event("step_update", steps[1])

            from gaik.software_components.extractor import DataExtractor

            # A schema made earlier in this session for exactly this task is reused: the
            # schema is made again only when the task changes (or the server forgot it).
            reuse_id = schema_id
            if reuse_id:
                try:
                    find_session_schema(reuse_id, user_requirements)
                except ValueError:
                    reuse_id = None
            schema_started = time.monotonic()
            extraction_model, requirements, generated_new_schema = await asyncio.to_thread(
                _get_or_create_schema,
                config=config,
                user_requirements=user_requirements,
                schema_key=schema_key,
                regenerate_schema=regenerate_schema,
                schema_id=reuse_id,
            )
            schema_seconds = time.monotonic() - schema_started
            if generated_new_schema:
                schema_source = "generated"
                if not schema_key:
                    reuse_id = store_session_schema(
                        user_requirements, extraction_model, requirements
                    )
            else:
                schema_source = "reused" if reuse_id else "saved"
            summary = schema_summary(extraction_model, requirements, user_requirements)

            steps[1]["status"] = "completed"
            steps[1]["message"] = {
                "generated": "Generated new schema",
                "reused": "Reused the schema of the earlier run",
                "saved": "Loaded saved schema",
            }[schema_source]
            yield sse_event("step_update", steps[1])

            # Step 3: Data Extraction
            steps[2]["status"] = "in_progress"
            steps[2]["message"] = "Extracting structured data..."
            yield sse_event("step_update", steps[2])

            extractor = DataExtractor(
                config=config, model=config["model"], **get_model_options(config)
            )
            extract_started = time.monotonic()
            extracted_data = await asyncio.to_thread(
                extractor.extract,
                extraction_model=extraction_model,
                requirements=requirements,
                user_requirements=user_requirements,
                documents=[parsed_content],
            )
            extract_seconds = time.monotonic() - extract_started
            # The generator drops letters such as ä and ö from field names: put them back.
            extracted_data = rename_keys(
                extracted_data, field_name_mapping(extraction_model, user_requirements)
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
                    # The parsed file as the parser shows it, and what it said about itself.
                    "parser": actual_parser_type,
                    "parsed_html": parsed_html,
                    "parse_metadata": parsed.get("metadata") or {},
                    # The schema, how it was got, and how long each step took.
                    **summary,
                    "schema_source": schema_source,
                    # To send with the next run of the same task, so that it is not made again.
                    "schema_id": reuse_id if schema_source != "saved" else None,
                    "timings": {
                        "parse_s": round(parse_seconds, 1),
                        "schema_s": round(schema_seconds, 1),
                        "extraction_s": round(extract_seconds, 1),
                    },
                },
            )

        except ImportError as e:
            yield sse_event("error", {"message": f"Required components not installed: {e}"})
        except Exception as e:
            # A parser reports its problems as HTTP errors: show the reason, not the status.
            message = str(e.detail) if isinstance(e, HTTPException) else str(e)
            for step in steps:
                if step["status"] == "in_progress":
                    step["status"] = "error"
                    step["message"] = message
                    yield sse_event("step_update", step)
                    break
            yield sse_event("error", {"message": message})
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


MAX_SCHEMA_PROMPT_CHARS = 4000


@router.post("/schema")
async def generate_session_schema(user_requirements: str = Form(...)):
    """Generate a schema for this session from a prompt, to be reused by the stream endpoints.

    The schema lives in memory only and is not saved.
    """
    prompt = user_requirements.strip()
    if len(prompt) < 10:
        raise HTTPException(400, "Write what to extract first.")
    if len(prompt) > MAX_SCHEMA_PROMPT_CHARS:
        raise HTTPException(400, f"The prompt is limited to {MAX_SCHEMA_PROMPT_CHARS} characters.")

    try:
        from gaik.software_components.extractor.schema import SchemaGenerator
    except ImportError as e:
        raise HTTPException(503, f"Required components not installed: {e}") from e

    try:
        from routers.luvata_order import describe_schema
    except ImportError:
        from api.routers.luvata_order import describe_schema

    config = get_api_config()

    def generate():
        generator = SchemaGenerator(
            config=config, model=config["model"], **get_model_options(config)
        )
        schema = generator.generate_schema(prompt)
        return schema, generator.item_requirements

    try:
        schema, requirements = await asyncio.to_thread(generate)
    except Exception as e:
        logger.exception("Schema generation failed")
        raise HTTPException(502, "The schema could not be generated. Try again.") from e

    schema = shorten_schema_name(wrap_schema_with_numeric_normalizers(schema))
    return {
        "schema_id": store_session_schema(prompt, schema, requirements),
        "fields": rename_described_fields(
            describe_schema(schema), field_name_mapping(schema, prompt)
        ),
    }


@router.get("/pdf/{job_id}")
async def download_pdf(job_id: str, inline: bool = False):
    """Download a generated PDF by job ID, or show it in the page with ?inline=true."""
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
        content_disposition_type="inline" if inline else "attachment",
    )
