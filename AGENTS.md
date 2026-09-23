# gaik-toolkit agent instructions

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

## agent-plugin (the published agent skills)

`agent-plugin/` is installed by Claude Code, Codex, Copilot and VS Code through
`.claude-plugin/marketplace.json`, and its skills quote gaik's API.

- Bump `version` in both `agent-plugin/plugin.json` and
  `agent-plugin/.claude-plugin/plugin.json` with any change under `agent-plugin/`: each
  client caches an install under the version it read.
- `implementation_layer/unit_tests/test_agent_plugin.py` fails when gaik renames a name a
  skill quotes; fix the skill in the same change. It checks names only, so a change in
  behaviour needs a read of the skill that describes it.

## toolkit_demo_app on Rahti

- Deploy by pushing to the `deploy/demo-app` branch: `git push origin main:deploy/demo-app`.
  A GitHub webhook starts the BuildConfigs in `openshift/buildconfigs.yaml`, and the
  deployments roll out when the images land. `openshift/deploy.sh` is the local fallback.
- Never `oc apply` the deployment manifests in `openshift/`: the live deployments carry
  env vars (Allas, `DATABASE_URL`, TTS, report-writer limits) set with `oc set env` that
  the manifests lack, and applying them drops those.
- The API image installs gaik from PyPI, not from this repository, so a gaik fix reaches
  the demo app only after a release.
- `proxy.ts` is the only auth layer in front of the FastAPI backend; every
  state-changing method needs a signed-in user (`lib/api-access.ts`).

## graphify (optional)

`graphify-out/` holds a committed knowledge graph. If the `graphify` CLI is installed,
prefer `graphify query|path|explain` for codebase questions and run `graphify update .`
after code changes. If it is not installed, use normal search and do not mention it.
Invoke `/graphify` only when that skill is listed. Dirty `graphify-out/` files are
expected.
