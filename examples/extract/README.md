# Extract Examples

## Setup

```bash
pip install gaik
```

## Environment

Choose **one** provider:

```powershell
$env:OPENAI_API_KEY='sk-...'           # OpenAI (default)
$env:ANTHROPIC_API_KEY='sk-ant-...'   # Anthropic
$env:GOOGLE_API_KEY='...'             # Google
$env:AZURE_API_KEY='...'              # Azure
$env:AZURE_ENDPOINT='https://...'
```

## Files

- `demo_anthropic.py` - Full extraction demo (basic, custom model, batch, schema inspection)

## Usage

```bash
python demo_anthropic.py
```

## Examples

### Basic

```python
extractor = SchemaExtractor(
    "Extract: name, age, occupation",
    provider="anthropic"
)
results = extractor.extract(["Alice is 25, engineer"])
```

### Providers

```python
SchemaExtractor(desc, provider="openai")     # Default
SchemaExtractor(desc, provider="anthropic")
SchemaExtractor(desc, provider="google")
SchemaExtractor(desc, provider="azure", azure_deployment="gpt-4")
```

### Custom Model

```python
SchemaExtractor(desc, provider="anthropic", model="claude-opus-4-20250514")
```

### Batch

```python
results = extractor.extract([doc1, doc2, doc3])
```

### Pre-defined Schema

```python
requirements = [
    FieldRequirement(field_name="name", field_type="str"),
    FieldRequirement(field_name="age", field_type="int")
]
extractor = SchemaExtractor(requirements=requirements)
```
