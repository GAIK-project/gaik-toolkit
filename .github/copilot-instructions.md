## Monorepo Structure
```
gaik-toolkit/
â”œâ”€â”€ packages/python/gaik/     # PyPI package source
â”‚   â”œâ”€â”€ src/gaik/
â”‚   â”‚   â”œâ”€â”€ extract/          # Schema extraction
â”‚   â”‚   â”œâ”€â”€ providers/        # LLM integrations
â”‚   â”‚   â””â”€â”€ parsers/          # PDF/document parsing
â”‚   â””â”€â”€ pyproject.toml        # Package config
â”œâ”€â”€ examples/                 # Usage examples
â””â”€â”€ .github/workflows/        # CI/CD pipelines
```

## Core APIs
```python
# Extraction
from gaik.extract import SchemaExtractor
extractor = SchemaExtractor("Extract name and age", provider="anthropic")
results = extractor.extract(["Alice is 25"])

# Parsing
from gaik.building_blocks.parsers.pymypdf import PyMuPDFParser
parser = PyMuPDFParser()
result = parser.parse_document("document.pdf")
```

## Local Development
```bash
cd packages/python/gaik
pip install -e .[all,dev]
pytest                     # Run tests
ruff check --fix .         # Lint
python -m build            # Build package
```

## Publishing
```bash
git tag v0.3.0             # Tag format: vX.Y.Z
git push origin v0.3.0     # Triggers GitHub Actions
```

GitHub Actions auto-publishes to PyPI and creates release.

