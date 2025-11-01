# GAIK - General AI Kit

**Reusable AI/ML components for Python**

GAIK is a modular toolkit providing production-ready AI/ML utilities. Currently featuring dynamic schema extraction with OpenAI's structured outputs.

> **⚠️ Requirements:** This package requires an [OpenAI API key](https://platform.openai.com/api-keys). Set it as an environment variable: `export OPENAI_API_KEY='sk-...'`

## Features

### 🔍 Dynamic Schema Extraction (`gaik.schema`)

Extract structured data from unstructured text using dynamically created schemas:

- ✅ **Guaranteed structure** - OpenAI API enforces exact schema compliance
- ✅ **Type-safe** - Full Pydantic validation, no parsing errors
- ✅ **No code generation** - Uses Pydantic's `create_model()`, no `eval()` needed
- ✅ **Cost-effective** - Minimal API calls and tokens
- ✅ **Simple & clean** - Easy to understand codebase, minimal dependencies
- ✅ **Clear errors** - Helpful error messages guide you when setup is needed

## Installation

```bash
# Install from Test PyPI
pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ gaik
```

## Quick Start

### 1. Set up your OpenAI API key

```bash
# Get your API key from: https://platform.openai.com/api-keys
export OPENAI_API_KEY='sk-...'
```

### 2. Simple Extraction

```python
from gaik.schema import dynamic_extraction_workflow

# Describe what you want to extract in natural language
description = """
Extract from invoices:
- Invoice number
- Date
- Total amount in USD
- Vendor name
"""

# Your documents
documents = [
    "Invoice #12345\nDate: 2024-01-15\nVendor: Acme Corp\nTotal: $1,500.00",
    "INV-67890\n2024-02-20\nSupplier: TechCo\nAmount: 2,750 USD"
]

# Extract structured data
results = dynamic_extraction_workflow(description, documents)

# Results are dictionaries with guaranteed structure
for result in results:
    print(f"Invoice: {result['invoice_number']}")
    print(f"Amount: ${result['total_amount']}")
```

### Reusable Extractor (Recommended for Multiple Batches)

```python
from gaik.schema import SchemaExtractor

# Create extractor once
extractor = SchemaExtractor("""
Extract from project reports:
- Project title
- Lead institution
- Total funding in euros
- List of partner countries
- Status (ongoing or completed)
""")

# Reuse for multiple document batches
batch1_results = extractor.extract(documents_batch1)
batch2_results = extractor.extract(documents_batch2)

# Inspect the schema
print(f"Extracting fields: {extractor.field_names}")
# Output: ['project_title', 'lead_institution', 'total_funding', ...]
```

### Advanced: Custom Field Specifications

```python
from gaik.schema import (
    FieldSpec,
    ExtractionRequirements,
    SchemaExtractor
)

# Define exact field specifications with custom extraction logic
custom_fields = [
    FieldSpec(
        field_name="invoice_number",
        field_type="str",
        description="Extract invoice ID. Look for 'Invoice #', 'INV-', or similar",
        required=True
    ),
    FieldSpec(
        field_name="amount_usd",
        field_type="float",
        description="Total in USD. Convert EUR (×1.1) and GBP (×1.25) if needed",
        required=True
    ),
    FieldSpec(
        field_name="payment_terms",
        field_type="str",
        description="Payment terms if mentioned (e.g., 'Net 30')",
        required=False
    )
]

# Create requirements
requirements = ExtractionRequirements(
    use_case_name="Invoice",
    fields=custom_fields
)

# Use with extractor
extractor = SchemaExtractor("", requirements=requirements)
results = extractor.extract(documents)
```

## Why Structured Outputs?

### Traditional Approach (Unreliable)
```python
# ❌ Hope it returns valid JSON
# ❌ Manually parse and validate
# ❌ Handle type errors and format issues
response = client.chat.completions.create(
    messages=[{"role": "user", "content": "Extract as JSON..."}]
)
```

### Structured Outputs (Guaranteed)
```python
# ✅ API enforces schema
# ✅ Already validated
# ✅ Type-safe results
response = client.beta.chat.completions.parse(
    response_format=YourPydanticModel
)
```

## How It Works

1. **Describe** what you want to extract in natural language
2. **LLM parses** the description into field specifications
3. **Pydantic creates** a dynamic schema from those specs
4. **Structured extraction** runs with guaranteed output format

```python
# 1. Natural language input
"Extract project title, budget in euros, and partner countries"

# 2. System creates schema dynamically
ProjectExtraction = create_model(
    "ProjectExtraction",
    title=(str, Field(description="Project title")),
    budget=(float, Field(description="Budget in euros")),
    partners=(list[str], Field(description="Partner countries"))
)

# 3. Extract with guaranteed structure
results = extractor.extract(documents)
```

## Field Descriptions = Extraction Instructions

The `description` field in each FieldSpec tells the LLM **how** to extract and format data:

```python
FieldSpec(
    field_name="budget",
    field_type="float",
    description="Budget in USD, convert from any currency mentioned"
)
```

**No complex prompts needed!** The schema handles all instructions.

## API Reference

### `dynamic_extraction_workflow(user_description, documents, *, client=None, verbose=False)`

Complete workflow from natural language to structured extraction.

**Parameters:**
- `user_description` (str): Natural language description of what to extract
- `documents` (list[str]): List of document texts
- `client` (OpenAI, optional): OpenAI client instance
- `verbose` (bool): Print progress information

**Returns:** `list[dict]` - Extracted data as dictionaries

---

### `SchemaExtractor(user_description, *, client=None, requirements=None)`

Reusable extractor for processing multiple document batches.

**Parameters:**
- `user_description` (str): Natural language description
- `client` (OpenAI, optional): OpenAI client instance
- `requirements` (ExtractionRequirements, optional): Pre-defined field specs

**Methods:**
- `.extract(documents)` → `list[dict]` - Extract from multiple documents
- `.extract_one(document)` → `dict` - Extract from single document
- `.field_names` → `list[str]` - List of field names
- `.fields` → `list[FieldSpec]` - Field specifications

---

### `FieldSpec`

Specification for a single extraction field.

**Attributes:**
- `field_name` (str): Snake_case field name
- `field_type` (Literal): One of "str", "int", "float", "bool", "list[str]"
- `description` (str): What to extract and how
- `required` (bool): Whether field is required

---

### `ExtractionRequirements`

Collection of field specifications.

**Attributes:**
- `use_case_name` (str): Name for this extraction use case
- `fields` (list[FieldSpec]): List of field specifications

## Environment Setup

Set your OpenAI API key:

```bash
export OPENAI_API_KEY="sk-..."
```

Or use a `.env` file with `python-dotenv` (optional):

```env
OPENAI_API_KEY=sk-...
```

## Development

```bash
# Clone the repository
git clone https://github.com/GAIK-project/toolkit-shared-components
cd toolkit-shared-components/gaik-py

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
ruff format .

# Lint
ruff check .
```

## Coming Soon

- Document parsing utilities (PDF, HTML, Markdown)
- Logging helpers
- More AI/ML utilities

## Resources

- [OpenAI Structured Outputs Guide](https://platform.openai.com/docs/guides/structured-outputs)
- [Pydantic Dynamic Models](https://docs.pydantic.dev/latest/concepts/models/#dynamic-model-creation)
- [GitHub Repository](https://github.com/GAIK-project/toolkit-shared-components)

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

Contributions welcome! Please open an issue or submit a pull request.
