# Knowledge Extraction Using Dynamic Schema Generation

Extract structured data from documents using natural language requirements. Automatically generates Pydantic schemas and validates extracted data.

## Features

- **Natural Language → Schema**: Describe extraction needs in plain English
- **Auto Structure Detection**: Automatically detects flat vs nested data patterns
- **Type-Safe Extraction**: Pydantic validation with structured outputs
- **Modular Architecture**: Separate schema generation and data extraction

## Installation

```bash
# Install the package in editable mode (for development)
pip install -e .

# Or install from source
pip install .

# Configure environment
cp .env.example .env
# Edit .env with your API keys
```

## Configuration

Create a `.env` file with your credentials:

```env
# Azure OpenAI
AZURE_API_KEY=your_azure_key_here

# Standard OpenAI (alternative)
OPENAI_API_KEY=your_openai_key_here
```

## Quick Start

### Basic Extraction

```python
from extractors import get_openai_config, SchemaGenerator, DataExtractor

# Step 1: Configure OpenAI client (choose Azure or standard OpenAI)
config = get_openai_config(use_azure=True)  # Set to False for standard OpenAI

# Step 2: Generate schema from requirements
generator = SchemaGenerator(config=config)

requirements = """
Extract project information:
- Project title (string)
- Budget in EUR (decimal)
- Start date (date)
- Status (enum: active or completed)
"""

schema = generator.generate_schema(user_requirements=requirements)

# Step 3: Extract data using the generated schema
extractor = DataExtractor(config=config)

documents = [
    """
    Project: AI Research Initiative
    Budget: 2,500,000 EUR
    Start Date: 2024-01-15
    Status: Active
    """
]

results = extractor.extract(
    extraction_model=schema,
    requirements=generator.item_requirements,
    user_requirements=requirements,
    documents=documents
)

print(results)
```

Here, `schema` is the dynamic Pydantic model class that `SchemaGenerator` produced (for the sample prompt it includes fields like `project_title`, `project_acronym`, etc.), while `generator.item_requirements` is the structured `ExtractionRequirements` metadata describing those fields (each `FieldSpec` stores the name, type, enum, and required flag). The extractor uses the schema to validate the LLM output and uses the requirements to normalize values (e.g., convert dates to ISO, split list fields) in the final result.

### With JSON Export

```python
# Extract and save to JSON in one step
results = extractor.extract(
    extraction_model=schema,
    requirements=generator.item_requirements,
    user_requirements=requirements,
    documents=documents,
    save_json=True,
    json_path="extraction_results.json"
)
```

### PDF Processing With LLM-Based Vision Parsing

```python
from extractors import get_openai_config
from extractors.parsers import VisionParser

# Configure parser
config = get_openai_config(use_azure=True)
parser = VisionParser(
    openai_config=config,
    use_context=True,      # Use previous page context for better continuity
    dpi=300,               # Image resolution (200-300 recommended)
    clean_output=True      # Merge and clean tables across pages
)

# Parse PDF to markdown
markdown_pages = parser.convert_pdf("input/document.pdf")
parser.save_markdown(markdown_pages, "output/document.md")

# Use markdown as extraction input
results = extractor.extract(
    extraction_model=schema,
    requirements=generator.item_requirements,
    user_requirements=requirements,
    documents=markdown_pages  # Use parsed markdown
)
```

## API Providers

### Azure OpenAI

```python
from extractors import get_openai_config

# Default configuration
config = get_openai_config(use_azure=True)

# All classes use the same config
generator = SchemaGenerator(config=config)
extractor = DataExtractor(config=config)
parser = VisionParser(openai_config=config)
```

Configuration includes:
- Deployment: `gpt-4.1`
- Endpoint: Configured in `extraction_config.py`
- API Version: `2024-12-01-preview`

### Standard OpenAI

```python
from extractors import get_openai_config, SchemaGenerator, DataExtractor
from extractors.parsers import VisionParser

# Switch to standard OpenAI
config = get_openai_config(use_azure=False)

# All classes use the same config
generator = SchemaGenerator(config=config)
extractor = DataExtractor(config=config)
parser = VisionParser(openai_config=config)
```

Configuration includes:
- Model: `gpt-4.1-2025-04-14`
- Uses standard OpenAI API

### Custom Models

```python
# Override model for specific component
generator = SchemaGenerator(config=config, model="gpt-4.1-2025-04-14")
extractor = DataExtractor(config=config, model="gpt-4.1-2025-04-14")
```

## Project Structure

```
extractors/
├── pyproject.toml            # Package configuration
├── README.md                 # Documentation
├── requirements.txt          # Dependencies (legacy)
├── src/
│   └── extractors/           # Main package
│       ├── __init__.py       # Package exports
│       ├── config.py         # Shared OpenAI configuration
│       ├── schema.py         # Dynamic schema generation
│       ├── extractor.py      # Data extraction engine
│       └── parsers/          # Document parsers
│           ├── __init__.py   # Parser exports
│           ├── vision.py     # PDF → Markdown (PyMuPDF + Vision API)
│           ├── pymupdf.py    # Fast text-based PDF parser
│           ├── docling.py    # Alternative parser (optional)
│           └── docx.py       # Word document parser (optional)
├── examples/                 # Usage examples + generated assets
│   ├── extraction_example_1.py  # Basic extraction example
│   ├── extraction_example_2.py  # Nest/hierarchical extraction with document classification
│   ├── extraction_example_3.py  # Manual schema + requirements
│   ├── extraction_example_4.py  # Persist and reload generated schema
└── input/                    # Input documents
```

## Core Classes

### SchemaGenerator

Generates Pydantic schemas from natural language requirements.

```python
from extractors import get_openai_config, SchemaGenerator

config = get_openai_config(use_azure=True)
generator = SchemaGenerator(config=config)

# Generate schema
schema = generator.generate_schema(
    user_requirements="Extract: name (string), age (int), email (string)"
)

# Access generated components
print(generator.extraction_model)      # Pydantic model
print(generator.item_requirements)     # Field specifications
print(generator.structure_analysis)    # Flat vs nested detection
```

### DataExtractor

Extracts structured data using pre-generated schemas.

```python
from extractors import get_openai_config, DataExtractor

config = get_openai_config(use_azure=True)
extractor = DataExtractor(config=config)

# Extract data
results = extractor.extract(
    extraction_model=schema,           # From SchemaGenerator
    requirements=requirements,         # Field specifications
    user_requirements=requirements_text,
    documents=["doc1", "doc2"],
    save_json=True,                    # Optional JSON export
    json_path="results.json"
)
```

### VisionParser

Converts PDFs to markdown using Vision API.

```python
from extractors import get_openai_config
from extractors.parsers import VisionParser

config = get_openai_config(use_azure=True)
parser = VisionParser(
    openai_config=config,
    use_context=True,
    dpi=300,
    clean_output=True
)

markdown_pages = parser.convert_pdf("document.pdf")
```

## Key Concepts

### User Requirements

Describe extraction needs in plain English:

```python
requirements = """
For each invoice item, extract:
- Item number (string)
- Description (string)
- Quantity (integer)
- Unit price (decimal)
- Total (decimal)
"""
```

### Structure Detection

The system automatically detects:
- **Flat**: One record per document (e.g., invoice header)
  ```
  Extract: invoice_number, total, date
  ```
- **Nested**: Multiple items per document (e.g., invoice line items)
  ```
  Extract items from invoice:
  - item_number
  - description
  - quantity
  ```

### Field Types

Supported types:
- `str` - Text strings
- `int` - Integers
- `float` - Floating point numbers
- `decimal` - Precise decimal numbers
- `bool` - Boolean values
- `date` - Date strings (auto-converted to ISO format)
- `list[str]` - Lists of strings
- `list[dict]` - Nested structures

### Field Validation

```python
requirements = """
Extract:
- Email (string, pattern: ^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$)
- Status (enum: draft, pending, approved, rejected)
- Amount (decimal, format: currency-eur)
- Date (date, format: iso-date)
- Required field (required: true)
- Optional field (required: false)
"""
```

## Complete Workflow

```python
from extractors import get_openai_config, SchemaGenerator, DataExtractor
from extractors.parsers import VisionParser

# 1. Configure (once for all components)
config = get_openai_config(use_azure=True)

# 2. Parse PDF documents
parser = VisionParser(openai_config=config, dpi=300, clean_output=True)
markdown_docs = parser.convert_pdf("invoice.pdf")

# 3. Generate extraction schema
generator = SchemaGenerator(config=config)
schema = generator.generate_schema(
    user_requirements="""
    Extract invoice line items:
    - Item number (string)
    - Description (string)
    - Quantity (int)
    - Unit price (decimal)
    - Total (decimal)
    """
)

### Schema Persistence & Manual Models

- Start from **examples/extraction_example_3.py** when you want a fixed, handwritten Pydantic schema plus the matching `ExtractionRequirements`.
- Use **examples/extraction_example_4.py** to see how to serialize a generated schema (Python module + JSON requirements) and reload it later without rerunning SchemaGenerator.

## Examples

Complete examples available in the `examples/` folder:
- **examples/extraction_example_1.py** – Basic schema generation and extraction
- **examples/extraction_example_2.py** – Complete PO+BOM matching pipeline
- **examples/extraction_example_3.py** – Manual schema + requirements without SchemaGenerator
- **examples/extraction_example_4.py** – Generate, save (code + JSON), and reload schemas
- **extractor.py** – Production-ready PO+BOM pipeline with PDF parsing

Run examples:
```bash
# Basic extraction example
python examples/extraction_example_1.py

# Complete PO+BOM example
python examples/extraction_example_2.py

# Production pipeline
python extractor.py
```

