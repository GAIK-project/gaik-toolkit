# Verification

The steps to run after Phase 4 (execution) to confirm the new component is
correctly installed and importable.

## 1. Install the component's extras

Run from the **repo root** (not from `implementation_layer/`):

```bash
pip install -e ".[<extra-name>]"
```

Where `<extra-name>` is the hyphenated name added to `[project.optional-dependencies]`
in `pyproject.toml`.

Expected output contains a line like:
```
Successfully installed gaik-<version> <dep1> <dep2> ...
```

If the install fails, read the error and bail out. Common causes:
- Version conflict with an existing extra → loosen the pin in `pyproject.toml`.
- Typo in the extra name → must match exactly what's in `pyproject.toml`.
- Missing system dependency (e.g. FFmpeg, build toolchain) → surface to the user.

## 2. Import smoke test

```bash
python -c "from gaik.software_components.<component_name> import <MainClassName>; print('OK')"
```

Expected output: `OK`.

This verifies:
- The component directory is installed in the `gaik` package.
- `__init__.py` re-exports `<MainClassName>`.
- All `import` statements inside the component resolve.

## 3. Example run (best effort)

Try to run the example file:

```bash
python implementation_layer/examples/software_components/<component_name>/<component_name>_example.py
```

Expected behavior depends on whether the example hits live APIs:
- **Provider-agnostic components** should run successfully and print something.
- **LLM-based components** will fail without credentials — this is expected.
  Report to the user: "Example run skipped — requires AZURE_API_KEY or OPENAI_API_KEY."

Do not fail the whole skill if the example fails due to missing credentials.
Do fail if the example fails due to an `ImportError`, `AttributeError`, or
`SyntaxError` — those indicate real problems in the generated code.

## 4. Final status report

Print a short report to the user with four sections:

```
Files created:
- implementation_layer/src/gaik/software_components/<component_name>/__init__.py
- implementation_layer/src/gaik/software_components/<component_name>/<component_name>.py
- implementation_layer/src/gaik/software_components/<component_name>/README.md
- implementation_layer/examples/software_components/<component_name>/<component_name>_example.py

Files modified:
- pyproject.toml (added [project.optional-dependencies] <extra-name>)
- implementation_layer/src/gaik/software_components/__init__.py (added "<component_name>" to __all__)

Install:    OK (`pip install -e ".[<extra-name>]"`)
Smoke test: OK (`python -c "..."` printed OK)
Example:    <OK | skipped — requires credentials | FAILED with <reason>>
```

Do not commit. Tell the user to review with `git status` and `git diff`, then
commit when they're satisfied.

## Common failure modes and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: gaik.software_components.<name>` | Component directory missing, or `__init__.py` missing | Re-check Phase 4 step 1–3 |
| `ImportError: cannot import name '<MainClassName>'` | Class not re-exported in `__init__.py` | Add it to `__all__` and the `from .<name> import ...` line |
| `pip install` fails with "no matching distribution for <dep>" | Bad version pin | Check PyPI for the real available version |
| `pip install -e ".[<extra>]"` says "WARNING: <extra> does not provide ..." | Typo in extra name in `pyproject.toml` | Verify the extra name exactly matches |
| Example file fails with `ModuleNotFoundError: dotenv` | Missing dev dep in system Python | `pip install python-dotenv` (already a core gaik dep, so installing `-e .` should cover it) |
| Circular import between `config.py` and the component | Component imported from `config.py` | Never import a specific component from `config.py` — only the reverse |
| Changes not picked up by `python -c` | Editable install didn't refresh | Re-run `pip install -e ".[<extra>]"` — adding a new extras group can require a reinstall |
