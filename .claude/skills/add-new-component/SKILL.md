---
name: add-new-component
description: Full pipeline for adding a new GAIK toolkit component end-to-end. Use when adding a new parser, extractor, transcriber, RAG module, TTS, classifier, or pipeline and you want the complete release-ready flow — not just source. Sequences build-software-component (source) and gaik-add-examples (example), then prompts for website docs (guidance_layer/website/), toolkit_demo_app integration, and PyPI release tag (v*.*.*). Use this over build-software-component when you want the whole flow from code to release so nothing gets forgotten.
---

# Add New Component — Full Pipeline

Orchestrates the end-to-end workflow for adding a new GAIK toolkit component:

**source → example → website docs → toolkit_demo_app → PyPI release**

This skill does not reimplement the existing skills — it sequences them and adds the website / demo-app / release prompts that are easy to forget.

## When to use

- Adding a new parser, extractor, transcriber, RAG module, classifier, TTS, or pipeline.
- You want the **whole** release-ready flow (not just source).
- Last `multimodal_parser` addition (commit 2066cf7) shipped source + example but the website and release tag were manual follow-ups — this skill closes that gap.

## When NOT to use

- Just creating a quick prototype/component with no intent to release → use `build-software-component` directly.
- Adding only an example for an existing component → use `gaik-add-examples` directly.
- Bug fix in an existing component → no skill needed.

## Workflow

### 1. Build source

Delegate to `build-software-component` skill (mandatory plan-review-execute loop).

Result:
- `implementation_layer/src/gaik/software_components/<category>/<name>/` (main module + `__init__.py` + `config.py` + `prompts.py` if applicable + `README.md`)
- Updated category `__init__.py` and category `README.md`
- New optional extra in `pyproject.toml`
- Installed locally and import smoke test passes

### 2. Add additional examples (ask)

Step 1 already created one initial example under
`implementation_layer/examples/software_components/<name>/` as part of
`build-software-component`. This step is only about **additional** examples.

Delegate to `gaik-add-examples` skill when the user says yes to any of:

- **"Add a `software_modules/` pipeline example?"** (default: yes, if the new
  component is a building block in an end-to-end pipeline).
- **"Add a second numbered example (`<name>_example_2.py`) covering a different
  configuration or use case?"** (default: no — only if the component has distinct
  modes worth demonstrating).
- **"Enrich the component's README with a usage walkthrough?"** (default: no).

If none apply, skip to step 3 — the initial example from step 1 is sufficient.

### 3. Website & docs (ask)

Ask: **"Update Fumadocs website (`guidance_layer/website/content/docs/`) and/or API docs (`guidance_layer/docs/`)?"**

Default:
- **Yes** for parsers, extractors, transcribers, RAG modules, pipelines (anything a user would discover via docs).
- **No** for internal utilities or private helpers.

If yes:
- Add or update an MDX page under `guidance_layer/website/content/docs/` describing the component, its config, and a minimal usage snippet.
- Link the new page from the relevant category index (`meta.json` or category MDX).
- Mirror the API surface in `guidance_layer/docs/` if the component has a non-trivial public API.

### 4. toolkit_demo_app integration (ask)

Ask: **"Expose this in `implementation_layer/toolkit_demo_app/`?"**

Default depends on type:
- **Yes** for interactive components users would want to try (parsers, transcribers, RAG, TTS, classifiers).
- **No** for internal utilities or developer-only helpers.

If yes:
- Add a FastAPI endpoint in the demo app's backend.
- Add a UI card / route in the Next.js frontend.
- Make sure the demo handles missing optional dependencies gracefully (the extra may not be installed by default).

### 5. PyPI release (ask)

Ask: **"Tag a PyPI release now?"**

If yes:
1. Commit and push all changes from steps 1–4.
2. Run the test suite locally: `uv run pytest` (or the project's configured runner).
3. Decide the version bump (semver):
   - patch (`v0.X.Y+1`) — bug fix or small additive component
   - minor (`v0.X+1.0`) — meaningful new component or capability
   - major — breaking changes (rare)
4. Tag and push: `git tag v0.X.Y && git push origin v0.X.Y`
5. `.github/workflows/publish.yml` triggers automatically on `v*.*.*` tag push: runs tests, builds wheel + sdist, validates version, uploads to PyPI, creates a GitHub Release.
6. setuptools-scm derives the package version from the tag — **do not** edit version manually anywhere.

If no:
- Note "release deferred" in the commit message so the next contributor knows it's pending.

## Release-readiness checklist

Run through this before tagging:

- [ ] Source files + `__init__.py` exports under `implementation_layer/src/gaik/software_components/<category>/<name>/`
- [ ] Component `README.md` written
- [ ] `pyproject.toml` optional extra added (and named consistently)
- [ ] Category `__init__.py` and `README.md` updated to list the new component
- [ ] Example under `implementation_layer/examples/` runs cleanly with the optional extra installed
- [ ] Local tests pass (`uv run pytest`)
- [ ] Website docs updated (if user-facing)
- [ ] `toolkit_demo_app` updated (if interactive)
- [ ] All changes committed and pushed
- [ ] `v*.*.*` tag pushed (if releasing now)

## Notes

- **Do not** edit version strings manually — setuptools-scm reads from git tags. Manual edits cause the publish workflow to fail version validation.
- The publish workflow (`.github/workflows/publish.yml`) is gated on tests passing and uses a protected `release` GitHub environment.
- If a release tag fails to publish, check the Actions tab for `Publish to Production PyPI`. Common failures: tests broken, version mismatch, network issues uploading to PyPI (workflow has retry logic for the install verification step).
- This skill is purely orchestrative. If the user only needs one phase (e.g. just an example), invoke `gaik-add-examples` directly instead.
