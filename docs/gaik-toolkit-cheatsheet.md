# GAIK Toolkit – Quick Reference

## What is it?

- GAIK Toolkit is a Python library for AI/ML development with multi-provider LLM support
- Available on PyPI - install and use immediately in any project
- All functionality runs locally in your codebase—no external service dependency

## How do I install it?

```bash
# Install from PyPI
pip install gaik

# Or with uv (faster alternative)
uv pip install gaik

# With optional vision parser support
pip install gaik[vision]
```

Installation works like any standard Python package.

## Fastest way to try it

```python
from gaik.extract import SchemaExtractor

# Default OpenAI provider
extractor = SchemaExtractor("Extract customer name and age from text")
result = extractor.extract(["Alice is 25 years old."])
print(result[0])
# {'name': 'Alice', 'age': 25}

# Switch to Anthropic Claude
extractor = SchemaExtractor(
    "Extract customer name and age from text",
    provider="anthropic"
)

# Or Google Gemini
extractor = SchemaExtractor(
    "Extract customer name and age from text",
    provider="google"
)
```

- Multi-provider support: OpenAI, Anthropic, Google, Azure
- `SchemaExtractor` builds the schema automatically and returns clean Python objects
- Easy provider switching with single parameter
- Further examples live in [gaik-py/README.md](../gaik-py/README.md) and the [`examples/`](../examples/) directory

## Environment variables

- The library supports multiple LLM providers - choose which one to use by setting the appropriate API key:

**OpenAI (default):**

```powershell
# PowerShell
$Env:OPENAI_API_KEY = "sk-..."
# Bash/Linux/Mac
export OPENAI_API_KEY='sk-...'
```

**Anthropic:**

```powershell
$Env:ANTHROPIC_API_KEY = "sk-ant-..."
export ANTHROPIC_API_KEY='sk-ant-...'
```

**Google:**

```powershell
$Env:GOOGLE_API_KEY = "..."
export GOOGLE_API_KEY='...'
```

**Azure OpenAI:**

```powershell
$Env:AZURE_API_KEY = "..."
$Env:AZURE_ENDPOINT = "https://your-resource.openai.azure.com/"
```

## Local development

- After installation the package code is fully available locally.
- We can iterate and test new capabilities without pulling in additional external services.

## Release process

- GitHub Actions automatically publishes to PyPI whenever we cut a version and push a tag.
- Releases use the `release` environment for added deployment protection.

## Executive summary

- Easy to install and invoke just like familiar third-party Python libraries
- Multi-provider support (OpenAI, Anthropic, Google, Azure) - choose what works best for you
- Requires only one API key for your chosen provider
- Release automation is in place; promotion to the official PyPI feed is the next step

## View toward JavaScript/Node.js

- We can deliver equivalent functionality for JavaScript/Node.js, but it would require a dedicated npm package—Python modules cannot be reused directly.
- The implementation style can be class-based, functional, or a hybrid; we will choose the shape that best matches the use case when we build it.
