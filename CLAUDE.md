@AGENTS.md

## Graphify-first navigation

For GAIK toolkit codebase questions, first use the local graphify knowledge
graph when the CLI is available:

```bash
graphify query "<question>"
```

Use `graphify path "<A>" "<B>"` for relationships and
`graphify explain "<concept>"` for focused concepts. If graphify does not
surface the relevant files or symbols, fall back to normal source inspection
with search/read tools. After modifying code, run `graphify update .` when the
CLI is available.
