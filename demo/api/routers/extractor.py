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


@router.post("", response_model=ExtractResponse)
async def extract_data(request: ExtractRequest):
    """
    Extract structured data from documents using natural language requirements.

    - **documents**: List of document texts to extract from
    - **user_requirements**: Natural language description of what to extract
    - **fields**: Optional field definitions (name -> description)
    """
    # Check for API key (Azure or OpenAI)
    use_azure = bool(os.getenv("AZURE_API_KEY"))
    if not use_azure and not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="Either AZURE_API_KEY or OPENAI_API_KEY environment variable must be set",
        )

    if not request.documents:
        raise HTTPException(status_code=400, detail="No documents provided")

    if not request.user_requirements:
        raise HTTPException(status_code=400, detail="No requirements provided")

    try:
        from pydantic import create_model

        from gaik.building_blocks.extractor import (
            DataExtractor,
            ExtractionRequirements,
            FieldSpec,
            get_openai_config,
        )

        config = get_openai_config(use_azure=use_azure)
        extractor = DataExtractor(config)

        # Create dynamic extraction model if fields provided
        if request.fields:
            field_definitions = {name: (str | None, None) for name in request.fields.keys()}
            ExtractionModel = create_model("DynamicExtraction", **field_definitions)

            # Create proper FieldSpec objects
            field_specs = [
                FieldSpec(
                    field_name=name,
                    field_type="str",
                    description=desc,
                    required=False,
                )
                for name, desc in request.fields.items()
            ]
            requirements = ExtractionRequirements(
                use_case_name="DynamicExtraction",
                fields=field_specs,
            )
        else:
            # Use a simple generic model
            ExtractionModel = create_model(
                "GenericExtraction",
                extracted_data=(str | None, None),
            )
            requirements = ExtractionRequirements(
                use_case_name="GenericExtraction",
                fields=[
                    FieldSpec(
                        field_name="extracted_data",
                        field_type="str",
                        description=request.user_requirements,
                        required=False,
                    )
                ],
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
