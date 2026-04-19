---
name: build-software-component
description: >-
  Creates a new GAIK software component as an installable Python package.
  Accepts context from URLs, external codebases, or plain descriptions.
  Produces an implementation plan for user review, then executes the plan:
  creates component files, updates pyproject.toml, installs the package,
  and verifies with import smoke tests.
argument-hint: "[context: URLs, paths, PyPI package names, or description]"
---

# Build Software Component

Use this skill when the user wants to add a new GAIK software component under
`implementation_layer/src/gaik/software_components/`. The user will provide context —
URLs of a library's docs, a path to an external codebase to wrap, a PyPI package name,
or a plain description of the functionality — and this skill turns that context into
a working, installable component that follows GAIK's existing conventions.

## When to use

Invoke this skill when the user asks to:
- "Create/build/add a new software component …"
- "Wrap library X as a GAIK component"
- "Turn this codebase at `<path>` into a GAIK component"
- "Make a component from <URL / API docs>"

Do not use this skill for non-component work (demo app changes, docs website edits,
bug fixes in existing components, etc.).

## Workflow — 5 phases

Follow these phases in order. Do not skip Phase 3.

### Phase 1 — Context Gathering

Identify the context sources in the user's prompt and consume them:

- **URLs** → use `WebFetch` on each URL to extract API and usage info.
- **PyPI package names** → `WebFetch` `https://pypi.org/pypi/<name>/json` for
  metadata and latest version pin.
- **Local codebase paths** → use `Glob` / `Grep` / `Read` to map structure, public
  API, and dependencies.
- **Plain description** → treat the prompt text as the spec.

Before moving on, make sure you understand:
1. What the component does (one sentence).
2. What external library/APIs it wraps (if any).
3. What Python dependencies it needs, with versions when available.
4. Whether it is LLM-based (will use `get_openai_config()` / `create_openai_client()`)
   or provider-agnostic (pure Python / local library).

### Phase 2 — Plan Creation

Read `references/conventions.md` first to ground the plan in GAIK patterns.

Write a component plan to `.claude/skills/build_software_component/last_plan.md`
with these sections:

1. **Component identity** — `component_name` (snake_case directory name),
   `MainClassName` (PascalCase), one-line description.
2. **Public API** — classes, methods with signatures, any result dataclasses.
3. **Dependencies** — Python packages with version pins, marked required vs optional.
4. **Config integration** — uses `get_openai_config()` / `create_openai_client()`,
   or provider-agnostic.
5. **Files to create** — full relative paths.
6. **Files to modify** — additions to `pyproject.toml` and
   `implementation_layer/src/gaik/software_components/__init__.py`.
7. **Install extra name** — the name used in `pip install "gaik[<extra>]"`.
   Must be hyphenated, lowercase.
8. **Example usage** — one working snippet the example file will demonstrate.
9. **Verification steps** — the exact import test and smoke-test commands.

### Phase 3 — Plan Review (MANDATORY — never skip)

- Display the full plan to the user via text output (read the plan file back
  in full, do not summarize).
- Ask: "Approve this plan, or describe changes?"
- If the user requests changes: revise `last_plan.md`, re-display the full plan,
  re-ask. Loop until the user explicitly approves.
- Do not execute any file creation, editing, or installation until approval.

### Phase 4 — Execution

Only after explicit approval. Read `references/file-templates.md` for the literal
file bodies to use. Execute in this order — if any step fails, stop and report
the error to the user before continuing:

1. Create `implementation_layer/src/gaik/software_components/<component_name>/`
   directory.
2. Write `<component_name>.py` — the main class file. Use the template from
   `file-templates.md`.
3. Write `__init__.py` — module docstring, re-exports, `__all__`,
   `__version__ = "0.1.0"`.
4. Write `README.md` — description, install command, quick-start example.
5. Edit `pyproject.toml` — add a new entry under `[project.optional-dependencies]`
   named `<extra-name>`. If the component belongs in `all` / `all-cpu` composite
   groups, add it there too.
6. Edit `implementation_layer/src/gaik/software_components/__init__.py` — append
   the new `component_name` string to the `__all__` list.
7. Create `implementation_layer/examples/software_components/<component_name>/<component_name>_example.py`
   using the example template.

### Phase 5 — Verification

Read `references/verification.md` for exact commands. Steps:

1. Run `pip install -e ".[<extra-name>]"` from the repo root.
2. Run the import smoke test:
   `python -c "from gaik.software_components.<component_name> import <MainClassName>; print('OK')"`.
3. If the example file can be run without live credentials, run it. Otherwise,
   skip this step and note that running the example requires credentials.
4. Report final status to the user:
   - Files created (paths).
   - Install result (success/failure + key lines if failed).
   - Smoke test result.
   - Example run result (or "skipped — requires credentials").

## Hard rules

- **Never skip Phase 3.** Always present the plan and wait for approval.
- **Scope of edits:** only create/edit files inside
  `implementation_layer/src/gaik/software_components/<component_name>/`,
  `implementation_layer/examples/software_components/<component_name>/`,
  `pyproject.toml`, and
  `implementation_layer/src/gaik/software_components/__init__.py`.
  Never edit anything else (no demo app, no docs website, no other components).
- **Shared config:** for any component that calls an LLM, import from
  `gaik.software_components.config` and use `get_openai_config()` +
  `create_openai_client()`. Never call `load_dotenv()` inside the component
  and never read `OPENAI_API_KEY` / `AZURE_API_KEY` directly.
- **Never commit.** Leave all changes uncommitted so the user can review with
  `git diff` and commit themselves.
- **No unit tests** unless the user's context explicitly demands them. The
  example file is the proof-of-life artifact.

## References

- `references/conventions.md` — GAIK component directory layout, `__init__.py`
  pattern, constructor pattern, result dataclass pattern, extras naming.
- `references/file-templates.md` — literal templates for every file to create
  plus the exact edits to `pyproject.toml` and the parent `__init__.py`.
- `references/verification.md` — install command, smoke test, common failure
  modes and fixes.
