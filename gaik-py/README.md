# GAIK - General AI Kit

**Reusable AI/ML components for Python**

GAIK is a modular toolkit providing production-ready AI/ML utilities. Currently featuring dynamic schema extraction with OpenAI's structured outputs.

> **⚠️ Requirements:** This package requires an [OpenAI API key](https://platform.openai.com/api-keys). Set it as an environment variable: `export OPENAI_API_KEY='sk-...'`

## Features

### 🔍 Dynamic Data Extraction (`gaik.extract`)

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
from gaik.extract import dynamic_extraction_workflow

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
from gaik.extract import SchemaExtractor

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

# Access the generated Pydantic model
pydantic_model = extractor.model
json_schema = extractor.model.model_json_schema()
print(json_schema)
```

### 3. Schema-Only Generation (No Extraction)

Sometimes you just want to generate a Pydantic schema without extracting data:

```python
from gaik.extract import FieldSpec, ExtractionRequirements, create_extraction_model

# Define fields manually
requirements = ExtractionRequirements(
    use_case_name="Invoice",
    fields=[
        FieldSpec(
            field_name="invoice_number",
            field_type="str",
            description="The invoice identifier",
            required=True
        ),
        FieldSpec(
            field_name="amount",
            field_type="float",
            description="Total amount",
            required=True
        )
    ]
)

# Create the Pydantic model
InvoiceModel = create_extraction_model(requirements)

# Use it however you want
schema = InvoiceModel.model_json_schema()
instance = InvoiceModel(invoice_number="INV-123", amount=1500.00)
```

**💡 More Examples:** Check out the [examples directory](https://github.com/GAIK-project/toolkit-shared-components/tree/main/examples) for more use cases and patterns.

## API Overview

| Function/Class                  | Purpose                                               |
| ------------------------------- | ----------------------------------------------------- |
| `dynamic_extraction_workflow()` | One-shot extraction from natural language description |
| `SchemaExtractor`               | Reusable extractor for multiple document batches      |
| `create_extraction_model()`     | Generate Pydantic model from field specifications     |
| `FieldSpec`                     | Define a single extraction field                      |
| `ExtractionRequirements`        | Collection of field specifications                    |

See docstrings for detailed parameter information.

## Resources

- [GitHub Repository](https://github.com/GAIK-project/toolkit-shared-components)
- [OpenAI Structured Outputs Guide](https://platform.openai.com/docs/guides/structured-outputs)
- [Pydantic Documentation](https://docs.pydantic.dev/)

## License

MIT License - see [LICENSE](LICENSE) file for details.
