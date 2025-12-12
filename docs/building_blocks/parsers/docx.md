# DocxParser

Parse Word documents (.docx, .doc) to text using python-docx. No API calls required.

## Installation

```bash
pip install gaik[parser]
```

**Note:** No API keys required - runs completely locally

---

## Quick Start

```python
from gaik.building_blocks.parsers import DocxParser

parser = DocxParser()

# Parse Word document (fast, no AI required)
result = parser.parse_document(
    file_path="document.docx",
    use_markdown=True  # True for simple text, False for structured
)

# Access extracted content
print(result["text_content"])
print(f"Word count: {result['word_count']}")

# Or use convenience function
from gaik.building_blocks.parsers import parse_docx
result = parse_docx("document.docx", output_path="output.txt")
```

---

## Features

- **Fast Local Processing** - No API calls, no costs
- **Multiple Format Support** - Works with .docx and .doc files
- **Markdown Output** - Optional markdown formatting
- **Word Count** - Automatic word count calculation
- **Metadata Extraction** - File name and parsing method info
- **No Dependencies** - Works offline, no API keys needed

---

## API Reference

### DocxParser

```python
from gaik.building_blocks.parsers import DocxParser

parser = DocxParser()

# Parse Word document
result = parser.parse_document(
    file_path: str,
    use_markdown: bool = True  # True for simple text, False for structured
)
```

### Return Format

```python
{
    "text_content": str,          # Extracted text from document
    "file_name": str,             # Name of the processed file
    "word_count": int,            # Total word count
    "parsing_method": "docx",     # Parser identifier
    ...
}
```

### Convenience Function

```python
from gaik.building_blocks.parsers import parse_docx

# Parse and optionally save to file
result = parse_docx(
    file_path: str,
    output_path: str | None = None  # Optional output file path
)
```

---

## When to Use

**Best for:**
- Extracting text from Word documents
- Fast local processing without API costs
- Batch processing many Word files
- Offline/local processing requirements
- Simple text extraction needs

**Not ideal for:**
- Complex formatting preservation
- PDF documents (use PyMuPDFParser or VisionParser)
- Documents requiring OCR
- Advanced table extraction (consider VisionParser)

---

## Examples

```python
# Basic extraction
from gaik.building_blocks.parsers import DocxParser

parser = DocxParser()
result = parser.parse_document("report.docx")
print(result["text_content"])

# Save to file
from gaik.building_blocks.parsers import parse_docx

parse_docx("input.docx", output_path="output.txt")
```

---

## Resources

- **Back to Parsers**: [docs/parsers/](README.md)
- **Repository**: [github.com/GAIK-project/gaik-toolkit](https://github.com/GAIK-project/gaik-toolkit)
- **Contributing**: [CONTRIBUTING.md](../../CONTRIBUTING.md)

## License

MIT - see [LICENSE](../../LICENSE)


