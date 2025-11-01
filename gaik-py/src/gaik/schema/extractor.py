"""Dynamic schema extraction with OpenAI structured outputs.

This module provides the main API for extracting structured data from documents
using dynamically created Pydantic schemas and OpenAI's structured outputs.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from openai import OpenAI, OpenAIError
from pydantic import BaseModel

from gaik.schema.models import ExtractionRequirements
from gaik.schema.utils import create_extraction_model

if TYPE_CHECKING:
    from gaik.schema.models import FieldSpec


def _get_openai_client(client: OpenAI | None = None) -> OpenAI:
    """Get or create OpenAI client with helpful error message.

    Args:
        client: Optional existing client to return

    Returns:
        OpenAI client instance

    Raises:
        ValueError: If no API key is found with instructions
    """
    if client is not None:
        return client

    try:
        return OpenAI()
    except OpenAIError as e:
        if "api_key" in str(e).lower():
            raise ValueError(
                "OpenAI API key not found. Please set it as an environment variable:\n\n"
                "  export OPENAI_API_KEY='sk-...'\n\n"
                "Get your API key from: https://platform.openai.com/api-keys"
            ) from e
        raise


def _parse_user_requirements(
    user_description: str, client: OpenAI | None = None
) -> ExtractionRequirements:
    """Parse user's natural language into structured field specifications.

    Uses OpenAI's structured outputs to ensure the response matches our schema.

    Args:
        user_description: Natural language description of what to extract
        client: Optional OpenAI client instance. Creates new one if not provided.

    Returns:
        Parsed extraction requirements with field specifications
    """
    openai_client = _get_openai_client(client)

    response = openai_client.responses.parse(
        model="gpt-4.1",
        input=[
            {"role": "user", "content": user_description},
        ],
        text_format=ExtractionRequirements,
    )

    return response.output_parsed


def _extract_from_document(
    document_text: str, extraction_model: type[BaseModel], client: OpenAI | None = None
) -> BaseModel:
    """Extract structured data from document using structured outputs.

    The schema is enforced by OpenAI's structured outputs API.

    Args:
        document_text: The document text to extract data from
        extraction_model: Pydantic model defining the extraction schema
        client: Optional OpenAI client instance. Creates new one if not provided.

    Returns:
        Extracted data as a Pydantic model instance
    """
    openai_client = _get_openai_client(client)

    response = openai_client.responses.parse(
        model="gpt-4.1",
        input=[
            {"role": "user", "content": document_text},
        ],
        text_format=extraction_model,
    )

    return response.output_parsed


class SchemaExtractor:
    """Dynamic schema extractor using OpenAI structured outputs.

    This class allows you to define extraction requirements once and reuse them
    across multiple documents. It's more efficient than calling the workflow
    function when processing multiple documents with the same schema.

    Attributes:
        requirements: The parsed extraction requirements
        model: The dynamically created Pydantic model for extraction
        client: OpenAI client instance

    Example:
        >>> extractor = SchemaExtractor('''
        ...     Extract from invoices:
        ...     - Invoice number
        ...     - Date
        ...     - Total amount in USD
        ...     - Vendor name
        ... ''')
        >>> results = extractor.extract(documents)
        >>> # Reuse the same schema for more documents
        >>> more_results = extractor.extract(more_documents)
    """

    def __init__(
        self,
        user_description: str,
        *,
        client: OpenAI | None = None,
        requirements: ExtractionRequirements | None = None,
    ):
        """Initialize the schema extractor.

        Args:
            user_description: Natural language description of what to extract.
                Ignored if requirements is provided.
            client: Optional OpenAI client instance. Creates new one if not provided.
            requirements: Optional pre-parsed extraction requirements. If provided,
                user_description is ignored and no parsing happens.
        """
        self.client = _get_openai_client(client)

        if requirements is not None:
            self.requirements = requirements
        else:
            self.requirements = _parse_user_requirements(user_description, self.client)

        self.model = create_extraction_model(self.requirements)

    @property
    def field_names(self) -> list[str]:
        """Get the list of field names that will be extracted."""
        return [f.field_name for f in self.requirements.fields]

    @property
    def fields(self) -> list[FieldSpec]:
        """Get the field specifications for this extractor."""
        return self.requirements.fields

    def extract(self, documents: list[str]) -> list[dict]:
        """Extract structured data from multiple documents.

        Args:
            documents: List of document texts to extract data from

        Returns:
            List of extracted data as dictionaries
        """
        results = []
        for doc in documents:
            extracted = _extract_from_document(doc, self.model, self.client)
            results.append(extracted.model_dump())
        return results

    def extract_one(self, document: str) -> dict:
        """Extract structured data from a single document.

        Args:
            document: Document text to extract data from

        Returns:
            Extracted data as a dictionary
        """
        extracted = _extract_from_document(document, self.model, self.client)
        return extracted.model_dump()


def dynamic_extraction_workflow(
    user_description: str,
    documents: list[str],
    *,
    client: OpenAI | None = None,
    verbose: bool = False,
) -> list[dict]:
    """Complete workflow from natural language description to structured extraction.

    This is a convenience function that combines all steps:
    1. Parse user requirements into field specifications
    2. Create dynamic Pydantic schema from specifications
    3. Extract data using structured outputs (guaranteed format)

    For better performance when processing multiple batches with the same schema,
    use SchemaExtractor instead.

    Args:
        user_description: Natural language description of what to extract
        documents: List of document texts to extract data from
        client: Optional OpenAI client instance. Creates new one if not provided.
        verbose: If True, prints progress information

    Returns:
        List of extracted data as dictionaries

    Example:
        >>> results = dynamic_extraction_workflow(
        ...     user_description='''
        ...         Extract project title, budget in euros, and partner countries
        ...     ''',
        ...     documents=[doc1, doc2, doc3]
        ... )

    Advantages:
        - Reliable: API enforces schema compliance
        - Efficient: Minimal API calls needed
        - Safe: No code execution or eval()
        - Type-safe: Full Pydantic validation
    """
    client = _get_openai_client(client)

    if verbose:
        print("Step 1: Parsing user requirements...")

    requirements = _parse_user_requirements(user_description, client)

    if verbose:
        print(f"[OK] Identified {len(requirements.fields)} fields to extract")
        print(f"  Fields: {[f.field_name for f in requirements.fields]}")
        print("\nStep 2: Creating dynamic Pydantic schema...")

    extraction_model = create_extraction_model(requirements)

    if verbose:
        print(f"[OK] Created schema: {extraction_model.__name__}")
        print(f"  Schema: {extraction_model.model_json_schema()}")
        print("\nStep 3: Extracting from documents...")

    results = []
    for i, doc in enumerate(documents):
        if verbose:
            print(f"  Processing document {i + 1}/{len(documents)}...")
        extracted = _extract_from_document(doc, extraction_model, client)
        results.append(extracted.model_dump())

    if verbose:
        print(f"[OK] Extracted data from {len(documents)} documents")

    return results


__all__ = ["SchemaExtractor", "dynamic_extraction_workflow"]
