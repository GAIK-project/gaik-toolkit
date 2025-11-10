"""Dynamic structured data extraction with LLM providers.

Extract structured data from unstructured text using Pydantic schemas
and provider-enforced structured outputs (OpenAI, Anthropic, Azure, Google).

Example:
    >>> from gaik.extract import SchemaExtractor
    >>> extractor = SchemaExtractor("Extract name and age")
    >>> results = extractor.extract(["Alice is 25 years old"])
"""

from gaik.extract.extractor import SchemaExtractor, dynamic_extraction_workflow
from gaik.extract.models import ExtractionRequirements, FieldSpec
from gaik.extract.utils import create_extraction_model, sanitize_model_name

__all__ = [
    # Main API
    "SchemaExtractor",
    "dynamic_extraction_workflow",
    # Models
    "FieldSpec",
    "ExtractionRequirements",
    # Utilities
    "create_extraction_model",
    "sanitize_model_name",
]
