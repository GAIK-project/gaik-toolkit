"""Pipeline endpoints for diary and incident report generation."""

import tempfile
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from implementation_layer.api.config import get_openai_config, settings
from implementation_layer.api.dependencies import verify_api_key
from implementation_layer.api.schemas.pipeline import DiaryResponse, IncidentReportResponse
from implementation_layer.api.utils import temp_file, validate_file_size, validate_upload

router = APIRouter()

# PDF storage (in production, use proper storage like S3)
PDF_STORAGE: dict[str, Path] = {}

# Default Finnish construction diary requirements
DEFAULT_DIARY_REQUIREMENTS = """
The task is to extract all the required fields needed for the official Työmaapäiväkirja (daily construction site diary)
from the transcript of an audio recorded by a construction site supervisor who verbally describes the day's events on the
worksite.
Output MUST follow the field structure below exactly, using Finnish field names.
If the transcript does not mention a field, return an empty string ("").
All the extracted fields should be as brief as possible, not exceeding a few key words.

Fields to Extract (in Finnish)
Extract the following fields exactly as they appear below:
1. Kohde [Subject of the diary]
2. Laatija [Name of the author recording the diary]
3. Sää [e.g., 3 °C, 2 m/s, 78 % suht. kosteus]
4. Päivämäärä [Format: dd.mm.yyyy]
5. Resurssit - Henkilöstö [e.g., Työnjohtajat: 2 hlö, Työntekijät: 1 hlö, Alihankkijat: 4 hlö, Yhteensä: 7 hlö]
6. Työviikko [Week number, e.g., 2]
7. Päivän työt (Omat työt) [List all works]
8. Päivän tapahtumat [e.g., Ei tapahtumia]
9. Liitteet [number of attachments]
10. Valvojan huomiot
11. Päivän poikkeamat
12. Aloitetut työvaiheet
13. Käynnissä olevat työvai
14. Päättyneet työvai
15. Keskeytyneet työvai
16. Pyydetyt lisäajat
17. Tehdyt katselmukset
18. Valvojan huomautukset
19. Valvojan allekirjoitus
20. Vastaavan allekirjoitus
"""

# Default incident report requirements
DEFAULT_INCIDENT_REQUIREMENTS = """
Extract the following from the incident report:
- Incident date and time
- Location of incident
- Brief description of what happened
- People involved (names, roles if mentioned)
- Injuries or damages reported
- Immediate actions taken
- Witness information (if any)
"""


@router.post(
    "/diary",
    response_model=DiaryResponse,
    dependencies=[Depends(verify_api_key)],
    summary="Generate construction site diary from audio",
    description="Transcribe audio and extract structured Finnish construction diary fields.",
)
async def create_diary(
    file: UploadFile = File(..., description="Audio file of site supervisor report"),
    generate_pdf: bool = Form(default=True, description="Generate PDF diary document"),
    enhanced: bool = Form(default=True, description="Enhance transcript with LLM"),
    custom_requirements: str | None = Form(
        default=None, description="Custom extraction requirements"
    ),
):
    """
    Generate a construction site diary from audio recording.

    Uses Finnish Työmaapäiväkirja format with 20 standardized fields.
    """
    job_id = str(uuid.uuid4())
    suffix = validate_upload(file, settings.ALLOWED_AUDIO_EXTENSIONS)

    content = await file.read()
    validate_file_size(content)

    with temp_file(content, suffix) as tmp_path:
        try:
            config = get_openai_config()

            from gaik.software_modules.audio_to_structured_data import (
                AudioToStructuredData,
            )

            pipeline = AudioToStructuredData(api_config=config)
            result = pipeline.run(
                file_path=tmp_path,
                user_requirements=custom_requirements or DEFAULT_DIARY_REQUIREMENTS,
                transcriber_ctor={"enhanced_transcript": enhanced},
            )

            response = DiaryResponse(
                job_id=job_id,
                raw_transcript=result.transcription.raw_transcript,
                enhanced_transcript=result.transcription.enhanced_transcript,
                extracted_data=result.extracted_fields[0] if result.extracted_fields else None,
            )

            # Generate PDF if requested
            if generate_pdf and result.extracted_fields:
                from implementation_layer.api.utils.diary_pdf import generate_diary_pdf

                pdf_buffer = generate_diary_pdf(
                    extraction_data=result.extracted_fields[0],
                    logo_path=None,
                )
                pdf_path = Path(tempfile.gettempdir()) / f"{job_id}.pdf"
                pdf_path.write_bytes(pdf_buffer.getvalue())
                PDF_STORAGE[job_id] = pdf_path
                response.pdf_available = True

            return response

        except ImportError as e:
            raise HTTPException(
                status_code=500, detail=f"Required components not installed: {e}"
            ) from e
        except Exception as e:
            return DiaryResponse(
                job_id=job_id,
                error=str(e),
            )


@router.post(
    "/incident-report",
    response_model=IncidentReportResponse,
    dependencies=[Depends(verify_api_key)],
    summary="Generate incident report from audio, text, or document",
    description="Extract structured incident details from various input types.",
)
async def create_incident_report(
    file: UploadFile | None = File(default=None, description="Audio or document file"),
    text: str | None = Form(default=None, description="Text description of incident"),
    generate_pdf: bool = Form(default=False, description="Generate PDF report"),
    enhanced: bool = Form(default=True, description="Enhance transcript (audio only)"),
    parser_type: Literal["auto", "pymupdf", "docx", "vision"] = Form(default="auto"),
    custom_requirements: str | None = Form(
        default=None, description="Custom extraction requirements"
    ),
):
    """
    Generate an incident report from audio, text, or document input.

    Provide either:
    - `file`: Audio file (.mp3, .wav, etc.) or document (.pdf, .docx)
    - `text`: Direct text description of the incident
    """
    job_id = str(uuid.uuid4())
    user_requirements = custom_requirements or DEFAULT_INCIDENT_REQUIREMENTS

    # Determine input type
    if text and text.strip():
        return await _process_text_incident(job_id, text, user_requirements, generate_pdf)
    elif file:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Filename is required")
        suffix = Path(file.filename).suffix.lower()
        if suffix in settings.ALLOWED_AUDIO_EXTENSIONS:
            return await _process_audio_incident(
                job_id, file, suffix, user_requirements, enhanced, generate_pdf
            )
        elif suffix in settings.ALLOWED_DOC_EXTENSIONS:
            return await _process_document_incident(
                job_id, file, suffix, user_requirements, parser_type, generate_pdf
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {suffix}. Use audio or document formats.",
            )
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either 'file' (audio/document) or 'text' input.",
        )


async def _process_text_incident(
    job_id: str, text: str, requirements: str, generate_pdf: bool
) -> IncidentReportResponse:
    """Process text input for incident report."""
    try:
        config = get_openai_config()

        from gaik.software_components.extractor.extractor import DataExtractor
        from gaik.software_components.extractor.schema import SchemaGenerator

        generator = SchemaGenerator(config=config)
        schema = generator.generate_schema(requirements)

        extractor = DataExtractor(config=config)
        extracted_data = extractor.extract(
            extraction_model=schema,
            requirements=generator.item_requirements,
            user_requirements=requirements,
            documents=[text],
        )

        response = IncidentReportResponse(
            job_id=job_id,
            input_type="text",
            input_text=text,
            extracted_data=extracted_data,
        )

        if generate_pdf and extracted_data:
            _generate_incident_pdf(job_id, extracted_data)
            response.pdf_available = True

        return response

    except ImportError as e:
        raise HTTPException(
            status_code=500, detail=f"Required components not installed: {e}"
        ) from e
    except Exception as e:
        return IncidentReportResponse(
            job_id=job_id,
            input_type="text",
            error=str(e),
        )


async def _process_audio_incident(
    job_id: str,
    file: UploadFile,
    suffix: str,
    requirements: str,
    enhanced: bool,
    generate_pdf: bool,
) -> IncidentReportResponse:
    """Process audio input for incident report."""
    content = await file.read()
    validate_file_size(content)

    with temp_file(content, suffix) as tmp_path:
        try:
            config = get_openai_config()

            from gaik.software_modules.audio_to_structured_data import (
                AudioToStructuredData,
            )

            pipeline = AudioToStructuredData(api_config=config)
            result = pipeline.run(
                file_path=tmp_path,
                user_requirements=requirements,
                transcriber_ctor={"enhanced_transcript": enhanced},
            )

            response = IncidentReportResponse(
                job_id=job_id,
                input_type="audio",
                raw_transcript=result.transcription.raw_transcript,
                enhanced_transcript=result.transcription.enhanced_transcript,
                extracted_data=result.extracted_fields,
            )

            if generate_pdf and result.extracted_fields:
                _generate_incident_pdf(job_id, result.extracted_fields)
                response.pdf_available = True

            return response

        except ImportError as e:
            raise HTTPException(
                status_code=500, detail=f"Required components not installed: {e}"
            ) from e
        except Exception as e:
            return IncidentReportResponse(
                job_id=job_id,
                input_type="audio",
                error=str(e),
            )


async def _process_document_incident(
    job_id: str,
    file: UploadFile,
    suffix: str,
    requirements: str,
    parser_type: str,
    generate_pdf: bool,
) -> IncidentReportResponse:
    """Process document input for incident report."""
    content = await file.read()
    validate_file_size(content)

    with temp_file(content, suffix) as tmp_path:
        try:
            config = get_openai_config()

            from gaik.software_modules.documents_to_structured_data import (
                DocumentsToStructuredData,
            )

            # Map parser type
            parser_map = {
                "auto": "pymupdf" if suffix == ".pdf" else "docx",
                "pymupdf": "pymupdf",
                "docx": "docx",
                "vision": "vision_parser",
            }

            pipeline = DocumentsToStructuredData(api_config=config)
            result = pipeline.run(
                file_path=tmp_path,
                user_requirements=requirements,
                parser_choice=parser_map.get(parser_type, "pymupdf"),
            )

            response = IncidentReportResponse(
                job_id=job_id,
                input_type="document",
                parsed_content=result.parsed_documents[0] if result.parsed_documents else None,
                extracted_data=result.extracted_fields,
            )

            if generate_pdf and result.extracted_fields:
                _generate_incident_pdf(job_id, result.extracted_fields)
                response.pdf_available = True

            return response

        except ImportError as e:
            raise HTTPException(
                status_code=500, detail=f"Required components not installed: {e}"
            ) from e
        except Exception as e:
            return IncidentReportResponse(
                job_id=job_id,
                input_type="document",
                error=str(e),
            )


def _generate_incident_pdf(job_id: str, data: list[dict]) -> None:
    """Generate PDF for incident report."""
    from implementation_layer.api.utils.pdf_generator import StructuredDataToPDF

    pdf_generator = StructuredDataToPDF(title="Incident Report")
    pdf_path = Path(tempfile.gettempdir()) / f"{job_id}.pdf"
    pdf_generator.run(data, pdf_path)
    PDF_STORAGE[job_id] = pdf_path


@router.get(
    "/pdf/{job_id}",
    summary="Download generated PDF",
    description="Download a previously generated PDF by job ID.",
)
async def download_pdf(job_id: str):
    """Download generated PDF by job ID."""
    if job_id not in PDF_STORAGE:
        raise HTTPException(status_code=404, detail="PDF not found")

    pdf_path = PDF_STORAGE[job_id]
    if not pdf_path.exists():
        del PDF_STORAGE[job_id]
        raise HTTPException(status_code=404, detail="PDF file no longer exists")

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"report_{job_id[:8]}.pdf",
    )
