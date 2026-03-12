"""Parser router - Document parsing endpoints"""

import os
import tempfile
from pathlib import Path
from typing import Literal

try:
    from utils import validate_file_size
except ImportError:
    from api.utils import validate_file_size
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

router = APIRouter()


@router.post("")
async def parse_document(
    file: UploadFile = File(...),
    parser_type: Literal["auto", "pymupdf", "docx", "vision", "vision_plus", "docling_api"] = Form(
        "auto"
    ),
):
    """
    Parse a document (PDF, DOCX, or image) and extract text content.

    - **file**: The document or image file to parse
    - **parser_type**: Parser to use (auto, pymupdf, docx, vision, vision_plus)
    """
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

    # Validate file size and save temporarily
    content = await validate_file_size(file)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Auto-detect parser type
        if parser_type == "auto":
            if suffix == ".docx":
                parser_type = "docx"
            elif suffix in supported_images:
                parser_type = "vision"
            else:
                parser_type = "pymupdf"

        if parser_type == "docx":
            from gaik.software_components.parsers import DocxParser

            parser = DocxParser()
            result = parser.parse_document(tmp_path)
        elif parser_type == "pymupdf":
            from gaik.software_components.parsers import PyMuPDFParser

            parser = PyMuPDFParser()
            result = parser.parse_document(tmp_path)
        elif parser_type == "vision":
            from gaik.software_components.config import get_openai_config
            from gaik.software_components.parsers import VisionParser

            openai_config = get_openai_config(use_azure=bool(os.getenv("AZURE_API_KEY")))
            parser = VisionParser(openai_config=openai_config)
            # VisionParser uses convert_pdf() which returns list of markdown pages
            markdown_pages = parser.convert_pdf(tmp_path)
            result = {"text_content": "\n\n".join(markdown_pages), "metadata": {}}
        elif parser_type == "vision_plus":
            from gaik.software_components.config import get_openai_config
            from gaik.software_components.RAG.rag_parser_vision import VisionRagParser

            vision_config = get_openai_config(use_azure=bool(os.getenv("AZURE_API_KEY")))
            parser = VisionRagParser(
                vision_config=vision_config,
                verbose=False,
                save_markdown=False,
                enable_ocr=False,
                enable_table_structure=True,
                enable_formula_enrichment=False,
            )
            # Convert to markdown (we don't need the chunks)
            markdown, _chunks = parser.convert_doc_to_chunks_with_vision(
                tmp_path, return_markdown=True
            )
            result = {"text_content": markdown, "metadata": {"parser": "vision_plus"}}
        elif parser_type == "docling_api":
            from gaik.software_components.parsers.docling_api_client import DoclingApiClientParser

            api_base = os.getenv("DOCLING_API_BASE")
            password = os.getenv("DOCLING_API_PASSWORD")
            if not api_base or not password:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Docling API not configured "
                        "(DOCLING_API_BASE / DOCLING_API_PASSWORD missing)"
                    ),
                )
            parser = DoclingApiClientParser(api_base=api_base, password=password)
            result_raw = parser.parse_document(tmp_path)
            result = {
                "text_content": result_raw.get("parsed_markdown", ""),
                "metadata": {
                    **result_raw.get("metadata", {}),
                    "source_file": result_raw.get("source_file", ""),
                    "elapsed_seconds": result_raw.get("elapsed_seconds"),
                    "parser": "docling_api",
                },
            }
        else:
            raise HTTPException(status_code=400, detail=f"Unknown parser: {parser_type}")

        return {
            "filename": file.filename,
            "parser": parser_type,
            "text_content": result.get("text_content", ""),
            "metadata": result.get("metadata", {}),
        }

    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Parser not installed: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        # Cleanup temp file
        Path(tmp_path).unlink(missing_ok=True)
