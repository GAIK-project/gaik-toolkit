# Parsers

Convert PDFs and Word documents to structured text using vision models, PyMuPDF, python-docx, or Docling OCR.

## Installation

```bash
pip install gaik[parser]
```

**Note:** Requires OpenAI or Azure OpenAI API access for vision-based parsing

---

## Quick Start

```python
from gaik.parsers import VisionParser, get_openai_config

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
- **Fast Local Parsing** - PyMuPDF for quick PDF text extraction, DocxParser for Word documents - no AI required
- **Advanced OCR** - Docling parser with OCR, table extraction, and multi-format support
- **Multi-Page Context** - Maintains context across pages for better accuracy
- **Table Cleaning** - Automatically merges and cleans tables across page breaks
- **Word Document Support** - Extract text from .docx and .doc files using python-docx

---

## Basic API

### VisionParser

```python
from gaik.parsers import VisionParser

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

### PyMuPDFParser

```python
from gaik.parsers import PyMuPDFParser

parser = PyMuPDFParser()

# Parse PDF document (fast, no AI required)
result = parser.parse_document(file_path: str)
# Returns: {"text_content": str, "metadata": dict}

print(result["text_content"])
print(result["metadata"])  # Page count, author, etc.
```

### DocxParser

```python
from gaik.parsers import DocxParser

parser = DocxParser()

# Parse Word document (fast, no AI required)
result = parser.parse_document(
    file_path: str,
    use_markdown: bool = True  # True for simple text, False for structured
)
# Returns: {
#     "text_content": str,
#     "file_name": str,
#     "word_count": int,
#     "parsing_method": "docx",
#     ...
# }

print(result["text_content"])
print(f"Word count: {result['word_count']}")

# Or use convenience function
from gaik.parsers import parse_docx
result = parse_docx("document.docx", output_path="output.txt")
```

### DoclingParser

```python
from gaik.parsers import DoclingParser

parser = DoclingParser(
    ocr_engine: str = "easyocr",  # or "tesseract", "rapid"
    use_gpu: bool = False
)

# Parse with OCR
result = parser.parse_document(file_path: str)

# Convert to markdown
markdown = parser.convert_to_markdown(file_path: str)
```

### Configuration

```python
from gaik.parsers import get_openai_config

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

**Note:** PyMuPDFParser, DocxParser, and DoclingParser do not require API keys.

---

## Examples

See [examples/parsers/](../../../../../../examples/parsers/) for complete examples.

---

## Resources

- **Repository**: [github.com/GAIK-project/gaik-toolkit](https://github.com/GAIK-project/gaik-toolkit)
- **Examples**: [examples/](../../../../../../examples/)
- **Contributing**: [CONTRIBUTING.md](../../../../../../CONTRIBUTING.md)
- **Issues**: [github.com/GAIK-project/gaik-toolkit/issues](https://github.com/GAIK-project/gaik-toolkit/issues)

## License

MIT - see [LICENSE](../../../../../../LICENSE)
