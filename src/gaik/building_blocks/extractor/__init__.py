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

from gaik.building_blocks.config import create_openai_client, get_openai_config

from .extractor import DataExtractor, save_to_json
from .schema import (
    ExtractionRequirements,
    FieldSpec,
    SchemaGenerator,
    StructureAnalysis,
    create_extraction_model,
    parse_date,
    normalize_extracted_data,
)

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
    "parse_date",
    "normalize_extracted_data",
]

__version__ = "0.1.0"

