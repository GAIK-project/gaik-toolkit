# Document Classifier

[![PyPI version](https://badge.fury.io/py/gaik.svg)](https://pypi.org/project/gaik/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

LLM-powered single-label document classification for PDFs, Word files, and images, shipped as part of the `gaik` toolkit.

## Installation

```bash
pip install gaik[classifier]
```

## Packages

| Package | Description | Documentation |
|---------|-------------|---------------|
| **gaik.doc_classifier** | Core document classification pipeline | [📖 Docs](./classifier.py) |
| **gaik.doc_classifier.config** | Helpers for OpenAI/Azure client configuration | [📖 Docs](./config.py) |
| **examples.classifier** | Ready-to-run classification workflows | [📖 Docs](../../../../../../examples/classifier/classification_example.py) |

## Documentation

- **Getting Started** - Import `DocumentClassifier` and `get_openai_config` from `gaik.doc_classifier`
- **Examples** - [examples/classifier/](../../../../../../examples/classifier/)
- **Contributing** - [CONTRIBUTING.md](../../../../../../CONTRIBUTING.md)

## Requirements

- Python 3.10+
- Access to OpenAI or Azure OpenAI (API key, endpoint, deployment/model)
- `gaik[classifier]` extras (installs `openai`, `PyMuPDF`, `python-docx`, and dependencies)

## License

MIT - see [LICENSE](../../../../../../LICENSE)
