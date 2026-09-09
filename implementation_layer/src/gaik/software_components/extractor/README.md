# Extractor

Extract structured data from documents using natural language requirements with automatic Pydantic schema generation.

## Installation

```bash
pip install gaik[extractor]
```

**Note:** Requires OpenAI or Azure OpenAI API access

---

## Quick Start

```python
from gaik.software_components.extractor import SchemaGenerator, DataExtractor, get_openai_config

# Configure
config = get_openai_config(use_azure=True)

# Use settings compatible with models that support reasoning effort.
MODEL = 'gpt-5.6-sol'
MODEL_OPTIONS = {
    'temperature': None,  # Omit temperature from the API request
    'reasoning_effort': 'low',
}

# Generate schema from natural language
generator = SchemaGenerator(config=config, model=MODEL, **MODEL_OPTIONS)
schema = generator.generate_schema(
    user_requirements="Extract: project title (string), budget (decimal), status (enum: active, completed)"
)

# Extract data
extractor = DataExtractor(config=config, model=MODEL, **MODEL_OPTIONS)
results = extractor.extract(
    extraction_model=schema,
    requirements=generator.item_requirements,
    user_requirements="Extract project info",
    documents=["Project: AI Initiative, Budget: EUR2.5M, Status: Active"]
)

print(results)  # [{'project_title': 'AI Initiative', 'budget': 2500000.0, 'status': 'active'}]
```

---

## Features

- **Natural Language -> Schema** - Describe extraction needs in plain English, get Pydantic models
- **Auto Structure Detection** - Automatically detects flat vs nested data patterns
- **Type-Safe Extraction** - Full Pydantic validation with field types, enums, and patterns
- **Multi-Provider** - OpenAI and Azure OpenAI support
- **JSON Export** - Save results to JSON files automatically

---

## Basic API

### SchemaGenerator

```python
from gaik.software_components.extractor import SchemaGenerator

generator = SchemaGenerator(
    config: dict,                         # From get_openai_config()
    model: str | None = None,             # Optional model override
    temperature: float | None = 0.0,      # None omits the parameter
    reasoning_effort: str | None = None,  # e.g. low, medium, or high
)

# Generate schema
schema = generator.generate_schema(user_requirements: str)

# Access components
generator.extraction_model      # Generated Pydantic model
generator.item_requirements     # Field specifications
generator.structure_analysis    # Structure type analysis
```

### DataExtractor

```python
from gaik.software_components.extractor import DataExtractor

extractor = DataExtractor(
    config: dict,                         # From get_openai_config()
    model: str | None = None,             # Optional model override
    temperature: float | None = 0.0,      # None omits the parameter
    reasoning_effort: str | None = None,  # e.g. low, medium, or high
)

# Extract data
results = extractor.extract(
    extraction_model=schema,
    requirements=field_specs,
    user_requirements=requirements_text,
    documents=["doc1", "doc2"],
    save_json=True,            # Optional
    json_path="results.json"   # Optional
)
```

### Configuration

```python
from gaik.software_components.extractor import get_openai_config

# Azure OpenAI (default)
config = get_openai_config(use_azure=True)

# Standard OpenAI
config = get_openai_config(use_azure=False)
```

### Sampling and reasoning compatibility

For reasoning models, pass an active `reasoning_effort` and set
`temperature=None`. This omits `temperature` from the API request instead of
sending JSON `null`. Use the same options for `SchemaGenerator` and
`DataExtractor`:

```python
MODEL = 'gpt-5.6-sol'
MODEL_OPTIONS = {
    'temperature': None,
    'reasoning_effort': 'low',
}

generator = SchemaGenerator(config=config, model=MODEL, **MODEL_OPTIONS)
extractor = DataExtractor(config=config, model=MODEL, **MODEL_OPTIONS)
```

Do not combine an active reasoning effort (`low`, `medium`, or `high`) with
a custom temperature. Supported reasoning-effort values are model-specific;
check the selected model's OpenAI documentation.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_API_KEY` | Azure only | Azure OpenAI API key |
| `AZURE_ENDPOINT` | Azure only | Azure OpenAI endpoint URL |
| `AZURE_DEPLOYMENT` | Azure only | Azure deployment name |
| `OPENAI_API_KEY` | OpenAI only | Standard OpenAI API key |
| `AZURE_API_VERSION` | Optional | API version (default: 2024-02-15-preview) |

---

## Examples

See [implementation_layer/examples/software_components/extractor/](../../../../examples/software_components/extractor/) for complete examples:
- `extraction_example_1.py` - Basic extraction
- `extraction_example_2.py` - Nested/hierarchical extraction
- `extraction_example_3.py` - Manual schema definition
- `extraction_example_4.py` - Schema persistence

---

## Resources

- **Repository**: [github.com/GAIK-project/gaik-toolkit](https://github.com/GAIK-project/gaik-toolkit)
- **Examples**: [implementation_layer/examples/software_components/extractor/](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/examples/software_components/extractor)
- **Contributing**: [CONTRIBUTING.md](../CONTRIBUTING.md)
- **Issues**: [github.com/GAIK-project/gaik-toolkit/issues](https://github.com/GAIK-project/gaik-toolkit/issues)

## License

MIT - see [LICENSE](../LICENSE)

