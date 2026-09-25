"""Classifier router - Document classification endpoints"""

import tempfile
from pathlib import Path
from typing import Literal

try:
    from utils import get_api_config, validate_file_size
except ImportError:
    from api.utils import get_api_config, validate_file_size
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

try:
    from utils.model_settings import provider_error_detail
except ImportError:
    from api.utils.model_settings import provider_error_detail

router = APIRouter()


@router.post("")
async def classify_document(
    file: UploadFile = File(...),
    classes: str = Form("invoice,receipt,contract,report"),
    parser: Literal["auto", "pymupdf", "docx"] = Form("auto"),
):
    """
    Classify a document into predefined categories.

    - **file**: The document file to classify
    - **classes**: Comma-separated list of possible classes
    - **parser**: Parser to use for text extraction
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    suffix = Path(file.filename).suffix.lower()

    if suffix not in [".pdf", ".docx", ".png", ".jpg", ".jpeg"]:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}",
        )

    # Validate file size and save temporarily
    content = await validate_file_size(file)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from gaik.software_components.doc_classifier import DocumentClassifier

        config = get_api_config()
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

        # The component represents a failed provider call as an unknown class.
        # Do not return a remote error body through the regular result response.
        reasoning = result.get("reasoning", "")
        if result.get("class") == "unknown" and reasoning.startswith("Classification error:"):
            reasoning = provider_error_detail(RuntimeError(reasoning))

        return {
            "filename": file.filename,
            "classification": result.get("class", "unknown"),
            "confidence": result.get("confidence", 0.0),
            "reasoning": reasoning,
        }

    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Classifier not installed: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=provider_error_detail(e)) from e
    finally:
        Path(tmp_path).unlink(missing_ok=True)
