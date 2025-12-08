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
# Set API keys (choose what you need)
export OPENAI_API_KEY='sk-...'
export ANTHROPIC_API_KEY='sk-ant-...'
export GOOGLE_API_KEY='...'
```

## Usage

### Structured Data Extraction

```bash
# Using UV
uv run python examples/extractor/extraction_example_1.py

# Or with activated venv
python examples/extractor/extraction_example_1.py
```

### PDF to Markdown Parsing

```bash
# Using UV
uv run python examples/parsers/demo_vision_simple.py

# Or with activated venv
python examples/parsers/demo_vision_simple.py
```

### Document Classification

```bash
# Using UV
uv run python examples/classifier/classification_example.py

# Or with activated venv
python examples/classifier/classification_example.py
```

## Documentation

See [docs/](../docs/) for full API documentation.
