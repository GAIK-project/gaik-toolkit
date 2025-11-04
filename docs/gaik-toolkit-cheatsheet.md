# GAIK Toolkit – Quick Reference

## What is it?

- GAIK Toolkit is our Python library (currently internal, aiming for a wider release) that bundles AI tooling similar to public packages such as `openai`.
- The package can be installed from Test PyPI today and dropped into any project with a single command.
- Once installed, all functionality lives locally in your codebase—no external API service dependency for the library itself.

## How do I install it?

```bash
# Current install from Test PyPI
pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ gaik

# Future official PyPI release
# pip install gaik
```

- Installation works exactly like any other Python package.
- When we move to the official PyPI registry, the command shortens to `pip install gaik` and the package becomes discoverable as a stable release.

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
$Env:AZURE_OPENAI_API_KEY = "..."
$Env:AZURE_OPENAI_ENDPOINT = "https://your-resource.openai.azure.com/"
```

## Local development

- After installation the package code is fully available locally.
- We can iterate and test new capabilities without pulling in additional external services.

## Release process

- GitHub Actions automatically publishes to Test PyPI whenever we cut a version and push a tag.
- The next milestone is an official PyPI release, which makes the package easier to find and simplifies installation.

## Executive summary

- Easy to install and invoke just like familiar third-party Python libraries
- Multi-provider support (OpenAI, Anthropic, Google, Azure) - choose what works best for you
- Requires only one API key for your chosen provider
- Release automation is in place; promotion to the official PyPI feed is the next step

## View toward JavaScript/Node.js

- We can deliver equivalent functionality for JavaScript/Node.js, but it would require a dedicated npm package—Python modules cannot be reused directly.
- The implementation style can be class-based, functional, or a hybrid; we will choose the shape that best matches the use case when we build it.
