# GAIK - General AI Kit

**Shared Python components for AI/ML projects**

A modular toolkit providing production-ready AI/ML utilities. Currently featuring dynamic schema extraction with OpenAI's structured outputs.

---

## 📦 Quick Install

```bash
# From Test PyPI (current)
pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ gaik

# From PyPI (coming soon)
# pip install gaik
```

---

## 🚀 Quick Start

```python
from gaik.schema import SchemaExtractor

extractor = SchemaExtractor("Extract name and age from text")
result = extractor.extract_one("Alice is 25 years old")
print(result)
# {'name': 'Alice', 'age': 25}
```

**Full documentation:** [gaik-py/README.md](gaik-py/README.md)

---

## 🌟 Features

### `gaik.schema` - Dynamic Schema Extraction

Extract structured data from unstructured text using OpenAI's structured outputs:

```python
from gaik.schema import dynamic_extraction_workflow

description = """
Extract from invoices:
- Invoice number
- Total amount in USD
- Vendor name
"""

documents = [
    "Invoice #12345 from Acme Corp. Total: $1,500",
    "INV-67890, Vendor: TechCo, Amount: $2,750"
]

results = dynamic_extraction_workflow(description, documents)
```

**Benefits:**
- ✅ Guaranteed structure (API-enforced)
- ✅ Type-safe with Pydantic
- ✅ No code generation or `eval()`
- ✅ Cost-effective
- ✅ Clean, minimal dependencies

---

## 📁 Repository Structure

```
toolkit-shared-components/
├── gaik-py/              # Python package
│   ├── src/gaik/
│   │   └── schema/       # Dynamic schema extraction
│   ├── pyproject.toml
│   └── README.md
├── examples/             # Usage examples
├── docs/                 # Documentation
│   └── PUBLISHING.md     # PyPI publishing guide
└── .github/workflows/    # CI/CD automation
```

---

## 🔧 For Contributors

### Publishing New Versions

See detailed guide: [docs/PUBLISHING.md](docs/PUBLISHING.md)

**Quick workflow:**

1. Update version in `pyproject.toml` and `__init__.py`
2. Commit changes
3. Create and push tag: `git tag v0.2.0 && git push origin v0.2.0`
4. GitHub Actions automatically publishes to Test PyPI

### Local Development

```bash
# Clone and install
git clone https://github.com/GAIK-project/toolkit-shared-components.git
cd toolkit-shared-components/gaik-py
pip install -e ".[dev]"

# Build and test
python -m build
twine check dist/*
```

---

## 📋 Version History

- **v0.1.1** (Current) - Updated OpenAI API, improved docs
- **v0.1.0** - Initial release with dynamic schema extraction

---

## ⚠️ Requirements

The `gaik.schema` module requires an OpenAI API key:

```bash
export OPENAI_API_KEY='sk-...'
```

Get your key: https://platform.openai.com/api-keys

---

## 🔗 Resources

- **Package (Test PyPI)**: https://test.pypi.org/project/gaik/
- **Documentation**: [gaik-py/README.md](gaik-py/README.md)
- **Publishing Guide**: [docs/PUBLISHING.md](docs/PUBLISHING.md)
- **Issues**: https://github.com/GAIK-project/toolkit-shared-components/issues
- **OpenAI Docs**: https://platform.openai.com/docs/guides/structured-outputs

---

## 📄 License

MIT - see [LICENSE](LICENSE) for details
