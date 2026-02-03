"""Diary router - Construction diary (Työmaapäiväkirja) workflow endpoints."""

import tempfile
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
try:
    from utils import get_api_config, sse_event
except ImportError:
    from api.utils import get_api_config, sse_event
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

router = APIRouter()


# Temporary storage for generated PDFs
PDF_STORAGE: dict[str, Path] = {}

# Logo path for PDF generation (use GAIK logo)
LOGO_PATH = Path(__file__).parent.parent.parent / "public" / "logos" / "gaik-logo-letter-only.png"

# Finnish construction diary extraction requirements
DIARY_REQUIREMENTS = """Extract the following fields from the Finnish construction diary:
(Työmaapäiväkirja)
- Kohde (Project/Subject)
- Laatija (Author name)
- Päivämäärä (Date in dd.mm.yyyy format)
- Työviikko (Week number)
- Sää (Weather conditions: temperature, wind, humidity)
- Resurssit - Henkilöstö (Personnel: supervisors, workers, subcontractors, total)
- Päivän työt (Omat työt) (Day's work tasks - list all)
- Päivän tapahtumat (Day's events)
- Liitteet (Attachments: number and type)
- Valvojan huomiot (Supervisor's observations)
- Päivän poikkeamat (Day's deviations/exceptions)
- Aloitetut työvaiheet (Started work phases - list)
- Käynnissä olevat työvaiheet (Ongoing work phases - list)
- Päättyneet työvaiheet (Completed work phases - list)
- Keskeytyneet työvaiheet (Interrupted work phases - list)
- Pyydetyt lisäajat (Requested extensions)
- Tehdyt katselmukset (Completed inspections)
- Valvojan huomautukset (Supervisor's remarks)
- Valvojan allekirjoitus (Supervisor's signature)
- Vastaavan allekirjoitus (Responsible person's signature)"""


@router.post("/audio/stream")
async def diary_audio_pipeline_stream(
    file: UploadFile = File(...),
    generate_pdf: bool = Form(True),
    enhanced: bool = Form(True),
    compress_audio: bool = Form(True),
):
    """
    Process audio recording with SSE streaming progress updates.

    Returns Server-Sent Events with progress updates and final result.
    """
    job_id = str(uuid.uuid4())

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
            import io
            from contextlib import redirect_stdout

            from gaik.software_components.extractor import DataExtractor, SchemaGenerator
            from gaik.software_components.extractor.schema import print_pydantic_schema
            from gaik.software_components.transcriber import Transcriber

            config = get_api_config()

            # Step 1: Transcription
            steps[0]["status"] = "in_progress"
            steps[0]["message"] = "Converting audio to text..."
            yield sse_event("step_update", steps[0])

            transcriber = Transcriber(
                api_config=config,
                enhanced_transcript=enhanced,
                compress_audio=compress_audio,
            )
            transcription = transcriber.transcribe(file_path=tmp_path)

            steps[0]["status"] = "completed"
            steps[0]["message"] = "Transcription complete"
            yield sse_event("step_update", steps[0])

            # Step 2: Schema Generation (capture reasoning output)
            steps[1]["status"] = "in_progress"
            steps[1]["message"] = "Analyzing requirements..."
            yield sse_event("step_update", steps[1])

            reasoning_buffer = io.StringIO()
            with redirect_stdout(reasoning_buffer):
                schema_generator = SchemaGenerator(config=config)
                extraction_model = schema_generator.generate_schema(DIARY_REQUIREMENTS)
            reasoning_output = reasoning_buffer.getvalue()

            steps[1]["status"] = "completed"
            yield sse_event("step_update", steps[1])

            # Step 3: Data Extraction
            steps[2]["status"] = "in_progress"
            steps[2]["message"] = "Extracting diary data..."
            yield sse_event("step_update", steps[2])

            documents = [transcription.enhanced_transcript or transcription.raw_transcript]
            extractor = DataExtractor(config=config)
            extracted_data = extractor.extract(
                extraction_model=extraction_model,
                requirements=schema_generator.item_requirements,
                user_requirements=DIARY_REQUIREMENTS,
                documents=documents,
            )

            # Capture schema for UI display
            schema_buffer = io.StringIO()
            with redirect_stdout(schema_buffer):
                print_pydantic_schema(extraction_model, title="Generated Extraction Schema")
            schema_str = schema_buffer.getvalue()

            steps[2]["status"] = "completed"
            steps[2]["message"] = f"Extracted {len(extracted_data)} items"
            steps[2]["details"] = {
                "type": "schema",
                "title": "Generated Pydantic Schema",
                "content": reasoning_output + "\n" + schema_str,  # Include reasoning!
            }
            yield sse_event("step_update", steps[2])

            # Step 4: Generate PDF if requested
            pdf_available = False
            if generate_pdf:
                pdf_step_idx = 3
                steps[pdf_step_idx]["status"] = "in_progress"
                steps[pdf_step_idx]["message"] = "Generating report..."
                yield sse_event("step_update", steps[pdf_step_idx])

                try:
                    from utils.pdf_generator import StructuredDataToPDF

                    logo = LOGO_PATH if LOGO_PATH.exists() else None
                    pdf_generator = StructuredDataToPDF(
                        title="Construction Site Diary", logo_path=logo
                    )
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
async def diary_text_pipeline_stream(
    text: str = Form(...),
    generate_pdf: bool = Form(True),
):
    """
    Extract structured data from text with SSE streaming progress updates.

    Returns Server-Sent Events with progress updates and final result.
    """
    job_id = str(uuid.uuid4())

    async def event_generator() -> AsyncGenerator[str, None]:
        steps = [
            {"step": 1, "name": "Analyzing Text", "status": "pending"},
            {"step": 2, "name": "Schema Generation", "status": "pending"},
            {"step": 3, "name": "Data Extraction", "status": "pending"},
        ]
        if generate_pdf:
            steps.append({"step": 4, "name": "Report Formatting", "status": "pending"})

        # Send initial steps
        yield sse_event("steps", {"steps": steps})

        if not text or not text.strip():
            yield sse_event("error", {"message": "No text provided"})
            return

        try:
            import io
            from contextlib import redirect_stdout

            config = get_api_config()

            # Step 1: Analyzing text
            steps[0]["status"] = "in_progress"
            yield sse_event("step_update", steps[0])

            from gaik.software_components.extractor.extractor import DataExtractor
            from gaik.software_components.extractor.schema import (
                SchemaGenerator,
                print_pydantic_schema,
            )

            steps[0]["status"] = "completed"
            steps[0]["message"] = "Text received"
            yield sse_event("step_update", steps[0])

            # Step 2: Generate schema
            steps[1]["status"] = "in_progress"
            yield sse_event("step_update", steps[1])

            generator = SchemaGenerator(config=config)
            extraction_model = generator.generate_schema(DIARY_REQUIREMENTS)

            # Capture generated schema as string for logging
            schema_buffer = io.StringIO()
            with redirect_stdout(schema_buffer):
                print_pydantic_schema(extraction_model, title="Generated Extraction Schema")
            schema_str = schema_buffer.getvalue()

            steps[1]["status"] = "completed"
            steps[1]["message"] = "Schema generated"
            steps[1]["details"] = {
                "type": "schema",
                "title": "Generated Pydantic Schema",
                "content": schema_str,
            }
            yield sse_event("step_update", steps[1])

            # Step 3: Extract data
            steps[2]["status"] = "in_progress"
            yield sse_event("step_update", steps[2])

            extractor = DataExtractor(config=config)
            extracted_data = extractor.extract(
                extraction_model=extraction_model,
                requirements=generator.item_requirements,
                user_requirements=DIARY_REQUIREMENTS,
                documents=[text],
            )

            steps[2]["status"] = "completed"
            steps[2]["message"] = f"Extracted {len(extracted_data)} items"
            yield sse_event("step_update", steps[2])

            # Step 4: Generate PDF if requested
            pdf_available = False
            if generate_pdf:
                pdf_step_idx = 3
                steps[pdf_step_idx]["status"] = "in_progress"
                yield sse_event("step_update", steps[pdf_step_idx])

                try:
                    from utils.pdf_generator import StructuredDataToPDF

                    logo = LOGO_PATH if LOGO_PATH.exists() else None
                    pdf_generator = StructuredDataToPDF(
                        title="Construction Site Diary", logo_path=logo
                    )
                    pdf_path = Path(tempfile.gettempdir()) / f"{job_id}.pdf"

                    pdf_data = extracted_data if extracted_data else [{"input_text": text}]
                    pdf_generator.run(pdf_data, pdf_path)

                    PDF_STORAGE[job_id] = pdf_path
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


@router.get("/pdf/{job_id}")
async def download_diary_pdf(job_id: str):
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
        filename=f"tyomaapaivakira_{job_id[:8]}.pdf",
    )
