# 📋 Contributing to GAIK - Quick Guide

Simple cheatsheet for developers new to this project.

---

## 🚀 Quick Start

```bash
# Clone and setup
git clone https://github.com/GAIK-project/gaik-toolkit.git
cd gaik-toolkit/packages/python/gaik

# Create virtual environment and install
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # Linux/Mac

# Install for development (all features)
pip install -e .[all]

# Test it works
python ../examples/extract/demo_anthropic.py
python ../examples/vision/demo_vision_simple.py
```

**Installation options:**

```bash
# All features (recommended for development)
pip install -e .[all]

# Extract only (data extraction with all LLM providers)
pip install -e .[extract]

# Vision only (PDF parsing)
pip install -e .[vision]
```

---

## ➕ Adding New Code

### Project Module Structure

```text
packages/python/gaik/src/gaik/
├── extract/          # Text/structured data extraction (+ tests)
├── parsers/          # Vision, PDF, and other parsers (+ tests)
├── providers/        # LLM provider integrations (+ tests)
└── [your-feature]/   # New standalone modules (e.g., audio, video)
```

### Add a New Standalone Feature

For completely new capabilities (e.g., audio transcription, video processing) that don't fit into existing modules:

1. **Create your module** → `packages/python/gaik/src/gaik/[feature-name]/`

   Example: Whisper audio transcription

   ```text
   packages/python/gaik/src/gaik/audio/
   ├── __init__.py
   ├── transcriber.py
   └── utils.py
   ```

2. **Add dependencies** → `packages/python/gaik/pyproject.toml`

   Create a new optional dependency group:

   ```toml
   [project.optional-dependencies]
   audio = [
       "openai-whisper>=1.0.0",
       "torch>=2.0.0",
   ]
   all = ["gaik[extract,vision,audio]"]  # Update all group
   ```

3. **Export public API** → `packages/python/gaik/src/gaik/__init__.py`

   ```python
   from .audio import AudioTranscriber
   ```

4. **Add examples** → `examples/audio/`

   Include README and usage examples

### Extend Existing Modules

For features that fit into existing modules, follow these step-by-step guides:

#### Add a New Parser

Parsers convert documents (PDFs, images, etc.) to structured formats.

1. **Create parser file** → `packages/python/gaik/src/gaik/parsers/your_parser.py`

   ```python
   """Your parser description.

   Example
   -------
   >>> from gaik.parsers import YourParser
   >>> parser = YourParser()
   >>> result = parser.parse("document.pdf")
   """

   from __future__ import annotations

   class YourParser:
       """Parser that converts X to Y."""

       def __init__(self, config: dict | None = None):
           self.config = config or {}

       def parse(self, input_path: str) -> str:
           """Parse input and return result."""
           # Your implementation here
           return result
   ```

2. **Export in module** → `packages/python/gaik/src/gaik/parsers/__init__.py`

   ```python
   from .your_parser import YourParser

   __all__ = [..., "YourParser"]  # Add to existing exports
   ```

3. **Add dependencies** (if needed) → `packages/python/gaik/pyproject.toml`

   ```toml
   [project.optional-dependencies]
   vision = [
       "your-library>=1.0.0",  # Add here
   ]
   ```

4. **Add tests** → `packages/python/gaik/src/gaik/parsers/tests/test_your_parser.py`

   ```python
   from gaik.parsers import YourParser

   def test_your_parser():
       parser = YourParser()
       result = parser.parse("test_input")
       assert result == "expected_output"
   ```

5. **Add usage example** → `examples/your_parser/demo.py`

   Include README explaining how to use your parser.

6. **Test locally**

   ```bash
   cd packages/python/gaik
   pip install -e .[vision,dev]
   pytest src/gaik/parsers/tests/test_your_parser.py
   ```

#### Add a New Extractor

Follow similar pattern in `packages/python/gaik/src/gaik/extract/` (see existing extractors for examples)

#### Add a New LLM Provider

Follow the `BaseProvider` interface in `packages/python/gaik/src/gaik/providers/base.py` (see existing providers for examples)

---

## 📦 Dependencies - Feature Groups

**GAIK uses optional dependency groups** - users install only what they need!

### Feature Groups

| Group       | Purpose                                | Dependencies                                             |
| ----------- | -------------------------------------- | -------------------------------------------------------- |
| `[extract]` | Data extraction with all LLM providers | langchain-\* packages (OpenAI, Anthropic, Google, Azure) |
| `[vision]`  | PDF/image parsing                      | openai, pdf2image, pillow                                |
| `[all]`     | All features                           | extract + vision                                         |

### Naming Convention

- **LangChain providers:** `langchain-{provider}` (e.g., `langchain-openai`, `langchain-anthropic`)
- **Vision tools:** `pdf2image`, `pillow`, `openai`
- **Core utilities:** `pydantic` (always installed)

### Where to Add Dependencies

**Location:** `packages/python/gaik/pyproject.toml` under `[project.optional-dependencies]`

**For extract providers:**

```toml
[project.optional-dependencies]
extract = [
    "langchain-core>=1.0.3",
    "langchain-yourprovider>=1.0.0",  # Add here
]
```

**For vision features:**

```toml
vision = [
    "openai>=2.7",
    "your-vision-tool>=1.0.0",  # Add here
]
```

**After adding:** Reinstall with `pip install -e .[all]`

---

## 🧪 Testing

**GAIK uses pytest for unit testing:**

### Running Tests Locally

```bash
cd packages/python/gaik

# Install dev dependencies (includes pytest)
pip install -e ".[extract,dev]"

# Run all tests
pytest

# Run tests with coverage report
pytest --cov=gaik --cov-report=term

# Run specific test file
pytest src/gaik/extract/tests/test_extract.py

# Run tests in verbose mode
pytest -v
```

### Writing Tests

**Add unit tests next to the code they cover** inside `src/gaik/<feature>/tests/`:

- Use pytest framework
- Follow naming: `test_*.py` or `*_test.py`
- Mock external API calls (no real API keys in tests)
- See `src/gaik/extract/tests/test_extract.py` for examples

**Example test:**

```python
def test_field_spec_creation():
    field = FieldSpec(
        field_name="test",
        field_type="str",
        description="Test field",
        required=True
    )
    assert field.field_name == "test"
```

**Add usage examples to `examples/`:**

- Shows real-world usage
- Helps users understand your feature

### Test Structure

```text
packages/python/gaik/
├── src/gaik/
│   ├── extract/
│   │   ├── ...
│   │   └── tests/          # Module-specific tests
│   │       ├── conftest.py
│   │       └── test_*.py
│   └── <other modules>/
│       └── tests/
├── scripts/
│   └── verify_installation.py
└── README.md
```

### Code Quality

```bash
# Format code
ruff format src/gaik/

# Check linting
ruff check --fix src/gaik/
```

### Before Committing

- ✅ Unit tests added for new features
- ✅ All tests pass locally (`pytest`)
- ✅ Code formatted (`ruff format`)
- ✅ No linting errors (`ruff check`)

---

## 🚀 Release Process (Maintainers Only)

**GitHub Actions + `setuptools_scm` manage releases automatically.**

### Automated Release Steps

1. **Make sure main/dev is green.** Tests run on every push via `Run Tests` workflow.

2. **Create a semantic version tag** once changes are merged:

   ```bash
   git tag v0.3.0
   git push origin v0.3.0
   ```

   > Tag format **must** be `vX.Y.Z`. The package version is derived from this tag.

3. **Done!** 🎉 The publish workflow will:
   - ✅ Re-run the shared `Run Tests` workflow
   - ✅ Build the package from `packages/python/gaik`
   - ✅ Validate metadata with Twine
   - ✅ Upload to PyPI
   - ✅ Smoke-test `pip install gaik`
   - ✅ Attach artifacts + GitHub Release notes

**Monitor progress:** GitHub → Actions → "Publish to Production PyPI" workflow

### Testing Pipeline Without Release

You can test the publish workflow without actually creating a tag:

```bash
# Go to GitHub → Actions → "Publish to Production PyPI"
# Click "Run workflow" → Select branch → Run
```

This triggers `workflow_dispatch` to test the build process without publishing.

### Troubleshooting

#### GitHub release failed with status: 403

✅ **FIXED!** The workflow now has proper permissions:

- `contents: write` - Creates releases
- `pull-requests: read` - Generates release notes

#### test (3.11) failed

✅ **FIXED!** Tests now install `[extract]` dependencies, so all LangChain packages are available.

#### Tests fail but I want to publish anyway

❌ **Not possible!** The publish workflow requires tests to pass first. This is by design - fix the tests before releasing.

#### How do I test without creating a tag?

✅ Push to `main` or `dev` branch - tests run automatically. Or use `workflow_dispatch` button in GitHub Actions.

#### Publish job fails with "No valid version" or similar

❌ **Problem:** The tag name does not match `vX.Y.Z` or the commit you tagged is missing package artifacts.

✅ **Fix:** Delete the incorrect tag locally/remotely and recreate it with the correct semantic version:

```bash
git tag -d bad-tag
git push origin --delete bad-tag
git tag v0.X.Y
git push origin v0.X.Y
```

### Manual Release (Emergency Only)

If GitHub Actions fails, maintainers can publish manually:

```bash
cd packages/python/gaik

# Build package
python -m build

# Validate
twine check dist/*

# Upload to PyPI (requires PYPI_API_TOKEN)
twine upload dist/*

# Create GitHub release (requires gh CLI)
gh release create v0.3.0 --generate-notes dist/*
```

> **Note:** This is rarely needed. GitHub Actions is the recommended way to publish.

---

## 📁 Project Structure Reference

```text
gaik-toolkit/
├── packages/
│   └── python/
│       └── gaik/                     # 📦 PyPI package (published)
│           ├── src/gaik/             # Source + co-located tests
│           ├── scripts/              # 🔧 Verification helpers
│           ├── pyproject.toml        # Package config & dependencies
│           └── README.md             # Package documentation
│
├── dev/                              # 🚧 Work in progress (not published)
│   ├── experimental/                 # Experimental features
│   ├── features/                     # Features under development
│   └── README.md                     # Dev workflow guide
│
├── examples/                         # 📚 Usage examples (not published)
│   ├── extract/                      # Extraction demos
│   └── vision/                       # Vision parsing demos
│
└── .github/workflows/                # 🤖 CI/CD pipelines
    ├── test.yml                      # Run tests on PR/push
    └── publish.yml                   # Auto-publish to PyPI
```

**Where to add code:**

- Production-ready code → `packages/python/gaik/src/gaik/`
- Unit tests → `packages/python/gaik/src/gaik/**/tests/`
- CI/CD scripts → `packages/python/gaik/scripts/`
- Code in development → `dev/` (see [dev/README.md](dev/README.md))
- Usage examples → `examples/`

---

## ❓ Questions?

- **Issues**: [github.com/GAIK-project/gaik-toolkit/issues](https://github.com/GAIK-project/gaik-toolkit/issues)
- **Documentation**: [packages/python/gaik/README.md](packages/python/gaik/README.md)
