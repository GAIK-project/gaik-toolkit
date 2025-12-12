# VisionParser

Parse PDFs to Markdown using OpenAI GPT-4 Vision with advanced table extraction and multi-page context awareness.

## Installation

```bash
pip install gaik[parser]
```

**Note:** Requires OpenAI or Azure OpenAI API access

---

## Quick Start

```python
from gaik.building_blocks.parsers import VisionParser, get_openai_config

# Configure
config = get_openai_config(use_azure=True)

# Parse PDF to Markdown using Vision API
parser = VisionParser(
    openai_config=config,
    use_context=True,      # Multi-page continuity
    dpi=200,               # Image quality (150-300)
    clean_output=True      # Clean and merge tables
)

pages = parser.convert_pdf("document.pdf")
markdown = pages[0] if len(pages) == 1 else "\n\n".join(pages)

# Save markdown
parser.save_markdown(markdown, "document.md")
```

---

## Features

- **Vision-Based Parsing** - PDF to Markdown using OpenAI GPT-4V with table extraction
- **Multi-Page Context** - Maintains context across pages for better accuracy
- **Table Cleaning** - Automatically merges and cleans tables across page breaks
- **High Quality** - Best results for complex layouts, images, and tables
- **Customizable** - Adjust DPI, prompts, and output cleaning

---

## API Reference

### VisionParser

```python
from gaik.building_blocks.parsers import VisionParser

parser = VisionParser(
    openai_config: dict,           # From get_openai_config()
    custom_prompt: str | None = None,
    use_context: bool = True,      # Multi-page context
    max_tokens: int = 16_000,
    dpi: int = 200,                # 150-300 recommended
    clean_output: bool = True      # Table cleaning
)

# Convert PDF
pages = parser.convert_pdf(pdf_path: str) -> list[str]

# Save markdown
parser.save_markdown(markdown_content: str, output_path: str)
```

### Configuration

```python
from gaik.building_blocks.parsers import get_openai_config

# Azure OpenAI (default)
config = get_openai_config(use_azure=True)

# Standard OpenAI
config = get_openai_config(use_azure=False)
```

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

## Performance Tips

- **DPI Settings**: 200 DPI is a good balance. Lower (150) for speed, higher (300) for quality
- **Multi-Page Context**: Enable `use_context=True` for documents with continuity between pages
- **Table Cleaning**: Enable `clean_output=True` for better table formatting
- **Token Limits**: Adjust `max_tokens` based on content density (default: 16,000)

---

## Examples

See [examples/building_blocks/parsers/demo_vision_simple.py](../../examples/building_blocks/parsers/demo_vision_simple.py) for complete example.

---

## Resources

- **Back to Parsers**: [docs/parsers/](README.md)
- **Repository**: [github.com/GAIK-project/gaik-toolkit](https://github.com/GAIK-project/gaik-toolkit)
- **Contributing**: [CONTRIBUTING.md](../../CONTRIBUTING.md)

## License

MIT - see [LICENSE](../../LICENSE)





