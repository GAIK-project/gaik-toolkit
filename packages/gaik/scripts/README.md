# CI/CD Scripts

This directory stores helper scripts that CI workflows call after building or installing the package. Keep them lightweight and dependency-free so they can run in both local and GitHub-hosted environments.

## Available scripts

| Script                   | Purpose                                                                    |
| ------------------------ | -------------------------------------------------------------------------- |
| `verify_installation.py` | Smoke test that imports and basic utilities work after `pip install gaik`. |

### verify_installation.py

This script performs quick runtime checks without making network calls:

- Imports the public API (`gaik`, `gaik.extract`, `gaik.providers`).
- Instantiates a few Pydantic models (no LLM providers needed).
- Confirms required providers are registered.
- Prints a ✅ success message and exits 0.

**Used by:** `test.yml` (after unit tests) and `publish.yml` (after uploading to PyPI).

Run manually from the repo root:

```bash
python packages/python/gaik/scripts/verify_installation.py
```

> Unit tests now live next to the modules they cover (e.g., `src/gaik/extract/tests`). These scripts are only for CI smoke checks.
