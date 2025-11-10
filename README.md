# GAIK - General AI Kit

**Shared Python components for AI/ML projects**

A modular toolkit providing production-ready AI/ML utilities. Currently featuring dynamic schema extraction with multi-provider LLM support (OpenAI, Anthropic, Azure, Google) using LangChain's structured outputs.

---

## 📦 Quick Install

```bash
# From PyPI (production)
pip install gaik

# With optional vision parser support
pip install gaik[vision]
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
    model="gemini-2.5-flash"
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

## 🔧 Contributing

Want to add a new LLM provider or contribute? See [CONTRIBUTING.md](CONTRIBUTING.md)

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
export AZURE_API_KEY='...'
export AZURE_ENDPOINT='https://your-resource.openai.azure.com/'
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

- **Package (PyPI)**: [pypi.org/project/gaik](https://pypi.org/project/gaik/)
- **Documentation**: [gaik-py/README.md](gaik-py/README.md)
- **Publishing Guide**: [docs/PUBLISHING.md](docs/PUBLISHING.md)
- **Cheatsheet (FI)**: [docs/gaik-toolkit-cheatsheet.md](docs/gaik-toolkit-cheatsheet.md)
- **Issues**: [github.com/GAIK-project/toolkit-shared-components/issues](https://github.com/GAIK-project/toolkit-shared-components/issues)
- **OpenAI Docs**: [OpenAI structured outputs guide](https://platform.openai.com/docs/guides/structured-outputs)

---

## 📄 License

MIT - see [LICENSE](LICENSE) for details
