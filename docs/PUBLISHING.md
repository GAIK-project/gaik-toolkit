# Publishing to PyPI - Cheat Sheet

## Current Status

- ✅ **Test PyPI**: Published and working
- ⏳ **Production PyPI**: Not yet published

---

## Publishing to Production PyPI

### Prerequisites

1. **PyPI Account**: Create account at https://pypi.org/account/register/
2. **API Token**: Generate at https://pypi.org/manage/account/token/
3. **GitHub Secret**: Add token as `PYPI_API_TOKEN` in repository secrets

---

### Step 1: Update Version

Edit **two files**:

```bash
# 1. gaik-py/pyproject.toml
version = "0.2.0"  # Bump version

# 2. gaik-py/src/gaik/__init__.py
__version__ = "0.2.0"  # Must match pyproject.toml
```

**Version numbering:**
- `0.x.0` - New features
- `0.1.x` - Bug fixes
- `1.0.0` - Stable release

---

### Step 2: Update GitHub Actions Workflow

Edit `.github/workflows/release-pypi.yml` (create if not exists):

```yaml
name: Publish to PyPI

on:
  push:
    tags:
      - 'v*.*.*'

jobs:
  build-and-publish:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.10'

    - name: Install build tools
      run: pip install build twine

    - name: Build package
      working-directory: gaik-py
      run: python -m build

    - name: Publish to PyPI
      working-directory: gaik-py
      env:
        TWINE_USERNAME: __token__
        TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
      run: |
        twine upload --repository-url https://upload.pypi.org/legacy/ dist/*
```

**Key differences from Test PyPI:**
- URL: `https://upload.pypi.org/legacy/` (not test.pypi.org)
- Secret: `PYPI_API_TOKEN` (not TEST_PYPI_API_TOKEN)
- No `--skip-existing` (PyPI doesn't allow re-uploads)

---

### Step 3: Test Locally

```bash
cd gaik-py

# Clean previous builds
rm -rf dist/ build/ src/*.egg-info/

# Build package
python -m build

# Check package integrity
twine check dist/*

# Test installation locally
pip install dist/gaik-*.whl
python -c "import gaik; print(gaik.__version__)"
```

---

### Step 4: Create Git Tag and Push

```bash
# Commit version changes
git add gaik-py/pyproject.toml gaik-py/src/gaik/__init__.py
git commit -m "chore: Bump version to 0.2.0"
git push

# Create and push tag
git tag v0.2.0
git push origin v0.2.0
```

**GitHub Actions will automatically:**
1. Build the package
2. Upload to PyPI
3. Make it available to everyone

---

### Step 5: Verify Publication

1. **Check PyPI**: https://pypi.org/project/gaik/
2. **Test installation**:
   ```bash
   pip install gaik
   python -c "from gaik.schema import SchemaExtractor; print('Success!')"
   ```

---

## Manual Publishing (If Needed)

If GitHub Actions fails or you need manual control:

```bash
cd gaik-py

# Build
python -m build

# Upload to PyPI
twine upload dist/*
# Enter username: __token__
# Enter password: [your PyPI API token]
```

---

## Common Issues

### Issue: "File already exists"
- **Cause**: PyPI doesn't allow re-uploading same version
- **Fix**: Bump version number and retry

### Issue: "Invalid credentials"
- **Cause**: Wrong API token or not configured
- **Fix**: Regenerate token at https://pypi.org/manage/account/token/

### Issue: "Package name already taken"
- **Cause**: Another package uses the name
- **Fix**: Choose a different name in `pyproject.toml`

---

## Version History Tracking

Keep a `CHANGELOG.md` in `gaik-py/`:

```markdown
# Changelog

## [0.2.0] - 2024-11-15
### Added
- New feature X

### Fixed
- Bug in Y

## [0.1.1] - 2024-11-01
### Changed
- Updated OpenAI API to new format
```

---

## Release Checklist

- [ ] Update version in `pyproject.toml`
- [ ] Update version in `__init__.py`
- [ ] Update `CHANGELOG.md`
- [ ] Run tests locally
- [ ] Build and check package (`python -m build && twine check dist/*`)
- [ ] Commit changes
- [ ] Create and push git tag
- [ ] Verify GitHub Actions succeeds
- [ ] Test installation from PyPI
- [ ] Create GitHub Release with notes

---

## Rollback

If a bad version is published:

1. **Cannot delete from PyPI** - versions are permanent
2. **Solution**: Publish a new fixed version (e.g., 0.2.1)
3. **Communicate**: Update README and CHANGELOG

---

## Resources

- **PyPI Help**: https://pypi.org/help/
- **Packaging Guide**: https://packaging.python.org/
- **Twine Docs**: https://twine.readthedocs.io/
- **GitHub Actions**: https://docs.github.com/en/actions
