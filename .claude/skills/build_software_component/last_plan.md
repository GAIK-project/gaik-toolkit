# Component Plan: multimodel_parser

## 1. Component Identity

- **component_name:** `multimodel_parser`
- **MainClassName:** `MultimodelParser`
- **One-line description:** Multi-provider PDF-to-markdown parser that sends PDFs to OpenAI, Claude, or Google Gemini for layout-aware extraction, producing raw markdown with layout metadata, cleaned markdown, and optionally styled HTML.

## 2. Public API

### Main class

```python
class MultimodelParser:
    def __init__(
        self,
        config: dict,
        *,
        model_provider: str = "openai",       # "openai" | "claude" | "google"
        reasoning_effort: str = "low",         # "low" | "medium" | "high"
        merge_table: bool = False,
        use_azure: bool = True,                # only affects openai provider
        additional_instructions: str | None = None,
        create_html: bool = False,
    ):
        """
        Args:
            config: Provider-specific configuration dict.
                    - openai: from get_openai_config(use_azure=...)
                    - claude: from get_claude_config()
                    - google: from get_google_config()
            model_provider: Which LLM provider to use.
            reasoning_effort: Thinking/reasoning effort level.
            merge_table: If True, instructs the model to combine tables
                         split across multiple pages.
            use_azure: Whether to use Azure OpenAI (only for openai provider).
            additional_instructions: Extra text appended to the user prompt.
            create_html: If True, also produce an HTML version of the cleaned markdown.
        """

    def parse(self, pdf_path: str | Path) -> ParseResult:
        """
        Parse a PDF file and return structured output.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            ParseResult with raw_markdown, clean_markdown, and optional html.
        """
```

### Result dataclass

```python
@dataclass
class ParseResult:
    raw_markdown: str         # Model output with <div data-bbox/data-label> wrappers
    clean_markdown: str       # Wrappers stripped, inner markdown/HTML preserved
    html: str | None          # Styled HTML document, or None if create_html=False

    def save(self, directory: str | Path, prefix: str = "output") -> dict[str, Path]:
        """
        Write outputs to disk.

        Returns:
            {"raw_markdown": Path, "clean_markdown": Path, "html": Path | None}
        """
```

### Config module (`config.py` — complete, self-contained)

The component ships its own `config.py` copied from the source codebase at
`C:\Users\h02317\parsing\config.py`. It covers **all three providers** in one
file and does NOT import from `gaik.software_components.config`.

```python
# multimodel_parser/config.py — all six functions

def require_env(name: str) -> str:
    """Return a required environment variable or fail with a clear message."""

def get_openai_config(use_azure: bool = True) -> dict:
    """OpenAI / Azure OpenAI config."""

def create_openai_client(config: dict):
    """Create OpenAI or AzureOpenAI client."""

def get_claude_config() -> dict:
    """Anthropic Foundry config (AZURE_API_KEY, ANTHROPIC_FOUNDRY_RESOURCE, ANTHROPIC_MODEL)."""

def create_claude_client(config: dict):
    """Create anthropic.AnthropicFoundry client."""

def get_google_config() -> dict:
    """Google Vertex AI config (project, service account, model, scopes, URL)."""

def get_google_access_token(config: dict) -> str:
    """Refresh and return a Google Cloud access token."""
```

This keeps the component fully self-contained. Users import config helpers from
the component itself, not from the shared GAIK config.

## 3. Dependencies

All required (needed by at least one provider path):

| Package | Version | Purpose |
|---------|---------|---------|
| `anthropic` | `>=0.43.0` | Claude / Anthropic Foundry client |
| `google-auth` | `>=2.0.0` | Google Vertex AI service-account auth |
| `requests` | `>=2.31.0` | Google Vertex AI HTTP calls |
| `markdown-it-py` | `>=3.0.0` | Markdown-to-HTML rendering |

Core deps already in GAIK base: `openai`, `pydantic`, `python-dotenv`.

## 4. Config Integration

All config functions live in the component's own `config.py` (self-contained,
same code as the source `C:\Users\h02317\parsing\config.py`):

| Provider | Config source | Client creation |
|----------|--------------|-----------------|
| `openai` | `get_openai_config(use_azure=...)` from `multimodel_parser.config` | `create_openai_client(config)` from `multimodel_parser.config` |
| `claude` | `get_claude_config()` from `multimodel_parser.config` | `create_claude_client(config)` from `multimodel_parser.config` |
| `google` | `get_google_config()` from `multimodel_parser.config` | Raw `requests.post(...)` to Vertex AI, auth via `get_google_access_token()` from `multimodel_parser.config` |

The main class **does not** call `load_dotenv()` or read env vars directly.
The config helpers in `config.py` handle env-var reads, and the user calls
them explicitly before constructing the parser.

## 5. Files to Create

| # | Path |
|---|------|
| 1 | `implementation_layer/src/gaik/software_components/multimodel_parser/__init__.py` |
| 2 | `implementation_layer/src/gaik/software_components/multimodel_parser/multimodel_parser.py` |
| 3 | `implementation_layer/src/gaik/software_components/multimodel_parser/config.py` |
| 4 | `implementation_layer/src/gaik/software_components/multimodel_parser/prompts.py` |
| 5 | `implementation_layer/src/gaik/software_components/multimodel_parser/README.md` |
| 6 | `implementation_layer/examples/software_components/multimodel_parser/multimodel_parser_example.py` |

### Component directory layout

```
multimodel_parser/
├── __init__.py              # Re-exports: MultimodelParser, ParseResult, all config helpers
├── multimodel_parser.py     # Main class + ParseResult dataclass
├── config.py                # Complete config for all 3 providers (same as source)
│                            # get_openai_config, create_openai_client,
│                            # get_claude_config, create_claude_client,
│                            # get_google_config, get_google_access_token
├── prompts.py               # System/user prompts for all 3 providers
└── README.md                # Install + quick start docs
```

### Why separate files?

- **config.py**: Mirrors the source codebase's `config.py` structure. Keeps
  provider auth logic separate from parsing logic. Users import config helpers
  directly when they need them.
- **prompts.py**: The six prompt constants (~80 lines of multi-line strings)
  would clutter the main class file.

## 6. Files to Modify

| File | Change |
|------|--------|
| `pyproject.toml` | Add `multimodel-parser = [...]` under `[project.optional-dependencies]` |
| `implementation_layer/src/gaik/software_components/__init__.py` | Append `"multimodel_parser"` to `__all__` |

The component will **not** be added to the `all` or `all-cpu` composite groups
because it pulls in `anthropic` and `google-auth` which are heavy optional deps.
Users opt in explicitly with `pip install "gaik[multimodel-parser]"`.

## 7. Install Extra Name

```
multimodel-parser
```

```toml
multimodel-parser = [
    "anthropic>=0.43.0",
    "google-auth>=2.0.0",
    "requests>=2.31.0",
    "markdown-it-py>=3.0.0",
]
```

## 8. Example Usage

```python
from gaik.software_components.multimodel_parser import (
    MultimodelParser,
    get_openai_config,
    get_claude_config,
    get_google_config,
)

# OpenAI / Azure OpenAI
config = get_openai_config(use_azure=True)
parser = MultimodelParser(
    config=config,
    model_provider="openai",
    reasoning_effort="low",
    merge_table=True,
    create_html=True,
)
result = parser.parse("document.pdf")
print(result.clean_markdown)
result.save("output/")

# Claude via Anthropic Foundry
config = get_claude_config()
parser = MultimodelParser(config=config, model_provider="claude", reasoning_effort="high")
result = parser.parse("document.pdf")

# Google Gemini via Vertex AI
config = get_google_config()
parser = MultimodelParser(config=config, model_provider="google", reasoning_effort="medium")
result = parser.parse("document.pdf")
```

## 9. Verification Steps

```bash
# Install
pip install -e ".[multimodel-parser]"

# Import smoke test
python -c "from gaik.software_components.multimodel_parser import MultimodelParser; print('OK')"

# Example (requires credentials)
python implementation_layer/examples/software_components/multimodel_parser/multimodel_parser_example.py
```

## Implementation Notes

### Reasoning effort mapping

The `reasoning_effort` parameter maps to provider-specific API fields:

| Provider | API field | low | medium | high |
|----------|-----------|-----|--------|------|
| OpenAI | `reasoning={"effort": ...}` | `"low"` | `"medium"` | `"high"` |
| Claude | `thinking={"type": "adaptive"}, output_config={"effort": ...}` | `"low"` | `"medium"` | `"high"` |
| Google | `generationConfig.thinkingConfig.thinkingLevel` | `"low"` | `"medium"` | `"high"` |

### additional_instructions handling

When `additional_instructions` is not None, the string is appended to the end
of the provider-specific user prompt (after a newline).

### Post-processing pipeline

1. Raw model output → `unwrap_fenced_output()` (strip code-block wrapper if present)
2. → `clean_markdown()` (strip `<div>` wrappers, keep inner content)
3. → `markdown_to_html_document()` (only if `create_html=True`)

### HTML template

The styled HTML template from the source code is embedded in `multimodel_parser.py`.
It uses a document-style CSS theme with table support.
