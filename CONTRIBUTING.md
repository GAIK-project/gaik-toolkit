# Contributing to GAIK

Thank you for your interest in contributing to GAIK!

## Developer Guide: Adding New LLM Provider

GAIK uses a shared `gaik.providers` module that all library components can use.

### 1. Create provider class

File: `gaik-py/src/gaik/providers/yourprovider.py`

```python
from langchain_yourprovider import ChatYourProvider
from .base import LLMProvider, _build_model_kwargs


class YourProviderProvider(LLMProvider):
    @property
    def default_model(self) -> str:
        return "your-default-model-name"

    def create_chat_model(self, model=None, api_key=None, **kwargs):
        model_name = model or self.default_model
        model_kwargs = _build_model_kwargs(model_name, api_key=api_key, **kwargs)
        return ChatYourProvider(**model_kwargs)
```

### 2. Add dependency

File: `gaik-py/pyproject.toml`

```toml
dependencies = [
    ...
    "langchain-yourprovider>=x.x.x",
]
```

### 3. Register provider

File: `gaik-py/src/gaik/providers/__init__.py`

```python
from .yourprovider import YourProviderProvider

PROVIDERS = {
    ...
    "yourprovider": YourProviderProvider(),
}
```

### 4. Use it

```python
from gaik.extract import SchemaExtractor

extractor = SchemaExtractor(
    "Extract name and age",
    provider="yourprovider"
)
```

Done! The provider is now available to all GAIK modules.

## Testing Your Changes

### Local development with uv (recommended)

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

### Testing checklist

- ✅ All imports work
- ✅ Provider registry contains your new provider
- ✅ Package builds without errors
- ✅ Twine check passes
- ✅ Real extraction works (if API key available)

## Publishing New Versions

See detailed guide: [docs/PUBLISHING.md](docs/PUBLISHING.md)

**Quick workflow:**

1. Update version in `gaik-py/pyproject.toml`
2. Commit changes
3. Create and push tag: `git tag v<version> && git push origin main v<version>`
4. GitHub Actions automatically builds and publishes to PyPI

## Local Development

```bash
# Clone and install
git clone https://github.com/GAIK-project/gaik-toolkit.git
cd gaik-toolkit/gaik-py
pip install -e .

# Optional: include dev tools
pip install -e .[dev]

# Build and test
python -m build
twine check dist/*
```

## Questions?

- **Issues**: [github.com/GAIK-project/gaik-toolkit/issues](https://github.com/GAIK-project/gaik-toolkit/issues)
- **Documentation**: [gaik-py/README.md](gaik-py/README.md)
