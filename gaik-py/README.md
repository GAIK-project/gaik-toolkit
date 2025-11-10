# GAIK - General AI Kit

**Reusable AI/ML components for Python**

Multi-provider AI toolkit for structured data extraction. Supports OpenAI, Anthropic Claude, Google Gemini, and Azure OpenAI.

## Features

### 🔍 Dynamic Data Extraction (`gaik.extract`)

Extract structured data from unstructured text using LangChain's structured outputs:

- ✅ **Multi-provider** - OpenAI, Anthropic, Azure, Google - easy switching
- ✅ **Guaranteed structure** - API-enforced schema compliance
- ✅ **Type-safe** - Full Pydantic validation
- ✅ **No code generation** - Uses Pydantic's `create_model()`, no `eval()`
- ✅ **Cost-effective** - Minimal API calls
- ✅ **Simple & clean** - Easy to understand, minimal dependencies

### 🖼️ Vision PDF Parsing (`gaik.parsers`)

Convert PDF pages to Markdown with OpenAI or Azure OpenAI vision models:

- ✅ **Single API surface** - Works with standard OpenAI or Azure deployments
- ✅ **Optional extras** - Install with `pip install gaik[vision]`
- ✅ **CLI ready** - See `examples/demo_vision_parser.py` for quick conversions
- ✅ **Table-aware** - Keeps multi-page tables intact with optional cleanup

## Installation

```bash
# From PyPI (production)
pip install gaik

# With optional vision parser support
pip install gaik[vision]
```

## Quick Start

### Extract Data from Text

Set your API key (choose one):

```bash
export OPENAI_API_KEY='sk-...'              # OpenAI (default)
export ANTHROPIC_API_KEY='sk-ant-...'       # Anthropic
export GOOGLE_API_KEY='...'                 # Google
export AZURE_API_KEY='...'                  # Azure
export AZURE_ENDPOINT='https://...'         # Azure (also required)
```

Then extract:

```python
from gaik.extract import SchemaExtractor

# Using default OpenAI provider
extractor = SchemaExtractor("Extract name and age from text")
result = extractor.extract_one("Alice is 25 years old")
print(result)
# {'name': 'Alice', 'age': 25}

# Switch provider
extractor = SchemaExtractor("Extract name and age", provider="anthropic")  # or "google", "azure"
```

### Convert PDF to Markdown

Requires: `pip install gaik[vision]`

Set environment variables first:
```bash
# For Azure OpenAI
export AZURE_API_KEY='...'
export AZURE_ENDPOINT='https://your-resource.openai.azure.com/'
export AZURE_DEPLOYMENT='gpt-4o'  # Your deployment name

# OR for OpenAI
export OPENAI_API_KEY='sk-...'
```

Then convert:
```python
from gaik.parsers import VisionParser, get_openai_config

# Configure
config = get_openai_config(use_azure=True)  # or use_azure=False for OpenAI
parser = VisionParser(config)

# Convert PDF (returns list of pages as Markdown strings)
pages = parser.convert_pdf("invoice.pdf", clean_output=True)

# Combine into single document
markdown = "\n\n".join(pages)
print(markdown)
```

### Batch Extraction

```python
from gaik.extract import dynamic_extraction_workflow

description = """
Extract from invoices:
- Invoice number
- Total amount in USD
- Vendor name
"""

documents = [
    "Invoice #12345 from Acme Corp. Total: $1,500",
    "INV-67890, Supplier: TechCo, Amount: $2,750"
]

# Use any provider
results = dynamic_extraction_workflow(
    description,
    documents,
    provider="openai"  # or "anthropic", "google", "azure"
)

for result in results:
    print(f"Invoice: {result['invoice_number']}, Amount: ${result['total_amount']}")
```

### 4. Reusable Extractor (Recommended)

```python
from gaik.extract import SchemaExtractor

# Create extractor once
extractor = SchemaExtractor("""
Extract from project reports:
- Project title
- Lead institution
- Total funding in euros
- List of partner countries
""")

# Reuse for multiple batches
batch1_results = extractor.extract(documents_batch1)
batch2_results = extractor.extract(documents_batch2)

# Inspect the schema
print(f"Fields: {extractor.field_names}")
# ['project_title', 'lead_institution', 'total_funding', 'partner_countries']
```

### 5. Schema-Only Generation

Generate Pydantic schemas without extraction:

```python
from gaik.extract import FieldSpec, ExtractionRequirements, create_extraction_model

requirements = ExtractionRequirements(
    use_case_name="Invoice",
    fields=[
        FieldSpec(
            field_name="invoice_number",
            field_type="str",
            description="Invoice identifier",
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

# Create Pydantic model
InvoiceModel = create_extraction_model(requirements)
schema = InvoiceModel.model_json_schema()
```

## API Reference

### Extraction API

| Function/Class                  | Purpose                                           |
| ------------------------------- | ------------------------------------------------- |
| `SchemaExtractor`               | Reusable extractor with provider selection        |
| `dynamic_extraction_workflow()` | One-shot extraction from natural language         |
| `create_extraction_model()`     | Generate Pydantic model from field specifications |
| `FieldSpec`                     | Define a single extraction field                  |
| `ExtractionRequirements`        | Collection of field specifications                |

### Vision Parser API

| Function/Class        | Purpose                                    |
| --------------------- | ------------------------------------------ |
| `VisionParser`        | PDF to Markdown converter using vision LLM |
| `get_openai_config()` | Helper to configure OpenAI/Azure API       |
| `OpenAIConfig`        | Configuration dataclass for vision parser  |

### Extraction Parameters

```python
SchemaExtractor(
    user_description: str | None = None,  # Optional if requirements provided
    provider: Literal["openai", "anthropic", "google", "azure"] = "openai",
    model: str | None = None,             # Optional: override default model
    api_key: str | None = None,           # Optional: override env variable
    client: BaseChatModel | None = None,  # Optional: custom LangChain client
    requirements: ExtractionRequirements | None = None  # Optional: pre-defined schema
)
```

### Vision Parser Parameters

```python
VisionParser(config: OpenAIConfig)

get_openai_config(
    use_azure: bool = True,  # True for Azure, False for OpenAI
) -> OpenAIConfig
```

**Environment variables (auto-detected):**

- OpenAI: `OPENAI_API_KEY`
- Azure: `AZURE_API_KEY` + `AZURE_ENDPOINT` + `AZURE_DEPLOYMENT` (optional: `AZURE_API_VERSION`)

## Default Models

| Provider  | Default Model                |
| --------- | ---------------------------- |
| OpenAI    | `gpt-4.1`                    |
| Anthropic | `claude-sonnet-4-5-20250929` |
| Google    | `gemini-2.5-flash`           |
| Azure     | `gpt-4.1` (or your deployment) |

## Resources

- [GitHub Repository](https://github.com/GAIK-project/toolkit-shared-components)
- [Examples Directory](https://github.com/GAIK-project/toolkit-shared-components/tree/main/examples)
- [LangChain Documentation](https://python.langchain.com/docs/how_to/structured_output/)
- [Pydantic Documentation](https://docs.pydantic.dev/)

## License

MIT License - see [LICENSE](LICENSE) file for details.
