# Document Classifier

Classify documents into predefined categories using LLM analysis. Supports PDFs, Word documents, and images.

## Installation

```bash
pip install gaik[classifier]
```

**Note:** Requires OpenAI or Azure OpenAI API access

---

## Quick Start

```python
from gaik.building_blocks.doc_classifier import DocumentClassifier, get_openai_config

# Configure
config = get_openai_config(use_azure=True)
classifier = DocumentClassifier(config=config)

# Define categories
classes = ["invoice", "receipt", "contract", "report", "memo"]

# Classify single file
result = classifier.classify(
    file_or_dir="document.pdf",
    classes=classes
)

print(f"Class: {result['document.pdf']['class']}")
print(f"Confidence: {result['document.pdf']['confidence']:.2f}")
print(f"Reasoning: {result['document.pdf']['reasoning']}")
```

---

## Features

- **Multi-Format Support** - PDFs, Word documents (.docx, .doc), and images (.png, .jpg, .jpeg)
- **Smart Extraction** - Extracts first 1000 characters from PDFs/DOCX, analyzes full images
- **Auto Parser Selection** - PyMuPDF for PDFs, DocxParser for Word, VisionParser for images
- **Confidence Scoring** - Returns classification confidence (0.0-1.0) and reasoning
- **Batch Processing** - Classify entire directories of mixed file types
- **Unknown Fallback** - Automatic "unknown" class for uncertain classifications

---

## Basic API

### DocumentClassifier

```python
from gaik.building_blocks.doc_classifier import DocumentClassifier

classifier = DocumentClassifier(
    config: dict,              # From get_openai_config()
    model: str | None = None   # Optional model override
)

# Classify file(s)
results = classifier.classify(
    file_or_dir: str,          # Path to file or directory
    classes: list[str],        # Classification categories
    parser: str | None = None  # Optional: "pymupdf", "docx", "vision"
)
```

**Extraction Behavior:**
- **PDF files**: Extracts first 1000 characters using PyMuPDFParser
- **DOCX files**: Extracts first 1000 characters using DocxParser
- **Image files**: Analyzes entire image using VisionParser

**Returns:**
```python
{
    "filename.pdf": {
        "class": "invoice",
        "confidence": 0.95,
        "reasoning": "Contains invoice number and billing details"
    }
}
```

### Configuration

```python
from gaik.building_blocks.doc_classifier import get_openai_config

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
| `AZURE_API_VERSION` | Optional | API version (default: 2025-03-01-preview) |

---

## Examples

See [examples/building_blocks/classifier/](../examples/building_blocks/classifier/) for complete examples:
- `classification_example.py` - Basic, directory, custom parser, mixed file types

### Directory Classification

```python
# Classify all documents in a directory
results = classifier.classify(
    file_or_dir="documents/",
    classes=["invoice", "receipt", "contract", "report"]
)

for filename, classification in results.items():
    print(f"{filename}: {classification['class']} ({classification['confidence']:.2f})")
```

### Custom Parser

```python
# Use vision parser for complex layouts
result = classifier.classify(
    file_or_dir="complex_document.pdf",
    classes=["invoice", "receipt"],
    parser="vision"  # Override default PyMuPDF parser
)
```

---

## Resources

- **Repository**: [github.com/GAIK-project/gaik-toolkit](https://github.com/GAIK-project/gaik-toolkit)
- **Examples**: [examples/building_blocks/](https://github.com/GAIK-project/gaik-toolkit/tree/main/examples/building_blocks)
- **Contributing**: [CONTRIBUTING.md](../CONTRIBUTING.md)
- **Issues**: [github.com/GAIK-project/gaik-toolkit/issues](https://github.com/GAIK-project/gaik-toolkit/issues)

## License

MIT - see [LICENSE](../LICENSE)






