---
name: gaik-add-examples
description: >-
  Adds or updates working code examples for GAIK toolkit components and pipelines
  in implementation_layer/examples/. Use when adding a new example, demonstrating
  a feature, creating a usage sample, or showing how a building block or pipeline
  works. After the example is in place, offers optional follow-ups: update API docs
  (guidance_layer/docs/), update the Fumadocs website (guidance_layer/website/content/docs/),
  expose the feature in the demo app (toolkit_demo_app/api/routers + UI), and push
  a PyPI release tag. Covers software_components (extractor, parsers, transcriber,
  RAG, classifier, TTS, enhance_transcript, postgres_agent, tabular_agent,
  validators (LLMJudge / panel / pairwise / calibration), evaluators
  (ExtractionEvaluator, RAGEvaluator,
  BatchEvaluationRunner), form_understander, observability) and software_modules
  (AudioToStructuredData, DocumentsToStructuredData, RAGWorkflow,
  MultiSourceReportGenerator). Not for creating a brand-new component
  package — use build-software-component for that.
argument-hint: "[component name or feature to demonstrate]"
---

# Add GAIK Examples

Adds or updates working examples under `implementation_layer/examples/`. After the
example is added, asks the user whether to propagate the new capability to docs,
the demo app, and a PyPI release.

**Not this skill's job** — use **`build-software-component`** instead when the user
wants to create a brand-new component package (new source files under
`implementation_layer/src/gaik/software_components/...`, new `pyproject.toml` extra,
installable `pip install "gaik[...]"` flow).

Examples live in `implementation_layer/examples/` split into two categories:

- `software_components/` — individual building blocks (extractor, parsers, transcriber, RAG, classifier, TTS, etc.)
- `software_modules/` — end-to-end pipelines (audio_to_structured_data, documents_to_structured_data, RAG_workflow, multi_source_report_generator)

## Steps

1. **Choose the right location**
   - New building block example → `software_components/<component_name>/`
   - New pipeline example → `software_modules/<pipeline_name>/`
   - Adding to existing component → add a numbered/named file alongside the existing ones:
     `demo_<variant>.py`, `<component>_example_2.py`, etc.

2. **Follow the standard file structure**

```python
"""
Example: [one-line summary]
Workflow: [input] -> [step1] -> [step2] -> [output]
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables before importing gaik modules
load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Add src directory to path to import modules (works without pip install)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik... import ...


def main() -> None:
    # example code here


if __name__ == "__main__":
    main()
```

   **Adjust `.parent` depth** to reach `implementation_layer/` from the example file's location.
   - `software_components/<comp>/example.py` → `.parent.parent.parent` for `.env`, `.parent.parent.parent.parent / "src"` for src
   - `software_modules/<mod>/example.py` → same depth
   - Subdirectory example (e.g. `software_modules/<mod>/subdir/example.py`) → add one more `.parent`

3. **Add or update README.md** in the component/module directory covering:
   - Prerequisites (pip extras: e.g. `pip install "gaik[extract]"`, required env vars)
   - How to run: `python example.py`
   - What the example demonstrates

4. **Update the parent README.md** (`software_components/README.md` or `software_modules/README.md`) to list the new example.

5. **Add sample input files if needed** (PDFs, audio files, images) to an `input/` subdirectory. Keep samples small and redistributable.

## Configuration pattern

**OpenAI/Azure-only examples** use the legacy config — always import from `gaik.software_components.config`:

```python
from gaik.software_components.config import get_openai_config, create_openai_client

config = get_openai_config(use_azure=True)   # Azure OpenAI
config = get_openai_config(use_azure=False)  # Standard OpenAI
client = create_openai_client(config)        # OpenAI/AzureOpenAI client
```

Pipeline constructors accept `use_azure=True/False` directly:

```python
pipeline = DocumentsToStructuredData(use_azure=True)
```

**Multi-provider examples** (validators, evaluators, anything that must run on
Anthropic or Google in addition to OpenAI/Azure) use the multi-provider surface:

```python
from gaik.software_components.llm import get_llm_config, create_llm_client

config = get_llm_config("anthropic")  # or "openai", "azure", "google"
client = create_llm_client(config)    # ProviderClient (chat / chat_parsed / chat_stream / embed)
```

`gaik[llm-anthropic]` and `gaik[llm-google]` extras pull in the provider SDKs on demand.

## Step 6 — Optional follow-ups (ask the user)

After Steps 1–5 are done, the example is working. Ask the user whether to
propagate the new capability further. Each sub-step is **gated** by its own
yes/no question — run only the ones the user approves.

Default suggestion: **ask all four** unless the example is a trivial tweak to
an existing file. Skip straight to a single question in that case.

### 6a. Update API docs (`guidance_layer/docs/`)

Ask: **"Update API-level Markdown docs under `guidance_layer/docs/`?"**

Update when: the example introduces a new public API surface, new constructor
params, or a new public method.

- `guidance_layer/docs/software_components/<component>.md` — per-component API reference
- `guidance_layer/docs/software_modules/<pipeline>/` — pipeline API reference

### 6b. Update Fumadocs website (`guidance_layer/website/content/docs/`)

Ask: **"Update the user-facing Fumadocs website?"**

Update when: the example demonstrates a new capability users would discover via
the website.

- `toolkit/software-components.mdx` or `toolkit/software-modules.mdx` — component catalog
- `use-cases/<case>.mdx` — new or updated use case walkthrough
- Update the relevant `meta.json` if a new page is added
- Preview locally: `cd guidance_layer/website && pnpm dev` (uses pnpm, not bun)

### 6c. Expose in `toolkit_demo_app/`

Ask: **"Expose this in the demo app (`implementation_layer/toolkit_demo_app/`)?"**

Default: **yes** for interactive, user-facing features (parsers, transcribers,
extractors, RAG, TTS, classifiers); **no** for internal utilities.

If yes:
- Add/extend a FastAPI router under `implementation_layer/toolkit_demo_app/api/routers/` (e.g. `parser.py`, `extractor.py`, `rag.py`)
- Add schema(s) under `implementation_layer/toolkit_demo_app/api/schemas/`
- Add or update a Next.js page/route under `implementation_layer/toolkit_demo_app/app/`
- Handle missing optional dependencies gracefully (the extra may not be installed by default)
- Dev preview: `bun run dev:all` from `implementation_layer/toolkit_demo_app/`

### 6d. Tag a PyPI release

Ask: **"Tag a PyPI release now?"**

Only relevant if the example accompanies a code change in
`implementation_layer/src/gaik/` (pure docs/example-only changes don't need a
release).

If yes:
1. Commit and push all changes.
2. Run the test suite locally (`uv run pytest`).
3. Choose the semver bump (patch / minor / major).
4. Tag and push: `git tag v0.X.Y && git push origin v0.X.Y`.
5. `.github/workflows/publish.yml` triggers on `v*.*.*` tag push — runs tests,
   builds wheel + sdist, uploads to PyPI, creates a GitHub Release.
6. setuptools-scm derives the version from the tag — **never** edit version
   strings manually.

## Notes

- Examples serve as both usage documentation and integration tests
- Keep each file focused on one concept — add a new numbered/named file for a new concept
- Real-world complexity examples go in a subdirectory (e.g., `diary_workflow/`)
- For the full mapping of "what changed → what to update", see the `gaik-toolkit` skill
