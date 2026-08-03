# gaik-toolkit agent instructions

## gaik-sync (keep the Solution Wizard in step with gaik)

The Solution Configuration Wizard (`implementation_layer/solution_wizard/`) holds a component registry, reference cards, and selection guidance that mirror the gaik API. When gaik changes, these drift silently and the wizard produces wrong blueprints or PoCs that fail at runtime.

Rule: after any change to gaik that affects its public surface, **remind the user to run the `gaik-sync` skill** (and offer to run it). Trigger changes include:

- adding, removing, or renaming a software component or module;
- changing a component's constructor params, primary method name, or return shape;
- adding/removing/renaming a behaviour-changing option;
- changing a component's `install_extra` / pip extra, supported providers, or input/output artifact types;
- a component now providing a capability internally (a new subsumption relationship);
- bumping the installed gaik version.

`gaik-sync` scans gaik, presents its findings for approval, and only then syncs the approved changes into the wizard and runs the tests. It edits the wizard assets only — never gaik. A quick non-mutating check is `uv run python .claude/skills/gaik-sync/scripts/audit_registry.py`.

**Sync the dev environment with all extras first:**

```bash
uv sync --all-extras
```

The audit and the wizard's `tests/test_reference_cards.py` both work by importing gaik classes. Several components swallow a missing optional dependency in `__init__.py` (`try: from .x import Y / except ImportError: pass`), so an environment missing an extra makes a class silently absent. The audit then reports it as `removed` drift that is not real, and the tests skip checks they appear to be running. Missing `pydub` alone produced two false `removed` findings and hid 12 assertions on 2026-08-03. Run the audit with `uv run` so it uses the project environment rather than a system Python.

## graphify (optional — only when the tooling is present)

This repo has a committed knowledge graph in graphify-out/ (god nodes, community
structure, cross-file relationships). The `graphify` CLI and skill are **not part
of the toolkit's required setup** — some developers have them installed, others
don't. Treat graphify as a best-effort accelerator, never a hard dependency.

**Availability gate — check before using, and degrade silently if absent:**

- If the user types `/graphify` and a `graphify` skill is actually listed as
  available, invoke it. If no such skill exists, do **not** attempt to invoke it —
  just answer the request with normal search.
- If the `graphify` CLI is installed, prefer it for codebase questions:
  `graphify query "<question>"`, `graphify path "<A>" "<B>"`,
  `graphify explain "<concept>"`. These return a scoped subgraph, usually much
  smaller than GRAPH_REPORT.md or raw grep.
- If the CLI is **not** installed and no skill is available, skip graphify entirely
  and use the normal tools (Grep/Glob/Read). Do not announce graphify or report it
  as missing — silently fall back. The committed graphify-out/ artifacts
  (graph.json, GRAPH_REPORT.md, wiki/) may be read directly as an optional
  fallback, but reading them is never required.

When graphify *is* in use:

- Dirty graphify-out/ files after hooks or incremental updates are expected and not
  a reason to skip it. Only skip if the task is about stale/incorrect graph output,
  or the user says not to use it.
- Prefer graphify-out/wiki/index.md for broad navigation, GRAPH_REPORT.md only for
  broad architecture review or when query/path/explain don't surface enough.
- After modifying code, `graphify update .` keeps the graph current (AST-only, no
  API cost) — only if the CLI is installed.
