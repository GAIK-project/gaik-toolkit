"""Dynamic schema extraction with LangChain structured outputs.

This module provides the main API for extracting structured data from documents
using dynamically created Pydantic schemas and LangChain's structured outputs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, cast

from gaik.extract.models import ExtractionRequirements
from gaik.extract.utils import create_extraction_model
from gaik.providers import get_provider
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

if TYPE_CHECKING:
    from gaik.extract.models import FieldSpec

# Type alias for supported providers
ProviderType = Literal["openai", "anthropic", "google", "azure"]


def _get_llm_client(
    provider: ProviderType = "openai",
    model: str | None = None,
    api_key: str | None = None,
    client: BaseChatModel | None = None,
    **kwargs: Any,
) -> BaseChatModel:
    """Get or create LLM client using provider.

    Args:
        provider: Provider name (e.g., "openai", "anthropic", "azure", "google").
                  Defaults to "openai".
        model: Model name. If None, uses provider's default model.
        api_key: API key for authentication. If None, uses environment variable.
        client: Optional existing LangChain client to return.
        **kwargs: Additional provider-specific parameters.

    Returns:
        BaseChatModel: LangChain chat model instance

    Raises:
        ValueError: If provider is not recognized
    """
    if client is not None:
        return client

    provider_obj = get_provider(provider)
    return provider_obj.create_chat_model(model=model, api_key=api_key, **kwargs)


def _parse_user_requirements(
    user_description: str,
    llm_client: BaseChatModel,
) -> ExtractionRequirements:
    """Parse user's natural language into structured field specifications.

    Uses LangChain's structured outputs to ensure the response matches our schema.

    Args:
        user_description: Natural language description of what to extract
        llm_client: LangChain chat model instance

    Returns:
        Parsed extraction requirements with field specifications
    """
    structured_model = llm_client.with_structured_output(ExtractionRequirements)
    response = structured_model.invoke(user_description)
    return cast(ExtractionRequirements, response)


def _extract_from_document(
    document_text: str,
    extraction_model: type[BaseModel],
    llm_client: BaseChatModel,
) -> BaseModel:
    """Extract structured data from document using structured outputs.

    The schema is enforced by LangChain's structured outputs API.

    Args:
        document_text: The document text to extract data from
        extraction_model: Pydantic model defining the extraction schema
        llm_client: LangChain chat model instance

    Returns:
        Extracted data as a Pydantic model instance
    """
    structured_model = llm_client.with_structured_output(extraction_model)
    response = structured_model.invoke(document_text)
    # LangChain's with_structured_output guarantees BaseModel return
    return cast(BaseModel, response)


class SchemaExtractor:
    """Dynamic schema extractor using LangChain structured outputs.

    This class allows you to define extraction requirements once and reuse them
    across multiple documents. It's more efficient than calling the workflow
    function when processing multiple documents with the same schema.

    Attributes:
        requirements: The parsed extraction requirements
        model: The dynamically created Pydantic model for extraction
        client: LangChain chat model instance

    Example:
        >>> # Using default OpenAI provider
        >>> extractor = SchemaExtractor('''
        ...     Extract from invoices:
        ...     - Invoice number
        ...     - Date
        ...     - Total amount in USD
        ...     - Vendor name
        ... ''')
        >>> results = extractor.extract(documents)

        >>> # Using Anthropic provider
        >>> extractor = SchemaExtractor(
        ...     "Extract name and age",
        ...     provider="anthropic"
        ... )

        >>> # Custom model
        >>> extractor = SchemaExtractor(
        ...     "Extract fields",
        ...     provider="openai",
        ...     model="gpt-4o"
        ... )
    """

    def __init__(
        self,
        user_description: str | None = None,
        *,
        provider: ProviderType = "openai",
        model: str | None = None,
        api_key: str | None = None,
        client: BaseChatModel | None = None,
        requirements: ExtractionRequirements | None = None,
        **kwargs: Any,
    ):
        """Initialize the schema extractor.

        Args:
            user_description: Natural language description of what to extract.
                Required if requirements is not provided.
            provider: Provider name (e.g., "openai", "anthropic", "azure", "google").
                Defaults to "openai".
            model: Model name. If None, uses provider's default model.
            api_key: API key for authentication. If None, uses environment variable.
            client: Optional custom LangChain chat model. If provided, provider,
                model, and api_key are ignored.
            requirements: Optional pre-parsed extraction requirements. If provided,
                user_description is not needed.
            **kwargs: Additional provider-specific parameters.

        Raises:
            ValueError: If neither user_description nor requirements is provided.
        """
        self.client = _get_llm_client(
            provider=provider,
            model=model,
            api_key=api_key,
            client=client,
            **kwargs,
        )

        if requirements is not None:
            self.requirements = requirements
        elif user_description is not None:
            self.requirements = _parse_user_requirements(user_description, self.client)
        else:
            raise ValueError("Either 'user_description' or 'requirements' must be provided")

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
    provider: ProviderType = "openai",
    model: str | None = None,
    api_key: str | None = None,
    client: BaseChatModel | None = None,
    verbose: bool = False,
    **kwargs: Any,
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
        provider: Provider name (e.g., "openai", "anthropic", "azure", "google").
            Defaults to "openai".
        model: Model name. If None, uses provider's default model.
        api_key: API key for authentication. If None, uses environment variable.
        client: Optional custom LangChain chat model. If provided, provider,
            model, and api_key are ignored.
        verbose: If True, prints progress information
        **kwargs: Additional provider-specific parameters.

    Returns:
        List of extracted data as dictionaries

    Example:
        >>> # Using default OpenAI provider
        >>> results = dynamic_extraction_workflow(
        ...     user_description='''
        ...         Extract project title, budget in euros, and partner countries
        ...     ''',
        ...     documents=[doc1, doc2, doc3]
        ... )

        >>> # Using Anthropic provider
        >>> results = dynamic_extraction_workflow(
        ...     user_description="Extract name and age",
        ...     documents=documents,
        ...     provider="anthropic"
        ... )

    Advantages:
        - Reliable: API enforces schema compliance
        - Efficient: Minimal API calls needed
        - Safe: No code execution or eval()
        - Type-safe: Full Pydantic validation
    """
    llm_client = _get_llm_client(
        provider=provider,
        model=model,
        api_key=api_key,
        client=client,
        **kwargs,
    )

    if verbose:
        print("Step 1: Parsing user requirements...")

    requirements = _parse_user_requirements(user_description, llm_client)

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
        extracted = _extract_from_document(doc, extraction_model, llm_client)
        results.append(extracted.model_dump())

    if verbose:
        print(f"[OK] Extracted data from {len(documents)} documents")

    return results


__all__ = ["SchemaExtractor", "dynamic_extraction_workflow"]
