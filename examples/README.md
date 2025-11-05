# GAIK Toolkit - Examples

Comprehensive examples demonstrating all features of the GAIK toolkit.

## Quick Start

### 1. Setup Environment

Create a `.env` file in the project root with your API keys:

```bash
# OpenAI (default provider)
OPENAI_API_KEY=sk-...

# Anthropic Claude
ANTHROPIC_API_KEY=sk-ant-...

# Google Gemini
GOOGLE_API_KEY=...

# Azure OpenAI
AZURE_API_KEY=...
AZURE_API_BASE=https://your-resource.openai.azure.com/
AZURE_DEPLOYMENT=gpt-4  # Optional: your deployment name
```

**Note:** You only need one API key to get started. The examples will work with any available provider.

### 2. Install Dependencies

```bash
# With uv (recommended)
cd gaik-py
uv sync
```

Or with standard pip:

```bash
pip install -e gaik-py
```

### 3. Run Examples

```bash
# From project root
python examples/01_getting_started.py
python examples/02_pydantic_schemas.py
python examples/03_real_world_use_cases.py
```

---

## Examples

### 🚀 [01_getting_started.py](01_getting_started.py)

**Best for:** First-time users, quick overview

Learn the basics in 5 examples:

- ✅ Basic extraction with natural language descriptions
- ✅ Batch processing multiple documents
- ✅ Schema inspection (without API calls)
- ✅ Switching providers (OpenAI, Anthropic, Google, Azure)
- ✅ Complex schemas with lists and nested data

```bash
python examples/01_getting_started.py
```

---

### 🔧 [02_pydantic_schemas.py](02_pydantic_schemas.py)

**Best for:** Understanding schemas, integration

Deep dive into Pydantic schemas:

- ✅ Inspect generated Pydantic models
- ✅ Export to JSON Schema format
- ✅ Use Pydantic validation features
- ✅ Work with nested structures
- ✅ Field introspection

```bash
python examples/02_pydantic_schemas.py
```

---

### 💼 [03_real_world_use_cases.py](03_real_world_use_cases.py)

**Best for:** Practical applications, production ideas

Real-world business scenarios:

- 📄 **Invoice Processing** - Automated accounting
- 💬 **Customer Feedback** - Sentiment analysis
- 👤 **Resume Parsing** - Recruitment automation
- 🛍️ **Product Catalogs** - E-commerce data
- 📰 **News Metadata** - Content management
- 📧 **Email Classification** - Support routing

```bash
python examples/03_real_world_use_cases.py
```

---

### � [demo_anthropic.py](demo_anthropic.py)

**Best for:** Anthropic Claude provider demo, modular examples

Simple, modular demonstrations:

- ✅ Basic extraction with Anthropic
- ✅ Custom model selection (Claude Opus)
- ✅ Schema inspection
- ✅ Custom LangChain client
- ✅ Batch extraction
- ✅ Pre-defined requirements (skip LLM parsing)

**Note:** Uses LangChain's `with_structured_output()` under the hood.

```bash
python examples/demo_anthropic.py
```

---

## Understanding Structured Output

GAIK automatically converts natural language descriptions into structured data:

### Input (Natural Language)

```python
description = """
Extract from text:
- product_name: Name of the product
- price: Price in USD (as a number)
- rating: Rating from 1-5
"""
```

### Processing

GAIK generates a Pydantic schema:

```python
class Product_Extraction(BaseModel):
    product_name: str
    price: float
    rating: float
```

### Output (Structured Data)

```python
{
    "product_name": "SuperWidget",
    "price": 29.99,
    "rating": 4.5
}
```

---

## Supported Providers

| Provider             | Default Model     | Environment Variable               |
| -------------------- | ----------------- | ---------------------------------- |
| **OpenAI** (default) | gpt-4o-mini       | `OPENAI_API_KEY`                   |
| **Anthropic**        | claude-sonnet-4-5 | `ANTHROPIC_API_KEY`                |
| **Google**           | gemini-2.5-flash  | `GOOGLE_API_KEY`                   |
| **Azure OpenAI**     | (your deployment) | `AZURE_API_KEY` + `AZURE_API_BASE` |

### Switching Providers

```python
# OpenAI (default)
extractor = SchemaExtractor(description)

# Anthropic
extractor = SchemaExtractor(description, provider="anthropic")

# Google
extractor = SchemaExtractor(description, provider="google")

# Azure
extractor = SchemaExtractor(
    description,
    provider="azure",
    api_key="...",
    azure_endpoint="...",
    azure_deployment="gpt-4"
)
```

---

## Common Use Cases

### 1. Document Processing

Extract structured data from invoices, receipts, contracts, or forms.

**Example:** Invoice parsing → Accounting system

### 2. Content Analysis

Analyze feedback, reviews, social media posts, or support tickets.

**Example:** Customer reviews → Sentiment analysis → Product insights

### 3. Data Integration

Parse emails, PDFs, or web content into structured formats.

**Example:** Email → Extract contact info → CRM system

### 4. Catalog Management

Structure product descriptions, specifications, or listings.

**Example:** Product text → Structured catalog → Database

### 5. Metadata Extraction

Extract metadata from articles, documents, or media.

**Example:** News articles → Tags, categories → Content management

---

## Working with Schemas

### Get JSON Schema

```python
extractor = SchemaExtractor(description)
json_schema = extractor.model.model_json_schema()

# Use with:
# - API documentation (OpenAPI/Swagger)
# - Form generators
# - Other programming languages
# - Database schemas
```

### Inspect Fields

```python
# Get field names
field_names = extractor.field_names

# Get field specifications
for field in extractor.fields:
    print(f"{field.field_name}: {field.field_type}")
```

### Access Pydantic Model

```python
# Get the generated Pydantic model
model = extractor.model

# Use Pydantic features
instance = model(**data)
json_output = instance.model_dump_json()
dict_output = instance.model_dump()
```

---

## Tips and Best Practices

### 1. Write Clear Descriptions

```python
# Good: Specific and clear
"""
Extract:
- invoice_number: The invoice reference number (string)
- amount: Total amount in EUR (number)
- due_date: Payment due date (ISO format YYYY-MM-DD)
"""

# Less optimal: Vague
"""
Get the invoice info
"""
```

### 2. Specify Data Types

```python
"""
Extract:
- price: Price in USD (as a number)  # Will be float
- quantity: Number of items (integer)
- is_available: Stock status (boolean)
- tags: List of tags (list of strings)
"""
```

### 3. Handle Optional Fields

```python
"""
Extract:
- customer_name: Customer's full name
- phone: Phone number (optional)
- notes: Additional notes (optional)
"""
```

### 4. Batch Processing

```python
# More efficient than processing one-by-one
documents = [doc1, doc2, doc3, ...]
results = extractor.extract(documents)
```

### 5. Reuse Extractors

```python
# Create once, use multiple times
extractor = SchemaExtractor(description)

# Process different batches
batch1_results = extractor.extract(batch1)
batch2_results = extractor.extract(batch2)
```

---

## Troubleshooting

### API Key Not Found

```
ERROR: No API keys found!
```

**Solution:** Create a `.env` file with at least one API key:

```bash
OPENAI_API_KEY=sk-...
```

### Azure Configuration Error

```
Azure extraction failed: ...
```

**Solution:** Ensure you have all required Azure variables:

```bash
AZURE_API_KEY=...
AZURE_API_BASE=https://your-resource.openai.azure.com/
AZURE_DEPLOYMENT=gpt-4  # Your deployment name
```

### Import Error

```
ModuleNotFoundError: No module named 'gaik'
```

**Solution:** Install the package:

```bash
cd gaik-py
pip install -e .
```

---

## Next Steps

1. **Start with basics:** Run `01_getting_started.py`
2. **Understand schemas:** Run `02_pydantic_schemas.py`
3. **Explore use cases:** Run `03_real_world_use_cases.py`
4. **Verify installation:** Run `test_gaik_installation.py` (no API needed)
5. **Test providers:** Run `test_real_extraction.py` (requires API key)
6. **Adapt to your needs:** Modify examples for your specific use case

---

## Additional Resources

- **Main README:** [../README.md](../README.md)
- **Package Documentation:** [../gaik-py/README.md](../gaik-py/README.md)
- **Publishing Guide:** [../docs/PUBLISHING.md](../docs/PUBLISHING.md)
- **Cheatsheet (Finnish):** [../docs/gaik-toolkit-cheatsheet.md](../docs/gaik-toolkit-cheatsheet.md)

---

## Questions or Issues?

- **GitHub Issues:** [github.com/GAIK-project/toolkit-shared-components/issues](https://github.com/GAIK-project/toolkit-shared-components/issues)
- **Documentation:** Check the main README and package documentation

---

**Happy extracting! 🚀**
