# Production PyPI Publishing Guide

Quick reference for publishing to production PyPI when ready to move from Test PyPI.

---

## 🚀 One-Time Setup

### 1. Create PyPI Account & Token

1. Register: <https://pypi.org/account/register/>
2. Generate API token: <https://pypi.org/manage/account/token/>
3. Add to GitHub: Settings → Secrets → Actions → New secret
   - Name: `PYPI_API_TOKEN`
   - Value: `pypi-...` (your token)

### 2. Create Production Workflow

Create `.github/workflows/release-pypi.yml`:

```yaml
name: Publish to Production PyPI

on:
  push:
    tags:
      - "v*.*.*"

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Install tools
        run: pip install build twine

      - name: Build
        working-directory: gaik-py
        run: python -m build

      - name: Publish to PyPI
        working-directory: gaik-py
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
        run: twine upload dist/*
```

**Key differences from Test PyPI:**

- Repository URL: `https://upload.pypi.org/legacy/` (default, can omit)
- Secret: `PYPI_API_TOKEN` (not TEST_PYPI_API_TOKEN)
- No `--skip-existing` flag

---

## 📦 Publishing New Version

### Quick Steps

```bash
# 1. Update version in gaik-py/pyproject.toml
# Example: version = "0.3.0" (replace with the desired release number)

# 2. Commit changes
git add gaik-py/pyproject.toml
git commit -m "Bump version to <new-version>"

# 3. Validate version match (recommended)
python gaik-py/tests/validate_version.py v<new-version>

# 4. Create tag and push
git tag v<new-version>
git push origin main v<new-version>

# 5. GitHub Actions validates and publishes automatically
```

**Note:** GitHub Actions will fail if git tag doesn't match `pyproject.toml` version.

**If build fails:** Delete tag (`git tag -d vX.Y.Z && git push origin :refs/tags/vX.Y.Z`), fix issue, commit, and re-tag. Or manually trigger workflow from GitHub Actions tab.

### Version Numbering (SemVer)

- **MAJOR.MINOR.PATCH** (e.g., `1.2.3`)
- `0.x.0` = New features
- `0.1.x` = Bug fixes
- `1.0.0` = First stable release

---

## 🧩 Adding New Code Safely

1. Implement changes under `gaik-py/src/gaik/...` and keep public APIs backwards compatible.
2. Update exports (for example `gaik/__init__.py`) when new modules must be discoverable by users.
3. Add or adjust dependencies in `gaik-py/pyproject.toml` (core requirements → `[project.dependencies]`, extras → `[project.optional-dependencies]`).
4. Run `python examples/demo_anthropic.py` to smoke test the package before bumping the version.
5. Update relevant docs/examples so new behavior is covered prior to tagging a release.

---

## ✅ Pre-Release Checklist

```bash
# Clean build
cd gaik-py
rm -rf dist/ build/ src/*.egg-info/

# Build locally
python -m build

# Verify package
twine check dist/*

# Test import
pip install dist/gaik-*.whl
python -c "from gaik.extract import SchemaExtractor; print('OK')"
```

---

## 🔍 Post-Release Verification

1. Check PyPI page: `https://pypi.org/project/gaik/`
2. Test installation:

```bash
# Clean environment
pip uninstall gaik -y

# Install from PyPI
pip install gaik

# Verify
python -c "from gaik.extract import SchemaExtractor; print('Success!')"
```

## 📋 Manual Publish (Emergency)

If GitHub Actions fails:

```powershell
cd .\gaik-py\
python -m build
twine upload dist/*
# Username: __token__
# Password: [your PYPI_API_TOKEN]
```

---

## 📝 Release Workflow

1. ✅ Update version in `pyproject.toml`
2. ✅ Test locally
3. ✅ Commit changes
4. ✅ Create git tag (`vX.Y.Z`)
5. ✅ Push tag to GitHub
6. ✅ Verify GitHub Actions succeeds
7. ✅ Test installation from PyPI
8. ✅ Create GitHub Release (optional - via GitHub UI or `gh release create vX.Y.Z --title "Title" --notes "Notes"`)

---

## 📚 Resources

- [Python Packaging Guide](https://packaging.python.org/)
- [Twine Documentation](https://twine.readthedocs.io/)
- [GitHub Actions - Publishing](https://docs.github.com/en/actions/publishing-packages)
