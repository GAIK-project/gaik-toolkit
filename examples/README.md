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
AZURE_ENDPOINT=https://your-resource.openai.azure.com/
```

**Note:** You only need one API key to get started. The examples will work with any available provider.

### 2. Install Package

```bash
# Install from PyPI
pip install gaik

# For vision features (PDF to Markdown conversion)
pip install gaik[vision]
```

### 3. Run Examples

```bash
# Extraction demos
python examples/extract/demo_anthropic.py

# Vision demos (requires gaik[vision])
python examples/vision/demo_vision_simple.py
python examples/vision/demo_vision_parser.py invoice.pdf
```

---

## Example Categories

### 📦 [Extract](extract/) - Structured Data Extraction

Extract structured data from text using LLM providers.

- `demo_anthropic.py` - Full extraction demo with multiple patterns

[→ See extract examples](extract/)

---

### 🖼️ [Vision](vision/) - PDF to Markdown

Convert PDF documents to Markdown using vision models.

- `demo_vision_simple.py` - Basic PDF conversion
- `demo_vision_parser.py` - Advanced CLI tool

[→ See vision examples](vision/)

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
    azure_deployment="gpt-4"  # Your Azure deployment name
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

```text
ERROR: No API keys found!
```

**Solution:** Create a `.env` file with at least one API key:

```bash
OPENAI_API_KEY=sk-...
```

### Azure Configuration Error

```text
Azure extraction failed: ...
```

**Solution:** Ensure you have all required Azure variables:

```bash
AZURE_API_KEY=...
AZURE_ENDPOINT=https://your-resource.openai.azure.com/
```

Then pass your Azure deployment name when creating the extractor:

```python
SchemaExtractor(..., provider="azure", azure_deployment="gpt-4")
```

### Import Error

```text
ModuleNotFoundError: No module named 'gaik'
```

**Solution:** Install the package:

```bash
cd gaik-py
pip install -e .
```

---

## Next Steps

1. **Start with extraction:** Run `demo_anthropic.py`
2. **Try vision parsing:** Run `demo_vision_simple.py` (requires `gaik[vision]`)
3. **Check main docs:** [../gaik-py/README.md](../gaik-py/README.md) for full API reference
4. **Adapt to your needs:** Modify examples for your specific use case

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

Happy extracting! 🚀
