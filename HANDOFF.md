# Handoff — Demo site on Rahti, now on the published gaik 0.5.16 wheel

Status: **shipped and verified live** at https://gaik-demo.2.rahtiapp.fi/ (2026-06-13).
gaik **0.5.16 is published to PyPI** and the demo app now installs that wheel instead
of building gaik from repository source. This doc captures the current state and the
deploy gotchas so they aren't re-discovered.

## Current state (all on `origin/main`)

- **gaik 0.5.16 on PyPI** (tag `v0.5.16`) — first release that ships the Report Writer
  module (`multi_source_report_generator`), plus accumulated component work since
  v0.5.15 (extractor/schema, vision_extractor, validators, parsers, llm providers).
- **Report Writer** is live for everyone (`/report-writer`); example assets bundled in
  the API image (`api/report_examples/`). The API now installs gaik **from the published
  wheel** — `api/requirements.txt` pins
  `gaik[all-cpu,multimodal-parser,postgres-agent,multi-source-report-generator-agentic,multi-source-report-generator-docx]>=0.5.16`.
  The repo-source install hack was removed from `api/Dockerfile`. In-container
  `gaik.__version__` now correctly reports `0.5.16` (was `0.0.0`).
- **Solution Wizard works on CSC Rahti** (`/solution-wizard`) but is gated: front page
  shows a "Coming soon" pill; `/solution-wizard` and `/api/wizard` are closed unless
  `WIZARD_ACCESS_SECRET` is set and supplied once via `/solution-wizard?key=<secret>`
  (sets a 30-day cookie). The secret lives in the Rahti `gaik-demo-admin` secret and in
  `.env.local` (gitignored). There is **no password input in the UI** — `?key=` URL only.
  The `claude` CLI ships **bundled inside the claude-agent-sdk wheel** — no Node needed.
- Wizard UX (polished 2026-06-13): extended-thinking streams into a **lightweight,
  height-capped, internally-scrolling** Reasoning block that stays open for the whole
  turn (no mid-stream collapse/jump) and finalizes into the message as a collapsed line
  in history; the "Thinking…" indicator is a plain inline row (no background box); the
  reply input is compact (`min-h-11`); the page subtitle is a single line. The
  generated-files tree refreshes live mid-turn; layout breaks out to 1400px.

## Deploy (works, don't reinvent)

- `openshift/deploy.sh api|frontend|all` — **both** api and frontend now build with the
  `gaik-rahti` docker-container buildx builder and push **single-arch Docker schema2**
  (`--provenance=false --output type=registry,oci-mediatypes=false`), then
  `oc rollout restart` + wait. Rahti's registry rejects Docker 29's default OCI/
  manifest-list output. (The frontend path was fixed this session — plain
  `docker build`+`docker push` silently breaks when a docker-container builder is
  selected, because the image never lands in the local store to tag/push.)
- API image builds from the **repository root** context (still copies the wizard assets
  under `implementation_layer/solution_wizard`). `.dockerignore` must keep the wizard
  `SKILL.md` — it excludes `*.md` globally and has explicit negations for the wizard files.
- The API image needs the **pandoc binary** (apt package) — Report Writer's DOCX export
  goes through pypandoc, which shells out to it. Without it the run 500s at the end.
- Foundry env vars on `gaik-demo-api` (from secret `gaik-demo-api-keys`):
  `CLAUDE_CODE_USE_FOUNDRY`, `ANTHROPIC_FOUNDRY_API_KEY`, `ANTHROPIC_FOUNDRY_RESOURCE`,
  `ANTHROPIC_DEFAULT_SONNET_MODEL`. The live deployment has drifted from
  `deployment-api.yaml` (extra `oc set env` vars like `DATABASE_URL`, `ALLAS_*`) — do NOT
  blindly `oc apply` the manifest; patch instead.
- Publishing gaik: push a `vX.Y.Z` tag → `.github/workflows/publish.yml` runs tests,
  builds (setuptools-scm version = tag), uploads to PyPI, and cuts a GitHub release.

## Verified live (2026-06-13)

- gaik 0.5.16 on PyPI; API pod imports it from `site-packages` (not source),
  `gaik.__version__ == 0.5.16`, `pandoc 3.1.11.1` present.
- Report Writer **end-to-end on the published wheel**: multi-modal example (PDF + MP3
  audio + notes + XLSX + PNG) → `/report-writer/run` 200, ~19.6k tokens, markdown + a
  valid pandoc-generated `.docx` (`PK..[Content_Types].xml`).
- Solution Wizard **heavy path** (blueprint → Pydantic schema → Mermaid → BPMN 2.0 →
  5 docs → runnable PoC scaffold + downloadable zip) verified end-to-end; the
  conversational flow + use-case classification re-verified on the wheel deployment.
  (The heavy path was driven on the prior source build, which is byte-identical code to
  the 0.5.16 wheel.)
- Wizard UI polish verified live: capped/scrolling Reasoning, no stream jump, no
  background "Thinking…" box, compact input, single-line subtitle.

## Known open issues (not blocking)

- **Wizard generated-PoC quality** (gaik-level, not the wizard runtime): end-to-end
  testing on a parent+line-items composite schema (`c:/Users/h03068/dev/fair/
  ravelast-wizard-test/FINDINGS.md`) found 4 open gaik bugs — nested/composite schema
  codegen + runtime crashes, and registry parser-name drift vs the gaik API. A flat
  schema (as in this session's medical-dictation run) does not trigger them. **Run
  `gaik-sync`** to reconcile: the non-mutating audit
  (`python .claude/skills/gaik-sync/scripts/audit_registry.py`) reports 19 findings —
  notably the registry's `MultiSourceReportGenerator` lists 8 options (`agentic`,
  `output_docx`, `report_language`, `curate_evidence`, …) that aren't real constructor
  params (actual: `api_config`, `use_azure`), plus option drift on TranscriptEnhancer /
  DocumentsToStructuredData / ParallelTranscriber and an untracked
  `gaik.software_components.llm` family. Then a separate fix round for the composite
  schema codegen.
- ESLint **now runs**: `eslint.config.mjs` uses eslint-config-next's native flat config
  and eslint is pinned to 9 (eslint 10 isn't supported by the Next 16 eslint stack yet).
  `bun run lint` surfaces ~36 pre-existing `react-hooks` issues in shadcn-generated
  `components/ui/*` + `hooks/*` (e.g. `Math.random` in render, setState-in-effect) — not
  from this work; clean up separately. The wizard files changed this session lint clean.
  `next build` still does not run ESLint, so builds/deploys are unaffected either way.

## Next steps (optional)

- Run `gaik-sync` and fix the 4 FINDINGS bugs (composite schema codegen) in gaik, then
  re-publish.
- Exercise a full wizard run **with a composite (parent + line-items) schema** in prod to
  confirm the codegen fixes once they land.
