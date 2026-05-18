# Vision Extractor

Single-pass PDF/image to structured data extraction using vision-capable LLMs.

`VisionExtractor` combines document parsing and structured extraction in one API call. Instead of first converting a document to Markdown/text and then running a separate extractor, it sends the original PDF/image files directly to a vision LLM, uses the model's reasoning to understand layout and content, and returns schema-conformant structured data validated by Pydantic.

This is different from the standard `extractor` component:

- `extractor` works on text/Markdown that has already been parsed elsewhere.
- `vision_extractor` performs visual document understanding and extraction together.
- `extractor` is efficient when clean text is already available.
- `vision_extractor` is better when parsing quality strongly affects extraction quality.

Use `VisionExtractor` for high-accuracy extraction from documents with complex visual layouts, tables, multi-page structures, scanned/visual forms, or cases where conventional parsing can lose context and misguide extraction. It is especially suitable for tasks where row alignment, table headers, spatial layout, or cross-document visual evidence matter.

## Installation

```bash
pip install "gaik[vision-extract]"
```

**Note:** Requires credentials for at least one supported provider: OpenAI/Azure OpenAI, Claude/Anthropic, or Google Gemini/Vertex AI.

---

## Quick Start

```python
from dotenv import load_dotenv
import json
from gaik.software_components.vision_extractor import VisionExtractor

load_dotenv() #loads .env

extractor = VisionExtractor(
    model_provider="openai",
    model="gpt-5.4-mini",
    use_azure=True,
    reasoning_effort="low",
)

result = extractor.extract(
    file_paths=["purchase_order.pdf"],
    user_requirements="""
    Extract purchase order header fields and line items.

    Header fields:
    - date (DD-MM-YYYY)
    - purchase order number
    - supplier number
    - contact

    Line items:
    - item number
    - complete description
    - quantity (text string showing number with a unit, e.g., 15.75 Kg)
    - price (text string showing number with a unit, e.g., 150,00 USD)
    - material number
    """,
    schema_dir="schema_single",
)

print(json.dumps(result.data, indent=2, default=str, ensure_ascii=False))
print(f"Cost: ${result.usage.cost_usd:.6f}" if result.usage else "Cost: N/A")
```
## Environment Variables

Set provider credentials before running the extractor. Put them in a `.env` file or export them in your shell/session; the toolkit configuration
helpers load these values when building the provider config.

The `.env` file can be saved in the same directory and loaded through `load_dotenv()`. 

### OpenAI / Azure OpenAI

| Variable | When | Description |
|----------|------|-------------|
| `AZURE_API_KEY` | `use_azure=True` | Azure OpenAI API key |
| `AZURE_ENDPOINT` | `use_azure=True` | Azure OpenAI endpoint URL |
| `AZURE_DEPLOYMENT` | `use_azure=True` | Azure deployment name |
| `AZURE_API_VERSION` | `use_azure=True` | Azure API version |
| `OPENAI_API_KEY` | `use_azure=False` | Standard OpenAI API key |
| `OPENAI_MODEL` | `use_azure=False` | Default OpenAI model |

### Claude

| Variable | When | Description |
|----------|------|-------------|
| `AZURE_API_KEY` | `use_azure=True` | Anthropic Foundry API key |
| `ANTHROPIC_FOUNDRY_RESOURCE` | `use_azure=True` | Foundry resource name |
| `ANTHROPIC_API_KEY` | `use_azure=False` | Direct Anthropic API key |
| `ANTHROPIC_MODEL` | Always | Default Claude model |

### Google

| Variable | When | Description |
|----------|------|-------------|
| `GOOGLE_PROJECT_ID` | `vertex_ai=True` | GCP project ID |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | `vertex_ai=True` | Service account JSON |
| `GOOGLE_SCOPES` | `vertex_ai=True` | OAuth scopes |
| `GOOGLE_GENERATE_CONTENT_URL` | `vertex_ai=True` | Vertex AI generateContent endpoint |
| `GOOGLE_API_KEY` | `vertex_ai=False` | Direct Gemini API key |
| `GOOGLE_MODEL` | Always | Default Gemini model |

---

## API

### VisionExtractor

```python
from gaik.software_components.vision_extractor import VisionExtractor

extractor = VisionExtractor(
    api_config=None,                 # Optional provider config dict. If set, skips env-based config loading.
    model_provider="openai",         # "openai" | "claude" | "google"
    model=None,                      # Model/deployment name. None = default from provider config/env vars.
    reasoning_effort="medium",       # "low" | "medium" | "high"
    merge_table=False,               # Ask the model to combine tables split across pages.
    use_azure=True,                  # OpenAI: Azure OpenAI. Claude: Anthropic Foundry.
    vertex_ai=True,                  # Google only. True = Vertex AI, False = Gemini direct API.
    additional_instructions=None,    # Extra instructions appended to the user prompt.
    include_verification=False,      # Add confidence_score and confidence_reason per extracted field.
)
```

Constructor options:

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `api_config` | `dict | None` | `None` | Provider config dictionary. If provided, it is used directly instead of loading from environment variables. |
| `model_provider` | `"openai" | "claude" | "google"` | `"openai"` | Provider used for the vision extraction API call. |
| `model` | `str | None` | `None` | Model or deployment name. If `None`, uses the configured provider default. |
| `reasoning_effort` | `"low" | "medium" | "high"` | `"medium"` | Provider reasoning/thinking effort. Used during layout understanding and extraction. |
| `merge_table` | `bool` | `False` | Adds an instruction to merge tables split across pages. |
| `use_azure` | `bool` | `True` | For OpenAI, use Azure OpenAI. For Claude, use Anthropic Foundry. |
| `vertex_ai` | `bool` | `True` | For Google, use Vertex AI instead of direct Gemini API. |
| `additional_instructions` | `str | None` | `None` | Extra extraction instructions appended to the provider user prompt. |
| `include_verification` | `bool` | `False` | Wraps fields with confidence metadata: `value`, `confidence_score`, and `confidence_reason`. |

### extract()

```python
result = extractor.extract(
    file_paths=["doc.pdf", "appendix.png"],  # Required. PDFs/images sent in one API call.
    user_requirements="Extract ...",         # Required. Natural-language extraction task.
    extraction_model=None,                   # Optional Pydantic model class.
    requirements=None,                       # Optional ExtractionRequirements metadata.
    schema_dir=None,                         # Optional directory for schema.py + requirements.json.
)
```

`extract()` options:

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| `file_paths` | `list[str | Path]` | Yes | One or more PDF/image files. All files are sent together so the model can use cross-document context. |
| `user_requirements` | `str` | Yes | Natural-language description of the structured information to extract. |
| `extraction_model` | `type[BaseModel] | None` | No | Existing Pydantic model. If supplied with `requirements`, schema generation is skipped. |
| `requirements` | `ExtractionRequirements | CompositeExtractionRequirements | None` | No | Field metadata used for post-processing and normalization. Must match `extraction_model` when provided manually. |
| `schema_dir` | `str | Path | None` | No | Directory used to load/save generated schema files. If `schema.py` and `requirements.json` exist, they are reused. |

Schema resolution order:

1. If both `extraction_model` and `requirements` are provided, use them directly.
2. If `schema_dir` contains `schema.py` and `requirements.json`, load the saved schema.
3. Otherwise, generate a schema from `user_requirements`, then save it to `schema_dir` if provided.

Supported input files:

```text
.pdf, .png, .jpg, .jpeg, .gif, .webp, .tiff, .tif, .bmp
```

---

## Result

`extract()` returns a `VisionExtractionResult`:

```python
result.data                 # Extracted structured data as a dict
result.verification         # Verification metadata, or None
result.usage                # UsageRecord with tokens, duration, and cost, or None
result.duration_s           # Wall-clock seconds for the extraction API call
result.model                # Model/deployment identifier used
result.documents_processed  # Number of input files
```

When `include_verification=True`, scalar fields are returned with confidence metadata:

```python
{
    "invoice_number": {
        "value": "INV-1001",
        "confidence_score": 0.98,
        "confidence_reason": "Value appears explicitly next to the invoice number label."
    }
}
```

---

## Schema Generation

If no schema is supplied, `VisionExtractor` uses `SchemaGenerator` to build a dynamic Pydantic model from `user_requirements`.
Schema generation uses OpenAI/Azure OpenAI configuration and follows the
`VisionExtractor(use_azure=...)` flag: `use_azure=True` uses Azure OpenAI, while
`use_azure=False` uses the standard OpenAI configuration.

The generated schema supports:

- Flat objects: one record with scalar fields.
- Nested lists: repeated records/items/rows.
- Parent with nested list: one document-level object plus one repeated child collection.

Example parent-with-list output:

```python
{
    "date": "12-05-2026",
    "purchase_order_number": "4500001234",
    "supplier_number": "SUP-123",
    "contact": "Jane Smith",
    "line_items": [
        {
            "item_number": "10",
            "complete_description": "Copper wire",
            "quantity": 20,
            "price": "15.50",
            "material_number": "MAT-100"
        }
    ]
}
```

Schema persistence files:

```text
schema.py           # Generated Pydantic model
requirements.json   # Field metadata and structure type
```

Delete or change `schema_dir` when you want to force schema regeneration.

---

## Provider Examples

### OpenAI / Azure OpenAI

```python
extractor = VisionExtractor(
    model_provider="openai",
    model="gpt-5.4-mini",
    use_azure=False,
    reasoning_effort="low",
)
```

### Claude

```python
extractor = VisionExtractor(
    model_provider="claude",
    model="claude-sonnet-4-6",
    use_azure=False,
    reasoning_effort="high",
)
```

Claude uses tool calling for structured extraction. When thinking is enabled, forced tool use is not compatible with Claude's API, so the component uses automatic tool choice and raises an error if the extraction tool is not called.

### Google Gemini

```python
extractor = VisionExtractor(
    model_provider="google",
    model="gemini-3.1-pro-preview",
    vertex_ai=False,
    reasoning_effort="medium",
)
```

---

## Examples

See the runnable example script:

```text
implementation_layer/examples/software_components/vision_extractor/vision_extractor_example.py
implementation_layer/examples/software_components/vision_extractor/vision_extractor_example_minimal.py
```

The example demonstrates single-document and multi-document extraction, schema
persistence with `schema.py` and `requirements.json`, provider selection,
reasoning effort, table-merge instructions, verification, token usage, and cost
reporting.

---

## Usage And Cost

`result.usage` is a `UsageRecord`:

```python
result.usage.provider
result.usage.model
result.usage.input_tokens
result.usage.output_tokens
result.usage.thinking_tokens
result.usage.total_tokens
result.usage.duration_s
result.usage.cost_usd
```

Cost is calculated using shared pricing tables in `gaik.observability.pricing`. Reasoning/thinking tokens are billed at the output-token rate.

---

## When To Use This Component

Use `VisionExtractor` when:

- The original document layout is important for extraction.
- Tables have merged cells, split pages, or ambiguous headers.
- A text parser loses row alignment or document structure.
- You need one call to reason over multiple related files.
- You want structured output directly from the visual document.
- The task is high-value enough to justify a larger vision-model call.

Use the standard `extractor` when:

- You already have clean, reliable text or Markdown.
- Layout is simple and extraction does not depend on visual structure.
- You want a lower-cost two-step pipeline with reusable parsed text.

## License

MIT - see [LICENSE](../../../../../LICENSE)
