# 📋 Contributing to GAIK - Quick Guide

Simple cheatsheet for developers new to this project.

---

## 🚀 Quick Start

```bash
# Clone and setup
git clone https://github.com/GAIK-project/gaik-toolkit.git
cd gaik-toolkit/gaik-py

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
gaik-py/src/gaik/
├── extract/          # Text/structured data extraction
├── parsers/          # Vision, PDF, and other parsers
├── providers/        # LLM provider integrations
└── [your-feature]/   # New standalone modules (e.g., audio, video)
```

### Add a New Standalone Feature

For completely new capabilities (e.g., audio transcription, video processing) that don't fit into existing modules:

1. **Create your module** → `gaik-py/src/gaik/[feature-name]/`

   Example: Whisper audio transcription

   ```text
   gaik-py/src/gaik/audio/
   ├── __init__.py
   ├── transcriber.py
   └── utils.py
   ```

2. **Add dependencies** → `gaik-py/pyproject.toml`

   Create a new optional dependency group:

   ```toml
   [project.optional-dependencies]
   audio = [
       "openai-whisper>=1.0.0",
       "torch>=2.0.0",
   ]
   all = ["gaik[extract,vision,audio]"]  # Update all group
   ```

3. **Export public API** → `gaik-py/src/gaik/__init__.py`

   ```python
   from .audio import AudioTranscriber
   ```

4. **Add examples** → `examples/audio/`

   Include README and usage examples

### Extend Existing Modules

For features that fit into existing modules:

- **Add parser:** `gaik-py/src/gaik/parsers/your_parser.py`
- **Add extractor:** `gaik-py/src/gaik/extract/your_extractor.py`
- **Add LLM provider:** `gaik-py/src/gaik/providers/your_provider.py` (see existing providers for examples)

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

**Location:** `gaik-py/pyproject.toml` under `[project.optional-dependencies]`

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
cd gaik-py

# Install dev dependencies (includes pytest)
pip install -e ".[extract,dev]"

# Run all tests
pytest

# Run tests with coverage report
pytest --cov=gaik --cov-report=term

# Run specific test file
pytest tests/test_extract.py

# Run tests in verbose mode
pytest -v
```

### Writing Tests

**Add unit tests to `gaik-py/tests/`:**

- Use pytest framework
- Follow naming: `test_*.py` or `*_test.py`
- Mock external API calls (no real API keys in tests)
- See `tests/test_extract.py` for examples

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
gaik-py/
├── tests/              # Unit tests (pytest)
│   ├── conftest.py    # Shared fixtures
│   └── test_*.py      # Test files
├── scripts/           # CI/CD verification scripts
│   ├── verify_installation.py
│   └── validate_version.py
└── examples/          # Usage examples
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

**GitHub Actions handles everything automatically!**

### Automated Release Steps

1. **Test first!** → Push changes to `main` or `dev` branch

   ```bash
   git add .
   git commit -m "Your changes"
   git push origin main
   ```

   **Check tests pass:** GitHub → Actions → "Run Tests" workflow
   - Tests run automatically on every push to main/dev
   - Tests must pass before you can release
   - Tests now include all [extract] dependencies

2. **Update version** → Edit `gaik-py/pyproject.toml`

   ```toml
   version = "0.3.0"  # Bump version number
   ```

3. **Commit version bump**

   ```bash
   git add gaik-py/pyproject.toml
   git commit -m "Bump to v0.3.0"
   git push origin main
   ```

4. **Create and push git tag**

   ```bash
   git tag v0.3.0
   git push origin v0.3.0
   ```

5. **Done!** 🎉 GitHub Actions automatically:
   - ✅ Runs all tests first (Python 3.10, 3.11, 3.12)
   - ✅ Only publishes if tests pass
   - Builds the package (`python -m build`)
   - Validates metadata (`twine check dist/*`)
   - Publishes to PyPI (`twine upload dist/*`)
   - Creates GitHub Release with notes

**Check progress:** GitHub → Actions tab → "Publish to Production PyPI" workflow

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

### Manual Release (Emergency Only)

If GitHub Actions fails, maintainers can publish manually:

```bash
cd gaik-py

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
├── gaik-py/                          # 📦 PyPI package (published)
│   ├── src/gaik/                     # Source code
│   │   ├── extract/                  # Data extraction module
│   │   ├── parsers/                  # Vision/PDF parsing
│   │   └── providers/                # LLM provider implementations
│   ├── tests/                        # 🧪 Unit tests (pytest)
│   ├── scripts/                      # 🔧 CI/CD verification scripts
│   ├── pyproject.toml                # Package config & dependencies
│   └── README.md                     # Package documentation
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

- Production-ready code → `gaik-py/src/gaik/`
- Unit tests → `gaik-py/tests/`
- CI/CD scripts → `gaik-py/scripts/`
- Code in development → `dev/` (see [dev/README.md](dev/README.md))
- Usage examples → `examples/`

---

## ❓ Questions?

- **Issues**: [github.com/GAIK-project/gaik-toolkit/issues](https://github.com/GAIK-project/gaik-toolkit/issues)
- **Documentation**: [gaik-py/README.md](gaik-py/README.md)
