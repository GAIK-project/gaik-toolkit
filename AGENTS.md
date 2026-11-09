# gaik-toolkit agent instructions

This repo is public: never commit machine-local paths, usernames or secret-store locations.

## layout

- `implementation_layer/src/gaik/`: the gaik library, published to PyPI; tests in
  `implementation_layer/unit_tests/`.
- `implementation_layer/solution_wizard/`: the Solution Wizard, which mirrors gaik's API
  (see gaik-sync below).
- `implementation_layer/toolkit_demo_app/`: the demo, Next.js on bun with a FastAPI
  backend in `api/`, deployed on Rahti.
- `guidance_layer/website/`: the docs site.

## checks

- Library: `uv run pytest -m "not llm"`. Tests marked `llm` make real provider calls
  and need keys.
- Demo API, from `implementation_layer/toolkit_demo_app/`:
  `uv run --python 3.11 --with pytest --with pytest-asyncio python -m pytest api/tests -o addopts="" -q`
  (`python -m` puts the demo folder on `sys.path`, so `import api` works).
- Demo front end, from the same folder: `bun test`, `bunx tsc --noEmit` and
  `bun run lint`. CI runs none of these, so run them for a front-end change.

## Code Review Rules

- Important here: a change to gaik's public names, parameters, return shapes or extras
  without the matching Solution Wizard registry or agent-skill update; an optional
  dependency whose absence now hides a class silently; a provider or model default
  changed without the release certification below. In the demo: a request past
  `proxy.ts` without its sign-in, approval or trial check; a model, transcription or
  parser call outside the rate limits; an upload that reaches a parser or a model before
  its content and size are checked; personal data kept past its cleanup; AI output
  without its AI notice. Anywhere: a secret, real customer document or machine-local
  path; a test that does not check what its name says; a CI or release check made to
  pass by skipping it.
- Give the file and line for each finding and the case where it goes wrong. Report a
  missing check only after naming the code path that lacks it.
- When a change leaves a weakness unfixed, name the area and say the details go to the
  maintainers; never describe how to exploit it in a public issue or comment.
- At most three nits, none about formatting (ruff owns it). Skip generated files unless
  the change is about them: `graphify-out/`, the demo's `lib/no-code/catalog.generated.json`
  and `public/downloads/skills/`, lockfiles and `evaluation_layer/**/runs/`.
- Start the summary with the number of findings by severity, or say in one line that
  there is nothing to fix.

## software components and modules (ask first)

Do not change the toolkit's software components or modules (`implementation_layer/src/gaik/`,
for example the schema generator, extractor, transcriber or LLM layer) until the user
has approved or permitted that change. Ask first and wait for the answer, whether the
change is a fix, a refactor, a test-driven tweak or a workaround for something seen in a
demo. Never commit such a change without asking either.

If a demo problem seems to come from a component, describe the cause and propose the
change, and offer a fix in the demo code (`toolkit_demo_app/`) that leaves the component
as it is. Approval for one change does not cover later ones.

## formatting

CI fails on `ruff format --check implementation_layer/` (ruff 0.14.10). Run
`uvx pre-commit install` once per clone so `.pre-commit-config.yaml` formats staged
Python files at commit time; keep its `rev` in step with the version in `test.yml`.

## gaik-sync (keep the Solution Wizard in step with gaik)

The Solution Wizard (`implementation_layer/solution_wizard/`) mirrors gaik's API in a
component registry, reference cards and selection guidance. When gaik changes they drift
silently, and the wizard generates blueprints or PoCs that fail at runtime.

After a change to gaik's public surface, remind the user to run the `gaik-sync` skill and
offer to run it. That covers adding, removing or renaming a component, module or
behaviour-changing option; changing constructor params, the primary method or its return
shape; changing a pip extra, providers or artifact types; a new subsumption; and bumping
gaik. The skill proposes changes and edits wizard assets only after approval. A quick
read-only check: `uv run python .claude/skills/gaik-sync/scripts/audit_registry.py`.

Run `uv sync --all-extras` first, and run the audit and wizard tests through `uv run`.
Components swallow a missing optional dependency in `__init__.py`, so a missing extra
makes a class silently absent: the audit reports false `removed` drift and the tests skip
checks they appear to run.

## agent-skills (the published agent plugin)

`implementation_layer/no-code-assets/agent-skills/` holds every agent skill under `skills/` as one plugin, installed by Claude Code, Codex, Copilot and VS Code through
`.claude-plugin/marketplace.json`, and its skills quote gaik's API.

- Bump `version` in both `plugin.json` and
  `.claude-plugin/plugin.json` in that directory with any change under it: each
  client caches an install under the version it read.
- `implementation_layer/unit_tests/test_agent_plugin.py` fails when gaik renames a name a
  skill quotes; fix the skill in the same change. It checks names only, so a change in
  behaviour needs a read of the skill that describes it.

## no-code assets (skills and prompts)

`implementation_layer/no-code-assets/` holds the prompts and the agent skills plugin,
`agent-skills/`. The demo app's `/skills` and `/prompts` pages serve a generated copy of
them, because its image is built from `toolkit_demo_app/` alone. After changing a skill,
a prompt, the plugin or `no-code-assets/catalog.json`, run
`uv run python implementation_layer/toolkit_demo_app/scripts/build_no_code_catalog.py` and
commit `lib/no-code/catalog.generated.json` and `public/downloads/skills/`;
`test_no_code_catalog.py` fails while they are stale.

## toolkit_demo_app on Rahti

- Deploy by pushing to the `deploy/demo-app` branch: `git push origin main:deploy/demo-app`.
  A GitHub webhook starts the BuildConfigs in `openshift/buildconfigs.yaml`, and the
  deployments roll out when the images land. `openshift/deploy.sh` is the local fallback.
- Keep `main` and `deploy/demo-app` level: land anything that reached the deploy branch in
  `main` by PR, so the push stays a fast-forward. Never force-push it; if it is ahead, merge it first.
- Never `oc apply` the deployment manifests in `openshift/`: the live deployments carry
  env vars (Allas, `DATABASE_URL`, TTS, report-writer limits) set with `oc set env` that
  the manifests lack, and applying them drops those.
- The API image installs gaik from PyPI, not from this repository, so a gaik fix reaches
  the demo app only after a release.
  The demo's local uv environment uses this repository's gaik as an editable install
  (`[tool.uv.sources]` in its `pyproject.toml`), so a local run can pass on a fix that
  the deployed demo lacks.
- `proxy.ts` is the only auth layer in front of the FastAPI backend; every
  state-changing method needs a signed-in, approved user (`lib/api-access.ts`), or a
  pending one within the daily trial allowance (`lib/trial.ts`, counted in Upstash
  Redis, off without it); the wizard routes have their own gate.

## docs site (GitHub Pages)

`.github/workflows/pages.yml` publishes `guidance_layer/website` (Fumadocs, pnpm) to
https://gaik-project.github.io/gaik-toolkit/ on every push to main that touches it.
`content/docs/<path>.mdx` is served at `/gaik-toolkit/<path>/`, with no `/docs` segment.
Link that page, not the MDX file; the old docs host `gaik-toolkit.2.rahtiapp.fi` is gone.

## graphify (optional)

`graphify-out/` holds a committed knowledge graph. If the `graphify` CLI is installed,
prefer `graphify query|path|explain` for codebase questions and run `graphify update .`
after code changes. If it is not installed, use normal search and do not mention it.
Invoke `/graphify` only when that skill is listed. Dirty `graphify-out/` files are
expected.

## release certification (required before every tag and PyPI release)

- Every version tag/release requires real authenticated component tests, not only
  imports, mocked calls, or the presence of API keys. Before tagging, commit the
  intended release, set the wizard validated pin to the planned version, then run
  `uv run python scripts/release_check.py --live --version X.Y.Z`. The command runs
  all-extras sync, offline tests, wizard tests/audit, package validation, and bounded
  live component checks. A passing sanitized `results/release-check.json` must name
  the exact commit and planned version. Rerun after any tracked release change.
- Set `RELEASE_PROVIDERS` and explicit `RELEASE_<PROVIDER>_MODEL` model/deployment IDs.
  Check current official model documentation/catalogs before choosing IDs; do not
  assume a model name in an old example is current. Every changed provider/model
  family and every newly added provider needs a sanitized live smoke report before
  tagging. The normal matrix is representative; exhaustive catalog evaluation is
  separate and must not automatically run on every release.
- CI always requires Azure plus any providers selected in `RELEASE_PROVIDERS`.
  Missing selected credentials, timeouts, skipped required checks, and invalid model
  output fail the gate. Do not turn these into a pass or bypass the gate to publish.
  Aitta and other optional providers can be certified locally; do not require a
  permanently valid Aitta token for unrelated releases.
- `publish.yml` calls the test workflow with `release_gate: true`; publishing depends
  on that complete workflow succeeding. Do not tag, upload to PyPI, or deploy the
  demo until the applicable certification passes. Keep credentials, raw provider
  errors, and personal documents out of reports; use the synthetic fixtures.
- Once a release is on PyPI, offer to take it into the Solution Wizard v2 fork with the
  `wizard-upstream-sync` skill: one checked pull request to the fork's `develop`.
