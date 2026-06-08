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

`gaik-sync` scans gaik, presents its findings for approval, and only then syncs the approved changes into the wizard and runs the tests. It edits the wizard assets only — never gaik. A quick non-mutating check is `python .claude/skills/gaik-sync/scripts/audit_registry.py`.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, invoke the `skill` tool with `skill: "graphify"` before doing anything else.

Rules:

- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If the `graphify` CLI is not installed, read the committed graphify-out/ artifacts directly (graph.json, GRAPH_REPORT.md, wiki/) instead of running the commands.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
