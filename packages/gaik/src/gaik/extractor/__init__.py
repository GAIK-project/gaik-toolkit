"""
Knowledge Extraction Using Dynamic Schema Generation

Extract structured data from documents using natural language requirements.
Automatically generates Pydantic schemas and validates extracted data.

Main Classes:
    - SchemaGenerator: Generate Pydantic schemas from natural language
    - DataExtractor: Extract structured data using generated schemas

Configuration:
    - get_openai_config: Get OpenAI/Azure configuration
    - create_openai_client: Create OpenAI client from config

Advanced (for custom schemas):
    - FieldSpec: Field specification model
    - ExtractionRequirements: Parsed extraction requirements
    - StructureAnalysis: Nested vs flat structure analysis
    - create_extraction_model: Create Pydantic model from requirements
"""

from gaik.config import get_openai_config, create_openai_client
from .schema import (
    SchemaGenerator,
    FieldSpec,
    ExtractionRequirements,
    StructureAnalysis,
    create_extraction_model,
)
from .extractor import DataExtractor, save_to_json

__all__ = [
    # Main API
    "SchemaGenerator",
    "DataExtractor",
    # Configuration
    "get_openai_config",
    "create_openai_client",
    # Advanced - for custom schemas
    "FieldSpec",
    "ExtractionRequirements",
    "StructureAnalysis",
    "create_extraction_model",
    # Utilities
    "save_to_json",
]

__version__ = "0.1.0"
