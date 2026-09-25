# Examples

Quick start examples for GAIK toolkit.

## Installation

```bash
# Install from PyPI
pip install gaik[all]

# Or for development
pip install -e ".[all]"

# If using UV (recommended)
uv pip install gaik[all]
```

## Environment Variables

```bash
# For OpenAI
export OPENAI_API_KEY='sk-...'

# For Azure OpenAI (default in examples)
export AZURE_API_KEY='...'
export AZURE_ENDPOINT='https://your-resource.openai.azure.com/'
export AZURE_DEPLOYMENT='gpt-6-luna'            # your deployment name; this is the default
export AZURE_API_VERSION='2025-03-01-preview'   # optional; this is the default
```

Extraction and classification need a deployment that supports structured outputs.
Other providers (Google, Anthropic, CSC Aitta, OpenAI-compatible servers, LiteLLM) are
configured with `get_llm_config()`; see `software_components/llm/` and the
[multi-provider guide](https://gaik-project.github.io/gaik-toolkit/toolkit/multi-provider-llm/).

## Usage

### Structured Data Extraction

```bash
# Using UV
uv run python examples/software_components/extractor/extraction_example_1.py

# Or with activated venv
python examples/software_components/extractor/extraction_example_1.py
```

### PDF to Markdown Parsing

```bash
# Using UV
uv run python examples/software_components/parsers/demo_vision_simple.py

# Or with activated venv
python examples/software_components/parsers/demo_vision_simple.py
```

### Document Classification

```bash
# Using UV
uv run python examples/software_components/classifier/classification_example.py

# Or with activated venv
python examples/software_components/classifier/classification_example.py
```

