---
name: build-software-component
description: >-
  Creates a new GAIK software component as an installable Python package.
  Accepts context from URLs, external codebases, or plain descriptions.
  Produces an implementation plan for user review, then executes the plan:
  creates component files, updates pyproject.toml, installs the package,
  and verifies with import smoke tests. For the full release-ready flow
  (more examples, docs, demo app integration, PyPI release tag) delegates
  to the gaik-add-examples skill instead of duplicating that workflow.
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

## Workflow — 6 phases (Phase 6 optional)

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
4. Whether it is LLM-based and which config surface to use:
   - **OpenAI/Azure-only** → `get_openai_config()` + `create_openai_client()`
     from `gaik.software_components.config`
   - **Multi-provider** (OpenAI/Azure/Anthropic/Google) → `get_llm_config()` +
     `create_llm_client()` from `gaik.software_components.llm`. Use this when
     the component needs to swap providers (e.g. validators, evaluators).
   - **Provider-agnostic** (pure Python / local library, no LLM call).
5. **Layout decision — top-level or nested?**
   - **Top-level** — sibling of `extractor/`, `transcriber/`, `doc_classifier/`. Use
     for new independent capabilities.
   - **Nested sub-component** — lives inside an existing category like
     `parsers/<name>/`, `RAG/<name>/`, or `transcriber/<name>/`. Use when the new
     component is a *variant* of an existing category (e.g. another PDF parser
     belongs in `parsers/`, another vector store in `RAG/`). The shipped
     `parsers/multimodal_parser/` is the canonical nested example.

   The two layouts follow the same conventions for `pyproject.toml` extras and
   shared config, but differ in which `__init__.py` gets edited — see the rules
   in Phase 4 and in `references/conventions.md`.

### Phase 2 — Plan Creation

Read `references/conventions.md` first to ground the plan in GAIK patterns.

Write a component plan to `.claude/skills/build-software-component/last_plan.md`
with these sections:

1. **Component identity** — `component_name` (snake_case directory name),
   `MainClassName` (PascalCase), one-line description.
2. **Public API** — classes, methods with signatures, any result dataclasses.
3. **Dependencies** — Python packages with version pins, marked required vs optional.
4. **Config integration** — uses `get_openai_config()` / `create_openai_client()`,
   or provider-agnostic.
5. **Layout** — top-level (`software_components/<name>/`) or nested
   (`software_components/<category>/<name>/`).
6. **Files to create** — full relative paths.
7. **Files to modify** — additions to `pyproject.toml` and *either*
   `software_components/__init__.py` (top-level) *or*
   `software_components/<category>/__init__.py` (nested).
8. **Install extra name** — the name used in `pip install "gaik[<extra>]"`.
   Must be hyphenated, lowercase.
9. **Example usage** — one working snippet the example file will demonstrate.
10. **Verification steps** — the exact import test and smoke-test commands.

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

Let `<dir>` be:
- `implementation_layer/src/gaik/software_components/<component_name>/` for top-level
- `implementation_layer/src/gaik/software_components/<category>/<component_name>/` for nested

1. Create `<dir>` directory.
2. Write `<component_name>.py` — the main class file. Use the template from
   `file-templates.md`.
3. Write `__init__.py` — module docstring, re-exports, `__all__`,
   `__version__ = "0.1.0"`.
4. Write `README.md` — description, install command, quick-start example.
5. Edit `pyproject.toml` — add a new entry under `[project.optional-dependencies]`
   named `<extra-name>`. If the component belongs in `all` / `all-cpu` composite
   groups, add it there too.
6. Register the component in the **parent** `__init__.py`:
   - **Top-level:** edit `software_components/__init__.py` — append the
     `component_name` string to `__all__`.
   - **Nested:** edit `software_components/<category>/__init__.py` — add a
     `try/except ImportError: pass` guard that imports and `__all__.extend(...)`
     the public classes (see `parsers/__init__.py:81-87` for the canonical
     pattern). Do **not** touch the top-level `software_components/__init__.py`.
7. Create the example at
   `implementation_layer/examples/software_components/<component_name>/<component_name>_example.py`
   (top-level) or
   `implementation_layer/examples/software_components/<category>/demo_<component_name>.py`
   (nested — mirrors how existing parser demos are organized) using the example
   template.

### Phase 5 — Verification

Read `references/verification.md` for exact commands. Steps:

1. Run `pip install -e ".[<extra-name>]"` from the repo root.
2. Run the import smoke test against the public import path:
   - Top-level: `python -c "from gaik.software_components.<component_name> import <MainClassName>; print('OK')"`
   - Nested: `python -c "from gaik.software_components.<category> import <MainClassName>; print('OK')"`
     (nested components are re-exported from the category's `__init__.py`).
3. If the example file can be run without live credentials, run it. Otherwise,
   skip this step and note that running the example requires credentials.
4. Report final status to the user:
   - Files created (paths).
   - Install result (success/failure + key lines if failed).
   - Smoke test result.
   - Example run result (or "skipped — requires credentials").

### Phase 6 — Full release workflow (optional)

After Phase 5, ask the user: **"Continue with the full release flow (more
examples → docs → demo app → PyPI tag), or stop here?"** Default: **stop**
for quick prototypes; **continue** when the component is a user-facing
capability worth shipping.

If the user continues, **delegate to the `gaik-add-examples` skill Step 6**
— it is the canonical publish flow and owns the gated 6a–6d prompts for:

- 6a. Additional API docs (`guidance_layer/docs/`)
- 6b. Fumadocs website (`guidance_layer/website/content/docs/`)
- 6c. Demo app integration (`toolkit_demo_app/api/routers/` + UI)
- 6d. PyPI release tag

Phase 4 step 7 of this skill already created one initial example, so
`gaik-add-examples` is typically invoked for **additional** examples (a
pipeline-level example, a second variant, or an enriched README walkthrough).

Do not duplicate 6a–6d logic here — read from `gaik-add-examples/SKILL.md`
so the publish flow stays in one place.

#### Component-specific release-readiness checklist

Before tagging (this is the build-side addition to the checklist in
`gaik-add-examples` — verify the component shape first):

- [ ] Source files + `__init__.py` exports under the component's directory.
- [ ] Component `README.md` written.
- [ ] `pyproject.toml` optional extra added (and named consistently).
- [ ] Parent `__init__.py` (top-level or category) updated to list the
      component.
- [ ] Local tests pass (`uv run pytest`).

## Hard rules

- **Never skip Phase 3.** Always present the plan and wait for approval.
- **Scope of edits during Phases 1–5** (source creation): only create/edit
  files inside
  - the component's own directory (top-level or nested),
  - the matching `implementation_layer/examples/software_components/...` directory,
  - `pyproject.toml`, and
  - exactly one parent `__init__.py`: either `software_components/__init__.py`
    (top-level) or `software_components/<category>/__init__.py` (nested) — never
    both.

  Never touch the demo app, docs website, or other components during source
  creation. Phase 6 is the only phase where those edits are allowed, and only
  after the user has explicitly opted in.
- **Shared config:** for any component that calls an LLM, import from
  `gaik.software_components.config` (`get_openai_config` /
  `create_openai_client`) for OpenAI/Azure-only components, or from
  `gaik.software_components.llm` (`get_llm_config` / `create_llm_client`) for
  multi-provider components (OpenAI/Azure/Anthropic/Google). Never call
  `load_dotenv()` inside the component and never read `OPENAI_API_KEY` /
  `AZURE_API_KEY` directly.
- **Never commit during Phases 1–5.** Leave source changes uncommitted so the
  user can review with `git diff`. Phase 6d is the only place that commits or
  pushes, and only after the user approves the PyPI release step.
- **No unit tests** unless the user's context explicitly demands them. The
  example file is the proof-of-life artifact.

## References

- `references/conventions.md` — GAIK component directory layout, `__init__.py`
  pattern, constructor pattern, result dataclass pattern, extras naming.
- `references/file-templates.md` — literal templates for every file to create
  plus the exact edits to `pyproject.toml` and the parent `__init__.py`.
- `references/verification.md` — install command, smoke test, common failure
  modes and fixes.
