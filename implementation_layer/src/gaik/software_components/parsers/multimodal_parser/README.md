# Multimodal Parser

Multi-provider PDF-to-markdown parser that sends PDFs to OpenAI, Claude, or Google Gemini for layout-aware extraction. Produces raw markdown with layout metadata, cleaned markdown, and optionally styled HTML.

## Installation

```bash
pip install "gaik[multimodal-parser]"
```

**Note:** Requires API credentials for at least one provider (OpenAI/Azure, Anthropic Foundry, or Google Vertex AI).

---

## Quick Start

```python
from gaik.software_components.parsers.multimodal_parser import MultimodalParser

parser = MultimodalParser(
    model_provider="openai",
    model="gpt-5.4",
    use_azure=True,
    reasoning_effort="low",
    merge_table=True,
    create_html=True,
)
result = parser.parse("document.pdf")
print(result.clean_markdown)
```

---

## API

### MultimodalParser

```python
from gaik.software_components.parsers.multimodal_parser import MultimodalParser

parser = MultimodalParser(
    model_provider="openai",                    # "openai" | "claude" | "google"
    model=None,                                 # Model name (None = default from config)
    reasoning_effort="low",                     # "low" | "medium" | "high"
    merge_table=False,                          # Combine tables split across pages
    use_azure=True,                             # Azure/Foundry (openai & claude providers)
    vertex_ai=True,                             # Vertex AI (google provider)
    additional_instructions=None,               # Additional instructions appended to user prompt
    create_html=False,                          # Produce HTML from cleaned markdown
)
result = parser.parse("document.pdf")
```

### ParseResult

```python
result.raw_markdown     # Model output with <div data-bbox/data-label> wrappers
result.clean_markdown   # Wrappers stripped, inner markdown/HTML preserved
result.html             # Styled HTML document, or None if create_html=False
result.usage            # UsageRecord with token counts, duration, and USD cost
```

### UsageRecord

Token accounting and cost are computed from `pricing.py` using longest-prefix
matching on the model name. Reasoning/thinking tokens are billed at the output
rate, matching provider behaviour.

```python
result.usage.provider        # "openai" | "claude" | "google"
result.usage.model           # Actual model identifier used
result.usage.input_tokens    # Prompt tokens sent
result.usage.output_tokens   # Completion tokens (incl. reasoning)
result.usage.thinking_tokens # Subset of output_tokens spent on reasoning
result.usage.total_tokens
result.usage.duration_s      # Wall-clock seconds for the single parse() call
result.usage.cost_usd        # 0.0 if the model has no pricing entry
```

To price a hypothetical call without running the parser:

```python
from gaik.software_components.parsers.multimodal_parser import compute_cost_usd

compute_cost_usd("openai", "gpt-5.4-mini", input_tokens=1000, output_tokens=2000)
# -> 0.00975
```

### Configuration

```python
from gaik.software_components.parsers.multimodal_parser import (
    get_openai_config, create_openai_client,   # OpenAI / Azure OpenAI
    get_claude_config, create_claude_client,   # Anthropic Foundry
    get_google_config, get_google_access_token, # Google Vertex AI
)
```

---

## Provider Examples

### OpenAI / Azure OpenAI

```python
from gaik.software_components.parsers.multimodal_parser import MultimodalParser

parser = MultimodalParser(model_provider="openai", model="gpt-5.4", use_azure=True)
result = parser.parse("document.pdf")
```

### Claude (Anthropic Foundry)

```python
from gaik.software_components.parsers.multimodal_parser import MultimodalParser

parser = MultimodalParser(model_provider="claude", model="claude-sonnet-4-6", use_azure=True, reasoning_effort="high")
result = parser.parse("document.pdf")
```

### Claude (Direct Anthropic API)

```python
from gaik.software_components.parsers.multimodal_parser import MultimodalParser

parser = MultimodalParser(model_provider="claude", model="claude-sonnet-4-6", use_azure=False, reasoning_effort="high")
result = parser.parse("document.pdf")
```

### Google Gemini (Vertex AI)

```python
from gaik.software_components.parsers.multimodal_parser import MultimodalParser

parser = MultimodalParser(model_provider="google", model="gemini-3-flash-preview", vertex_ai=True, reasoning_effort="medium")
result = parser.parse("document.pdf")
```

### Google Gemini (Direct API)

```python
from gaik.software_components.parsers.multimodal_parser import MultimodalParser

parser = MultimodalParser(model_provider="google", model="gemini-3-flash-preview", vertex_ai=False, reasoning_effort="medium")
result = parser.parse("document.pdf")
```

---

## Environment Variables

### OpenAI / Azure OpenAI

| Variable | When | Default | Description |
|----------|------|---------|-------------|
| `AZURE_API_KEY` | `use_azure=True` | — | Azure OpenAI API key |
| `AZURE_ENDPOINT` | `use_azure=True` | — | Azure OpenAI endpoint URL |
| `AZURE_DEPLOYMENT` | `use_azure=True` | `gpt-5.4` | Azure deployment name (fallback when `model=None`) |
| `AZURE_API_VERSION` | `use_azure=True` | `2025-03-01-preview` | API version |
| `OPENAI_API_KEY` | `use_azure=False` | — | Standard OpenAI API key |
| `OPENAI_MODEL` | `use_azure=False` | `gpt-5.4-2026-03-05` | Model name (fallback when `model=None`) |

### Anthropic (Claude)

| Variable | When | Default | Description |
|----------|------|---------|-------------|
| `AZURE_API_KEY` | `use_azure=True` | — | Foundry API key |
| `ANTHROPIC_FOUNDRY_RESOURCE` | `use_azure=True` | — | Foundry resource name |
| `ANTHROPIC_API_KEY` | `use_azure=False` | — | Direct Anthropic API key |
| `ANTHROPIC_MODEL` | Always | `claude-sonnet-4-6` | Model name (fallback when `model=None`) |

### Google (Gemini)

| Variable | When | Default | Description |
|----------|------|---------|-------------|
| `GOOGLE_PROJECT_ID` | `vertex_ai=True` | — | GCP project ID |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | `vertex_ai=True` | — | Service account JSON (inline) |
| `GOOGLE_SCOPES` | `vertex_ai=True` | — | OAuth scopes (comma-separated) |
| `GOOGLE_GENERATE_CONTENT_URL` | `vertex_ai=True` | — | Vertex generateContent endpoint. Include literal `{model}` to have the active model substituted at call time (e.g. `.../models/{model}:generateContent`), so one deployment can swap Gemini models at runtime. |
| `GOOGLE_API_KEY` | `vertex_ai=False` | — | Direct Gemini API key |
| `GOOGLE_MODEL` | Always | `gemini-3-flash-preview` | Model name (fallback when `model=None`) |

## License

MIT - see [LICENSE](../../../../../LICENSE)
