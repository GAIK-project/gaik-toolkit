"""Parse endpoint for document processing."""

import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from api.config import get_openai_config, settings
from api.dependencies import verify_api_key
from api.schemas.parse import ParseResponse
from gaik.building_blocks.parsers import DocxParser, PyMuPDFParser, VisionParser

router = APIRouter()


@router.post(
    "/",
    response_model=ParseResponse,
    dependencies=[Depends(verify_api_key)],
    summary="Parse document",
    description="Parse a PDF or DOCX document and extract text content.",
)
async def parse_document(
    file: UploadFile = File(..., description="Document file (PDF or DOCX)"),
    parser_type: Literal["auto", "pymupdf", "docx", "vision"] = Form(
        default="auto", description="Parser type to use"
    ),
):
    """
    Parse a document (PDF or DOCX) and extract text content.

    - **file**: PDF or DOCX file
    - **parser_type**:
        - auto: Automatically select based on file type
        - pymupdf: Fast local PDF parsing
        - docx: Word document parsing
        - vision: LLM-based PDF to Markdown (requires OpenAI)

    Returns extracted text content and metadata.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    # Validate file extension
    suffix = Path(file.filename).suffix.lower()
    if suffix not in settings.ALLOWED_DOC_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {suffix}. Allowed: {settings.ALLOWED_DOC_EXTENSIONS}",
        )

    # Read and validate file size
    content = await file.read()
    if len(content) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {settings.MAX_FILE_SIZE_MB}MB",
        )

    # Save to temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Auto-select parser based on file type
        actual_parser = parser_type
        if parser_type == "auto":
            actual_parser = "docx" if suffix == ".docx" else "pymupdf"

        text_content = ""
        metadata: dict = {}

        if actual_parser == "docx":
            parser = DocxParser()
            result = parser.parse_document(tmp_path)
            text_content = result.get("text_content", "")
            metadata = result.get("metadata", {})

        elif actual_parser == "pymupdf":
            parser = PyMuPDFParser()
            result = parser.parse_document(tmp_path)
            text_content = result.get("text_content", "")
            metadata = result.get("metadata", {})

        elif actual_parser == "vision":
            config = get_openai_config()
            # VisionParser expects OpenAIConfig object or dict
            openai_config = {
                "api_key": config["api_key"],
                "model": config["model"],
                "use_azure": config["use_azure"],
            }
            if config["use_azure"]:
                openai_config["azure_endpoint"] = config["azure_endpoint"]
                openai_config["api_version"] = config["api_version"]

            parser = VisionParser(openai_config=openai_config)
            pages = parser.convert_pdf(tmp_path, clean_output=True)
            text_content = "\n\n".join(pages)
            metadata = {"pages": len(pages), "parser": "vision"}

        else:
            raise HTTPException(status_code=400, detail=f"Unknown parser type: {parser_type}")

        # Add word count to metadata
        metadata["word_count"] = len(text_content.split())

        return ParseResponse(
            filename=file.filename,
            parser=actual_parser,
            text_content=text_content,
            metadata=metadata,
        )

    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Parser not available. Required dependencies missing.",
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Parsing failed")
    finally:
        # Clean up temporary file
        Path(tmp_path).unlink(missing_ok=True)
