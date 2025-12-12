"""
Data Extractor for extracting structured data from documents using generated Pydantic schemas.

This module provides the DataExtractor class for extracting data from documents
using pre-generated Pydantic models.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from gaik.building_blocks.config import create_openai_client

from .schema import (
    SYSTEM_PARSER,
    ExtractionRequirements,
    normalize_extracted_data,
    _parse_with,
)


def save_to_json(results: list[dict], json_path: str) -> None:
    """
    Save extraction results to JSON file.

    Args:
        results: List of extraction results (dicts)
        json_path: Output JSON file path
    """
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"OK Results saved to: {json_path}")


class DataExtractor:
    """
    Extractor for structured data from documents using Pydantic schemas.

    Takes a pre-generated Pydantic model and extracts data from documents
    according to that schema.

    Features:
    - Type-safe extraction with Pydantic validation
    - Data normalization (dates, lists, decimals)
    - Support for Azure OpenAI and OpenAI
    - Optional JSON export

    Usage:
        # Create config once
        config = get_openai_config(use_azure=True)  # or use_azure=False for standard OpenAI

        # Create extractor with config
        extractor = DataExtractor(config=config)

        # Extract data with pre-generated schema
        results = extractor.extract(
            extraction_model=MyPydanticModel,
            requirements=requirements,
            user_requirements="Extract...",
            documents=["doc1", "doc2"]
        )

        # Or extract and save to JSON
        results = extractor.extract(
            extraction_model=MyPydanticModel,
            requirements=requirements,
            user_requirements="Extract...",
            documents=["doc1", "doc2"],
            save_json=True,
            json_path="output.json"
        )
    """

    def __init__(self, config: dict, model: str | None = None):
        """
        Initialize the DataExtractor.

        Args:
            config: OpenAI configuration dict from get_openai_config()
            model: Optional model name override
        """
        self.config = config
        self.model = model if model else self.config["model"]
        self.client = create_openai_client(self.config)

    def extract(
        self,
        extraction_model: type[BaseModel],
        requirements: ExtractionRequirements,
        user_requirements: str,
        documents: list[str],
        save_json: bool = False,
        json_path: str = "extraction_results.json",
    ) -> list[dict]:
        """
        Extract structured data from documents using a pre-generated Pydantic model.

        Args:
            extraction_model: Pre-generated Pydantic model class
            requirements: ExtractionRequirements with field specifications
            user_requirements: Original natural language requirements (for context)
            documents: List of document texts to extract from
            save_json: If True, save results to JSON file
            json_path: Output JSON file path (used if save_json=True)

        Returns:
            List of extraction results (dicts)
        """
        print("\n" + "=" * 80)
        print("EXTRACTION PHASE")
        print("=" * 80)
        results: list[dict] = []

        for i, doc in enumerate(documents, start=1):
            print(f"\nProcessing document {i}/{len(documents)}...")

            messages = [
                {"role": "system", "content": SYSTEM_PARSER},
                {
                    "role": "user",
                    "content": (
                        f"EXTRACTION TASK:\n{user_requirements}\n\nDocument:\n```txt\n{doc}\n```"
                    ),
                },
            ]

            resp = _parse_with(
                client=self.client,
                model=self.model,
                messages=messages,
                response_format=extraction_model,
            )

            if getattr(resp, "usage", None):
                print(f"  [extraction] tokens={resp.usage.total_tokens}")

            parsed = resp.choices[0].message.parsed
            result_dict = parsed.model_dump()

            # Normalize extracted data (dates, lists, etc.)
            if isinstance(result_dict, dict):
                # If nested container exists, normalize each item
                for key, value in list(result_dict.items()):
                    if isinstance(value, list) and value and isinstance(value[0], dict):
                        result_dict[key] = [
                            normalize_extracted_data(item, requirements) for item in value
                        ]
                # Also normalize the flat record itself
                result_dict = normalize_extracted_data(result_dict, requirements)

            results.append(result_dict)

        print(f"\nOK Completed extraction from {len(documents)} document(s)")

        # Save to JSON if requested
        if save_json:
            save_to_json(results, json_path)

        return results

