# GAIK - General AI Kit

[![PyPI version](https://badge.fury.io/py/gaik.svg)](https://pypi.org/project/gaik/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://github.com/GAIK-project/toolkit-shared-components/actions/workflows/test.yml/badge.svg)](https://github.com/GAIK-project/toolkit-shared-components/actions)

Shared Python components for AI/ML projects - production-ready utilities for schema extraction with multi-provider LLM support (OpenAI, Anthropic, Azure, Google).

---

## Quick Start

```bash
pip install gaik[extract]
```

```python
from gaik.extract import SchemaExtractor

extractor = SchemaExtractor("Extract name and age from text")
results = extractor.extract(["Alice is 25 years old"])
print(results[0])  # {'name': 'Alice', 'age': 25}
```

**Full documentation:** [gaik-py/README.md](gaik-py/README.md)

---

## Features

- **Multi-provider LLM support** - OpenAI, Anthropic (Claude), Google (Gemini), Azure
- **Guaranteed structure** - API-enforced outputs via LangChain
- **Type-safe** - Pydantic models, no `eval()` or code generation
- **Vision parsing** - PDF and image extraction (optional)

---

## Repository Structure

```
toolkit-shared-components/
├── gaik-py/              # Python package (pip install gaik)
│   ├── src/gaik/         # Source code
│   │   ├── extract/      # Schema extraction
│   │   ├── providers/    # LLM providers
│   │   └── parsers/      # Vision/PDF parsing
│   ├── tests/            # Unit tests (pytest)
│   ├── scripts/          # CI/CD verification
│   └── pyproject.toml    # Package config
├── examples/             # Usage examples
├── docs/                 # Documentation
└── .github/workflows/    # CI/CD (tests on push, publish on tag)
```

---

## Installation Options

```bash
pip install gaik             # Core only
pip install gaik[extract]    # + LangChain providers
pip install gaik[vision]     # + PDF/image parsing
pip install gaik[all]        # All features
```

---

## API Keys

Set environment variable for your provider:

```bash
export OPENAI_API_KEY='sk-...'          # OpenAI (default)
export ANTHROPIC_API_KEY='sk-ant-...'  # Anthropic Claude
export GOOGLE_API_KEY='...'             # Google Gemini
```

Or pass directly:

```python
extractor = SchemaExtractor("...", provider="anthropic", api_key="your-key")
```

---

## Resources

- **PyPI Package**: [pypi.org/project/gaik](https://pypi.org/project/gaik/)
- **Full Documentation**: [gaik-py/README.md](gaik-py/README.md)
- **Contributing Guide**: [CONTRIBUTING.md](CONTRIBUTING.md)
- **Issues**: [GitHub Issues](https://github.com/GAIK-project/toolkit-shared-components/issues)

---

## License

MIT - see [LICENSE](LICENSE) for details
