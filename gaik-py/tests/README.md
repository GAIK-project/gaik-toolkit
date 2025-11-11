# Unit Tests

This directory contains pytest-based unit tests for the GAIK package.

## Running Tests

```bash
# From gaik-py directory
cd gaik-py

# Install dev dependencies (includes pytest)
pip install -e ".[extract,dev]"

# Run all tests
pytest

# Run with coverage
pytest --cov=gaik --cov-report=term

# Run specific test
pytest tests/test_extract.py -v
```

## Writing Tests

### Test Structure

- `conftest.py` - Shared pytest fixtures
- `test_*.py` - Individual test modules

### Guidelines

1. **Use pytest framework**
   - Name test files `test_*.py` or `*_test.py`
   - Name test functions `test_*`
   - Use pytest fixtures from `conftest.py`

2. **Mock external dependencies**
   - No real API calls in tests
   - Use `pytest-mock` or `unittest.mock`
   - Mock LLM responses

3. **Test organization**
   - Group related tests in classes
   - One test file per module
   - Keep tests simple and focused

### Example Test

```python
def test_field_spec_creation(sample_field_spec):
    """Test FieldSpec initialization."""
    assert sample_field_spec.field_name == "test_field"
    assert sample_field_spec.required is True
```

## Coverage

Target: 80%+ code coverage

Check coverage:
```bash
pytest --cov=gaik --cov-report=html
# Open htmlcov/index.html in browser
```

## CI/CD

Tests run automatically in GitHub Actions:
- On every push to `main` or `dev` branches
- On every pull request
- Before publishing to PyPI

See [.github/workflows/test.yml](../../.github/workflows/test.yml)

## Not Tests?

- CI/CD verification scripts → `scripts/` directory
- Usage examples → `examples/` directory
