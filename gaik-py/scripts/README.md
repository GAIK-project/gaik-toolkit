# CI/CD Scripts

This directory contains scripts used for CI/CD pipelines and release automation.

## Scripts

### verify_installation.py

Verifies that the GAIK package was installed correctly. This script:
- Tests all module imports
- Checks public API availability
- Validates provider registry
- Tests basic functionality without making API calls

**Used by:** `.github/workflows/test.yml` and `.github/workflows/publish.yml`

**Run manually:**
```bash
python scripts/verify_installation.py
```

### validate_version.py

Validates that the git tag matches the version in `pyproject.toml`.

**Used by:** `.github/workflows/publish.yml` during release process

**Run manually:**
```bash
python scripts/validate_version.py v0.3.0
```

## Note

These are CI/CD tools, not unit tests. For unit tests, see the `tests/` directory.
