"""Classifier router - Document classification endpoints"""

import os
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

router = APIRouter()


class ClassifyRequest(BaseModel):
    classes: list[str]
    parser: Literal["pymupdf", "docx", "vision"] | None = None


@router.post("/")
async def classify_document(
    file: UploadFile = File(...),
    classes: str = "invoice,receipt,contract,report",
    parser: Literal["auto", "pymupdf", "docx"] = "auto",
):
    """
    Classify a document into predefined categories.

    - **file**: The document file to classify
    - **classes**: Comma-separated list of possible classes
    - **parser**: Parser to use for text extraction
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Check for OpenAI API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY environment variable not set",
        )

    suffix = Path(file.filename).suffix.lower()

    if suffix not in [".pdf", ".docx", ".png", ".jpg", ".jpeg"]:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}",
        )

    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from gaik.building_blocks.doc_classifier import DocumentClassifier, get_openai_config

        config = get_openai_config(use_azure=False)  # Use standard OpenAI
        config["api_key"] = api_key  # Override with provided key
        classifier = DocumentClassifier(config)

        class_list = [c.strip() for c in classes.split(",")]

        # Auto-detect parser
        parser_to_use = None
        if parser != "auto":
            parser_to_use = parser
        elif suffix == ".docx":
            parser_to_use = "docx"

        results = classifier.classify(
            file_or_dir=tmp_path,
            classes=class_list,
            parser=parser_to_use,
        )

        # Get result for our file
        filename = Path(tmp_path).name
        result = results.get(filename, {})

        return {
            "filename": file.filename,
            "classification": result.get("class", "unknown"),
            "confidence": result.get("confidence", 0.0),
            "reasoning": result.get("reasoning", ""),
        }

    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Classifier not installed: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        Path(tmp_path).unlink(missing_ok=True)

