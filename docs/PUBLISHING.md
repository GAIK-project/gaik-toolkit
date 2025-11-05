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
# 1. Update version
# Edit gaik-py/pyproject.toml: version = "0.2.0"

# 2. Commit and tag
git add gaik-py/pyproject.toml
git commit -m "Bump version to 0.2.0"
git tag v0.2.0
git push origin main
git push origin v0.2.0

# 3. GitHub Actions publishes automatically
# 4. Verify: pip install gaik
```

### Version Numbering (SemVer)

- **MAJOR.MINOR.PATCH** (e.g., `1.2.3`)
- `0.x.0` = New features
- `0.1.x` = Bug fixes
- `1.0.0` = First stable release

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

---

## 🐛 Common Issues

| Issue                 | Solution                                   |
| --------------------- | ------------------------------------------ |
| "File already exists" | Bump version (PyPI versions are permanent) |
| "Invalid credentials" | Check `PYPI_API_TOKEN` in GitHub Secrets   |
| "Package name taken"  | Choose different name in `pyproject.toml`  |

---

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
4. ✅ Create git tag (`v0.2.0`)
5. ✅ Push tag to GitHub
6. ✅ Verify GitHub Actions succeeds
7. ✅ Test installation from PyPI
8. ✅ Create GitHub Release (optional)

---

## 🔙 Rollback

**Important:** Cannot delete versions from PyPI!

- Publish fixed version (e.g., `0.2.1`)
- Update documentation
- Mark broken version in release notes

---

## 📚 Resources

- [Python Packaging Guide](https://packaging.python.org/)
- [Twine Documentation](https://twine.readthedocs.io/)
- [GitHub Actions - Publishing](https://docs.github.com/en/actions/publishing-packages)
