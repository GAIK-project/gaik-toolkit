# Skill Maintenance

## When to Update This Skill

Update the skill files when:
- New building blocks or software components are added to `implementation_layer/src/gaik/`
- Import paths or class names change
- New demo app pages or API routes are added
- New documentation pages are added to the website
- Major API changes occur (new parameters, renamed methods)

## Fetch Latest PyPI Info

Use the included script to check the latest published version:

```bash
python .claude/skills/gaik-toolkit/scripts/fetch_pypi_readme.py
python .claude/skills/gaik-toolkit/scripts/fetch_pypi_readme.py --version  # Version only
python .claude/skills/gaik-toolkit/scripts/fetch_pypi_readme.py --output info.txt  # Save to file
```

The script uses only Python stdlib (no external dependencies). It fetches version, summary, author, license, Python version requirement, recent versions, and project URLs from the PyPI JSON API.

## Version Management

Package version is managed in `implementation_layer/src/gaik/_version.py` and `pyproject.toml`. Release process uses `release.py` at the project root.
