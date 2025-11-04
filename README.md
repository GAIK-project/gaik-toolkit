# GAIK - General AI Kit

**Shared Python components for AI/ML projects**

A modular toolkit providing production-ready AI/ML utilities. Currently featuring dynamic schema extraction with multi-provider LLM support (OpenAI, Anthropic, Azure, Google) using LangChain's structured outputs.

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

### Extract Data from Text

```python
from gaik.extract import SchemaExtractor

# Using default OpenAI provider
extractor = SchemaExtractor("Extract name and age from text")
results = extractor.extract(["Alice is 25 years old"])
print(results[0])
# {'name': 'Alice', 'age': 25}

# Using Anthropic Claude
extractor = SchemaExtractor(
    "Extract name and age from text",
    provider="anthropic"
)

# Using Google Gemini
extractor = SchemaExtractor(
    "Extract name and age from text",
    provider="google",
    model="gemini-1.5-pro"
)
```

### Generate Schema Only (No Extraction)

```python
from gaik.extract import SchemaExtractor

# Create extractor and get the schema
extractor = SchemaExtractor("Extract invoice number and amount")

# Get JSON Schema (standard format, works with any tool)
json_schema = extractor.model.model_json_schema()
print(json_schema)
# Returns: {"type": "object", "properties": {...}, "required": [...]}

# Or access the Pydantic model directly
pydantic_model = extractor.model
```

**Full documentation:** [gaik-py/README.md](gaik-py/README.md)

---

## 🌟 Features

### `gaik.extract` - Dynamic Schema Extraction

Extract structured data from unstructured text using LangChain's structured outputs with multi-provider support:

```python
from gaik.extract import dynamic_extraction_workflow

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

# Default OpenAI
results = dynamic_extraction_workflow(description, documents)

# Or use Anthropic Claude
results = dynamic_extraction_workflow(
    description,
    documents,
    provider="anthropic"
)
```

**Benefits:**

- ✅ Multi-provider support (OpenAI, Anthropic, Azure, Google)
- ✅ Guaranteed structure (API-enforced)
- ✅ Type-safe with Pydantic
- ✅ No code generation or `eval()`
- ✅ Cost-effective
- ✅ Clean, extensible architecture

---

## 📁 Repository Structure

```
toolkit-shared-components/
├── gaik-py/              # Python package
│   ├── src/gaik/
│   │   ├── providers/    # Multi-provider LLM interface
│   │   └── extract/      # Dynamic schema extraction
│   ├── pyproject.toml
│   └── README.md
├── examples/             # Usage examples
├── docs/                 # Documentation
│   └── PUBLISHING.md     # PyPI publishing guide
└── .github/workflows/    # CI/CD automation
```

---

## 🔧 For Contributors

### Developer Guide: Add New LLM Provider

GAIK uses a shared `gaik.providers` module that all library components can use. Adding a new provider is straightforward:

**1. Create provider class**

File: `gaik-py/src/gaik/providers/yourprovider.py`

```python
from langchain_yourprovider import ChatYourProvider
from .base import LLMProvider

class YourProviderProvider(LLMProvider):
    @property
    def default_model(self) -> str:
        return "your-default-model-name"

    def create_chat_model(self, model=None, api_key=None, **kwargs):
        return ChatYourProvider(
            model=model or self.default_model,
            api_key=api_key,
            **kwargs
        )
```

**2. Add dependency**

File: `gaik-py/pyproject.toml`

```toml
dependencies = [
    ...
    "langchain-yourprovider>=x.x.x",
]
```

**3. Register provider**

File: `gaik-py/src/gaik/providers/__init__.py`

```python
from .yourprovider import YourProviderProvider

PROVIDERS = {
    ...
    "yourprovider": YourProviderProvider(),
}
```

**4. Use it**

```python
from gaik.extract import SchemaExtractor

extractor = SchemaExtractor(
    "Extract name and age",
    provider="yourprovider"
)
```

Done! The provider is now available to all GAIK modules (extract, future modules, etc.)

### Developer Guide: Testing Your Changes

**Local development with uv (recommended):**

```bash
cd gaik-py

# Create virtual environment
uv venv

# Install package in editable mode
uv pip install -e .

# Run tests (no API calls needed)
uv run python ../examples/test_gaik_installation.py

# Test with real API (requires API key)
uv run python ../examples/test_real_extraction.py

# Build package
uv pip install build
uv run python -m build

# Check package
uv pip install twine
uv run twine check dist/*
```

**Testing checklist:**
- ✅ All imports work
- ✅ Provider registry contains your new provider
- ✅ Package builds without errors
- ✅ Twine check passes
- ✅ Real extraction works (if API key available)

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
pip install -e .

# Optional: include linting/publishing tooling
pip install -e .[dev]

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

The `gaik.extract` module requires an API key for your chosen provider:

**OpenAI (default):**
```bash
export OPENAI_API_KEY='sk-...'
```
Get your key: [platform.openai.com/api-keys](https://platform.openai.com/api-keys)

**Anthropic:**
```bash
export ANTHROPIC_API_KEY='sk-ant-...'
```
Get your key: [console.anthropic.com](https://console.anthropic.com)

**Google:**
```bash
export GOOGLE_API_KEY='...'
```
Get your key: [ai.google.dev](https://ai.google.dev)

**Azure OpenAI:**
```bash
export AZURE_OPENAI_API_KEY='...'
export AZURE_OPENAI_ENDPOINT='https://your-resource.openai.azure.com/'
```

Alternatively, pass API keys directly to the extractor:
```python
extractor = SchemaExtractor(
    "Extract name and age",
    provider="anthropic",
    api_key="your-api-key"
)
```

---

## 🔗 Resources

- **Package (Test PyPI)**: [test.pypi.org/project/gaik](https://test.pypi.org/project/gaik/)
- **Documentation**: [gaik-py/README.md](gaik-py/README.md)
- **Publishing Guide**: [docs/PUBLISHING.md](docs/PUBLISHING.md)
- **Cheatsheet (FI)**: [docs/gaik-toolkit-cheatsheet.md](docs/gaik-toolkit-cheatsheet.md)
- **Issues**: [github.com/GAIK-project/toolkit-shared-components/issues](https://github.com/GAIK-project/toolkit-shared-components/issues)
- **OpenAI Docs**: [OpenAI structured outputs guide](https://platform.openai.com/docs/guides/structured-outputs)

---

## 📄 License

MIT - see [LICENSE](LICENSE) for details
