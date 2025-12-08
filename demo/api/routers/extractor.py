"""Extractor router - Data extraction endpoints"""

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class ExtractRequest(BaseModel):
    documents: list[str]
    user_requirements: str
    fields: dict[str, str] | None = None


class ExtractResponse(BaseModel):
    results: list[dict]
    document_count: int


@router.post("/", response_model=ExtractResponse)
async def extract_data(request: ExtractRequest):
    """
    Extract structured data from documents using natural language requirements.

    - **documents**: List of document texts to extract from
    - **user_requirements**: Natural language description of what to extract
    - **fields**: Optional field definitions (name -> description)
    """
    # Check for OpenAI API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY environment variable not set",
        )

    if not request.documents:
        raise HTTPException(status_code=400, detail="No documents provided")

    if not request.user_requirements:
        raise HTTPException(status_code=400, detail="No requirements provided")

    try:
        from pydantic import BaseModel as PydanticBaseModel
        from pydantic import create_model

        from gaik.extractor import DataExtractor
        from gaik.extractor.schema import ExtractionRequirements

        config = {"api_key": api_key}
        extractor = DataExtractor(config)

        # Create dynamic extraction model if fields provided
        if request.fields:
            field_definitions = {name: (str | None, None) for name in request.fields.keys()}
            ExtractionModel = create_model("DynamicExtraction", **field_definitions)

            requirements = ExtractionRequirements(
                fields={name: {"description": desc} for name, desc in request.fields.items()}
            )
        else:
            # Use a simple generic model
            ExtractionModel = create_model(
                "GenericExtraction",
                extracted_data=(str | None, None),
            )
            requirements = ExtractionRequirements(
                fields={"extracted_data": {"description": request.user_requirements}}
            )

        results = extractor.extract(
            extraction_model=ExtractionModel,
            requirements=requirements,
            user_requirements=request.user_requirements,
            documents=request.documents,
        )

        return ExtractResponse(
            results=results,
            document_count=len(request.documents),
        )

    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Extractor not installed: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
