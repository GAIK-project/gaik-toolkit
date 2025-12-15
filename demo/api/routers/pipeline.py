"""Pipeline router - End-to-end pipeline endpoints for demos."""

import os
import tempfile
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter()

# Temporary storage for generated PDFs
PDF_STORAGE: dict[str, Path] = {}


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


def _get_api_config():
    """Get OpenAI configuration from environment."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY environment variable not set",
        )

    from gaik.building_blocks.config import get_openai_config

    config = get_openai_config(use_azure=False)
    config["api_key"] = api_key
    return config


@router.post("/audio", response_model=AudioPipelineResponse)
async def audio_pipeline(
    file: UploadFile = File(...),
    user_requirements: str = Form(...),
    generate_pdf: bool = Form(False),
    enhanced: bool = Form(True),
    compress_audio: bool = Form(True),
):
    """
    Run the complete audio pipeline: Transcribe -> Extract -> (PDF).

    - **file**: Audio/video file (mp3, wav, mp4, m4a, etc.)
    - **user_requirements**: What data to extract from the transcript
    - **generate_pdf**: Whether to generate a PDF report
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

    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        config = _get_api_config()

        # Step 2: Transcribe
        steps[1].status = "in_progress"

        from gaik.software_components.audio_to_structured_data import AudioToStructuredData

        pipeline = AudioToStructuredData(api_config=config)

        result = pipeline.run(
            file_path=tmp_path,
            user_requirements=user_requirements,
            transcriber_ctor={
                "enhanced_transcript": enhanced,
                "compress_audio": compress_audio,
            },
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
        if generate_pdf and result.extracted_fields:
            try:
                steps[3].status = "in_progress"

                from utils.pdf_generator import StructuredDataToPDF

                pdf_generator = StructuredDataToPDF(title="Extracted Data Report")
                pdf_path = Path(tempfile.gettempdir()) / f"{job_id}.pdf"
                pdf_generator.run(result.extracted_fields, pdf_path)

                PDF_STORAGE[job_id] = pdf_path
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
    parser_type: Literal["auto", "pymupdf", "docx", "vision"] = Form("auto"),
    generate_pdf: bool = Form(False),
):
    """
    Run the complete document pipeline: Parse -> Extract -> (PDF).

    - **file**: Document file (PDF, DOCX)
    - **user_requirements**: What data to extract from the document
    - **parser_type**: Parser to use (auto, pymupdf, docx, vision)
    - **generate_pdf**: Whether to generate a PDF report
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
    if suffix not in [".pdf", ".docx"]:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}. Use PDF or DOCX.",
        )

    # Auto-detect parser type
    if parser_type == "auto":
        parser_type = "docx" if suffix == ".docx" else "pymupdf"

    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        config = _get_api_config()

        # Step 2: Parse
        steps[1].status = "in_progress"

        from gaik.software_components.documents_to_structured_data import (
            DocumentsToStructuredData,
        )

        # Map parser_type to pipeline parser_choice
        parser_map = {
            "pymupdf": "pymupdf",
            "docx": "docx",
            "vision": "vision_parser",
        }
        parser_choice = parser_map.get(parser_type, "pymupdf")

        pipeline = DocumentsToStructuredData(api_config=config)

        result = pipeline.run(
            file_path=tmp_path,
            user_requirements=user_requirements,
            parser_choice=parser_choice,
        )

        steps[1].status = "completed"
        steps[1].message = "Document parsed"

        # Step 3: Extract (already done by pipeline.run)
        steps[2].status = "completed"
        steps[2].message = f"Extracted {len(result.extracted_fields)} items"

        # Get parsed content
        parsed_content = (
            result.parsed_documents[0] if result.parsed_documents else None
        )

        response = DocumentPipelineResponse(
            job_id=job_id,
            steps=steps,
            parsed_content=parsed_content,
            extracted_data=result.extracted_fields,
        )

        # Step 4: Generate PDF if requested
        if generate_pdf and result.extracted_fields:
            try:
                steps[3].status = "in_progress"

                from utils.pdf_generator import StructuredDataToPDF

                pdf_generator = StructuredDataToPDF(title="Extracted Data Report")
                pdf_path = Path(tempfile.gettempdir()) / f"{job_id}.pdf"
                pdf_generator.run(result.extracted_fields, pdf_path)

                PDF_STORAGE[job_id] = pdf_path
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
