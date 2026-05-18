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
- CompositeExtractionRequirements: Parent + child extraction requirements
- StructureAnalysis: Nested vs flat structure analysis
- create_extraction_model: Create Pydantic model from requirements
"""

from gaik.software_components.config import create_openai_client, get_openai_config

from .extractor import DataExtractor, ExtractionResult, save_to_json
from .schema import (
    ChildRequirements,
    CompositeExtractionRequirements,
    ExtractionRequirements,
    FieldSpec,
    SchemaGenerationResult,
    SchemaGenerator,
    StructureAnalysis,
    create_extraction_model,
    normalize_extracted_data,
    parse_date,
)

__all__ = [
    # Main API
    "SchemaGenerator",
    "DataExtractor",
    "ExtractionResult",
    "SchemaGenerationResult",
    # Configuration
    "get_openai_config",
    "create_openai_client",
    # Advanced - for custom schemas
    "FieldSpec",
    "ExtractionRequirements",
    "ChildRequirements",
    "CompositeExtractionRequirements",
    "StructureAnalysis",
    "create_extraction_model",
    # Utilities
    "save_to_json",
    "parse_date",
    "normalize_extracted_data",
]

__version__ = "0.1.0"
