# PyMuPDFParser

Fast local PDF text extraction using PyMuPDF. No API calls required.

## Installation

```bash
pip install gaik[parser]
```

**Note:** No API keys required - runs completely locally

---

## Quick Start

```python
from gaik.building_blocks.parsers import PyMuPDFParser

parser = PyMuPDFParser()

# Parse PDF document (fast, no AI required)
result = parser.parse_document(file_path="document.pdf")

# Access extracted content
print(result["text_content"])
print(result["metadata"])  # Page count, author, etc.
```

---

## Features

- **Fast Local Processing** - No API calls, no costs
- **Simple Text Extraction** - Quick extraction of text content from PDFs
- **Metadata Extraction** - Access PDF metadata (author, page count, etc.)
- **No Dependencies** - Works offline, no API keys needed
- **Lightweight** - Minimal resource usage

---

## API Reference

### PyMuPDFParser

```python
from gaik.building_blocks.parsers import PyMuPDFParser

parser = PyMuPDFParser()

# Parse PDF document
result = parser.parse_document(file_path: str)
# Returns: {"text_content": str, "metadata": dict}

print(result["text_content"])
print(result["metadata"])  # Page count, author, title, etc.
```

### Return Format

```python
{
    "text_content": str,      # Extracted text from PDF
    "metadata": {
        "page_count": int,    # Number of pages
        "author": str,        # PDF author (if available)
        "title": str,         # PDF title (if available)
        "subject": str,       # PDF subject (if available)
        "creator": str,       # PDF creator app (if available)
        ...
    }
}
```

---

## When to Use

**Best for:**
- Simple text extraction from PDFs
- Fast processing without API costs
- Batch processing many PDFs
- Offline/local processing requirements
- Text-heavy documents with simple layouts

**Not ideal for:**
- Complex table extraction
- Documents with important visual layouts
- Scanned PDFs (use DoclingParser with OCR)
- Documents where formatting context is critical

---

## Examples

See [examples/building_blocks/parsers/demo_pymupdf.py](../../examples/building_blocks/parsers/demo_pymupdf.py) for complete example.

---

## Resources

- **Back to Parsers**: [docs/parsers/](README.md)
- **Repository**: [github.com/GAIK-project/gaik-toolkit](https://github.com/GAIK-project/gaik-toolkit)
- **Contributing**: [CONTRIBUTING.md](../../CONTRIBUTING.md)

## License

MIT - see [LICENSE](../../LICENSE)





