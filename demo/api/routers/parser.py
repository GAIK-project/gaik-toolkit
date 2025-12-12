"""Parser router - Document parsing endpoints"""

import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter()


@router.post("/")
async def parse_document(
    file: UploadFile = File(...),
    parser_type: Literal["auto", "pymupdf", "docx", "vision"] = "auto",
):
    """
    Parse a document (PDF or DOCX) and extract text content.

    - **file**: The document file to parse
    - **parser_type**: Parser to use (auto, pymupdf, docx, vision)
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    suffix = Path(file.filename).suffix.lower()

    if suffix not in [".pdf", ".docx"]:
        raise HTTPException(
            status_code=400, detail=f"Unsupported file type: {suffix}. Use PDF or DOCX."
        )

    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Auto-detect parser type
        if parser_type == "auto":
            parser_type = "docx" if suffix == ".docx" else "pymupdf"

        if parser_type == "docx":
            from gaik.building_blocks.parsers import DocxParser

            parser = DocxParser()
            result = parser.parse_document(tmp_path)
        elif parser_type == "pymupdf":
            from gaik.building_blocks.parsers import PyMuPDFParser

            parser = PyMuPDFParser()
            result = parser.parse_document(tmp_path)
        elif parser_type == "vision":
            # Vision parser requires OpenAI config
            raise HTTPException(
                status_code=501,
                detail="Vision parser requires OpenAI API key configuration",
            )
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

