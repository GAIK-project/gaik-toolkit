# Handoff — Demo site on Rahti: Report Writer live, Solution Wizard gated & working

Status: **shipped and verified live** at https://gaik-demo.2.rahtiapp.fi/ (2026-06-12).
This doc captures the current state and the deploy gotchas so they aren't re-discovered.

## Current state (all on `origin/main`)

- **Report Writer** is live for everyone (`/report-writer`); example assets are bundled in
  the API image (`api/report_examples/`), and the API installs gaik **from the repo source**
  because the published wheel lags the `multi_source_report_generator` module.
- **Solution Wizard works on CSC Rahti** (`/solution-wizard`) but is gated: front page shows
  a "Coming soon" pill; `/solution-wizard` and `/api/wizard` are closed unless
  `WIZARD_ACCESS_SECRET` is set and supplied once via `/solution-wizard?key=<secret>`
  (sets a 30-day cookie). The secret lives in the Rahti `gaik-demo-admin` secret and in
  `.env.local` (gitignored). There is **no password input in the UI** — access is via the
  `?key=` URL only.
- Wizard in-container support (commit `ab66d53`): container-aware `WIZARD_DIR` /
  `WIZARD_WORKSPACES_DIR` resolution in `api/routers/solution_wizard.py`, wizard assets
  baked into the API image, Foundry credentials wired from the `gaik-demo-api-keys` secret.
  The `claude` CLI ships **bundled inside the claude-agent-sdk wheel** — no Node needed.
- Wizard UX: extended thinking streams as `thinking_delta` SSE events into a collapsible
  Reasoning block; the generated-files tree refreshes live mid-turn; layout breaks out to
  1400px.
- UI polish: compact selected-file row in `FileUpload`, quieter How It Works trigger,
  slim hero pill for the wizard callout.

## Deploy (works, don't reinvent)

- `openshift/deploy.sh api|frontend|all` — builds with a `docker-container` buildx builder
  and pushes **single-arch Docker schema2** (`--provenance=false --output
  type=registry,oci-mediatypes=false`). Rahti's registry rejects Docker 29's default
  OCI/manifest-list output.
- API image builds from the **repository root** context (installs gaik from source, copies
  `implementation_layer/solution_wizard`). `.dockerignore` must keep the wizard `SKILL.md` —
  it excludes `*.md` globally and has explicit negations for the wizard files.
- Foundry env vars on `gaik-demo-api` (from secret `gaik-demo-api-keys`):
  `CLAUDE_CODE_USE_FOUNDRY`, `ANTHROPIC_FOUNDRY_API_KEY`, `ANTHROPIC_FOUNDRY_RESOURCE`,
  `ANTHROPIC_DEFAULT_SONNET_MODEL`. The live deployment has drifted from
  `deployment-api.yaml` (extra `oc set env` vars like `DATABASE_URL`, `ALLAS_*`) — do NOT
  blindly `oc apply` the manifest; patch instead.

## Verified live (2026-06-12)

- Wizard gate: no key → 307 to `/`; `/api/wizard/*` → 403; `?key=` → unlocks + cookie.
- Wizard run: `/wizard/start` → 200, bundled CLI found, welcome turn + use-case
  classification streamed over SSE in prod.
- Report writer page + example endpoints respond; transcriber, front page OK.
- GitHub Actions: ruff format check green after formatting `report_writer.py`.

## Known open issues (wizard quality, not environment)

End-to-end testing (local `ravelast-wizard-test` workspace, `FINDINGS.md`) found 4 open
gaik-level bugs: nested/composite schema codegen + runtime crashes, and registry
parser-name drift vs the gaik API (run `gaik-sync`). These affect generated-PoC quality,
not the wizard runtime itself.

## Next steps (optional)

- Publish gaik (e.g. 0.5.16) including `multi_source_report_generator`, then restore the
  PyPI pin in `api/requirements.txt` and drop the repo-install from the API Dockerfile.
- Run `gaik-sync` for the registry parser-name drift (FINDINGS.md Bug 3).
- In-container `gaik.__version__` reports `0.0.0` (cosmetic; repo install loses the
  git-derived version).
- Exercise a full wizard run in prod (through PoC generation) — only the conversational
  flow has been verified there; heavy scripted steps (generate_bpmn, scaffold_poc) have
  been verified locally.
