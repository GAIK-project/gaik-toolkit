# Document Classifier

[![PyPI version](https://badge.fury.io/py/gaik.svg)](https://pypi.org/project/gaik/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

LLM-powered single-label document classification for PDFs, Word files, and images.

## Installation

```bash
pip install gaik[classifier]
```

## How to Use

### Basic Classification

```python
from gaik.doc_classifier import DocumentClassifier, get_openai_config

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
    parser="vision"  # Options: "pymupdf", "docx", "vision"
)
```

**See [examples/classifier/](../../../../../../examples/classifier/) for more examples.**

## Packages

| Package | Description | Documentation |
|---------|-------------|---------------|
| **gaik.doc_classifier** | Core document classification pipeline | [📖 Docs](./classifier.py) |
| **gaik.config** | Shared OpenAI/Azure client configuration | [📖 Docs](../config.py) |
| **examples.classifier** | Ready-to-run classification workflows | [📖 Docs](../../../../../../examples/classifier/classification_example.py) |

## Documentation

- **Getting Started** - See package documentation above
- **Examples** - [examples/classifier/](../../../../../../examples/classifier/)
- **Contributing** - [CONTRIBUTING.md](../../../../../../CONTRIBUTING.md)

## Requirements

- Python 3.10+
- OpenAI or Azure OpenAI API access
- `gaik[classifier]` extras (installs `openai`, `PyMuPDF`, `python-docx`, and dependencies)

## License

MIT - see [LICENSE](../../../../../../LICENSE)
