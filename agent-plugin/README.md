# gaik-toolkit agent plugin

A portable [Agent Plugins v1](https://agent-plugins.org) package containing the skills an
AI coding agent needs to build document pipelines with the
[`gaik`](https://pypi.org/project/gaik/) Python toolkit.

The skills carry decisions and failure modes that are expensive to rediscover — which
parser preserves a table's structure, why an extraction request is refused, why a hybrid
search quietly became vector-only — rather than restating the API reference, which the
agent can read from the package itself.

## Skills

| Skill | Use it when |
|---|---|
| `parsing-documents` | Converting PDFs, scans, or Word files to text or markdown; tables come out wrong; parsing costs more than expected |
| `extracting-structured-data` | Pulling fields or line items into a schema; a request fails with a 400 or truncates; adding page/quote evidence; measuring accuracy |
| `searching-documents` | Adding semantic or hybrid (pgvector + full-text) search over documents; Finnish text; deciding whether a search found anything; measuring retrieval |

Each skill is self-contained: `SKILL.md` holds the workflow, and `references/` holds detail
loaded only when the task needs it.

## Installing

One package serves every client. The repository root carries a marketplace file,
`.claude-plugin/marketplace.json`, that Claude Code, Codex, Copilot CLI and VS Code all read.

| Client | Commands |
|---|---|
| Claude Code | `/plugin marketplace add GAIK-project/gaik-toolkit`, then `/plugin install gaik-toolkit@gaik-toolkit` |
| Codex | `codex plugin marketplace add GAIK-project/gaik-toolkit`, then `codex plugin add gaik-toolkit@gaik-toolkit` |
| Copilot CLI | `copilot plugin marketplace add GAIK-project/gaik-toolkit`, then `copilot plugin install gaik-toolkit@gaik-toolkit` |
| VS Code | add `GAIK-project/gaik-toolkit` to the `chat.plugins.marketplaces` setting, or run **Chat: Install Plugin From Source** |
| Other Agent Plugins v1 clients | point the client at this directory |
| No plugin support | copy the directories under `skills/` into the agent's skills directory — they are ordinary [Agent Skills](https://agentskills.io/specification) |

Claude Code 2.1.278 and Codex 0.149.1 were tested end to end (September 2026); the other
rows follow those clients' documentation.

## Layout

```text
agent-plugin/
├── plugin.json          # Agent Plugins v1 manifest
├── .claude-plugin/
│   └── plugin.json      # Claude Code's own manifest
└── skills/
    ├── parsing-documents/
    ├── extracting-structured-data/
    └── searching-documents/
        ├── SKILL.md
        └── references/
```

## How the clients read it

- **Agent Plugins v1 clients** (Codex, Copilot, VS Code, Cursor, Kiro) read `plugin.json` at
  this directory's root and discover skills in `skills/`.
- **Claude Code** does not implement Agent Plugins v1. It reads its own manifest,
  `.claude-plugin/plugin.json`, and discovers the same `skills/`. The Agent Plugins migration
  guide keeps a client's working files beside the portable manifest and removes them only
  once that client is tested without them — Claude Code still needs this one, and it is
  what names the skills `gaik-toolkit:…` even when the directory is loaded directly.
- **Codex** finds the marketplace through `.claude-plugin/marketplace.json`, which it
  accepts as a legacy-compatible location; its native one is
  `.agents/plugins/marketplace.json`. One file serves everything today — add the native one
  only if Codex stops reading the legacy path.

The format is deliberately small, and two of its rules shape any extension:

**Component locations are fixed and cannot be redirected.** `plugin.json` names and
describes the plugin; it cannot relocate `skills/`, and it cannot declare a component
inline. A client finds skills by looking in `skills/` for immediate child directories
containing a `SKILL.md` — it does not search deeper, so a skill nested two levels down is
invisible.

**The manifest schema is closed.** Allowed fields are `$schema`, `name`, `version`,
`description`, `author`, `homepage`, `repository`, `license`, `keywords` and `extensions`.
Client-specific data goes under `extensions`, keyed by a reverse-domain namespace such as
`com.openai`, or into a top-level directory named exactly for that namespace. A client
ignores namespaces it does not implement, so the package stays portable.

## Releasing a change

**Bump `version` in both manifests — `plugin.json` and `.claude-plugin/plugin.json` — with
every change under this directory.** Each client caches an installed plugin under the
version it read, so an edit that keeps the old version never reaches anyone who already
installed it. The test below fails if the two versions disagree.

The skills quote gaik's API. `implementation_layer/unit_tests/test_agent_plugin.py` checks
the manifest, the marketplace entry, every skill's frontmatter and links, and that the gaik
names the skills rely on still exist — so a rename in gaik fails CI until the skill is
updated too.

## Extending

**A skill.** Create `skills/<skill-name>/SKILL.md` with `name` (matching the directory)
and a third-person `description` that says when to use the skill, not only what it does —
that text is the whole basis on which an agent decides to open it. Put anything long in
`references/` and say in `SKILL.md` when to read it. No registration step.

**An MCP server.** Declare it twice, because the two families read different files —
tested: Claude Code 2.1.278 loads only `.mcp.json`, Codex 0.149.1 only `mcp.json`, so the
same server in both files does not collide:

| File | Read by | Shape |
|---|---|---|
| `mcp.json` | Agent Plugins v1 clients | `{"$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json", "mcpServers": {...}}`; transports `stdio`, `streamable-http`, `sse`; `${PLUGIN_ROOT}` / `${PLUGIN_DATA}` in `args`, `env` and `cwd` |
| `.mcp.json` | Claude Code | `{"mcpServers": {...}}`; transports `stdio`, `http`, `sse`; `${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_PLUGIN_DATA}` |

An invalid `mcp.json` disables only the MCP servers; the skills still load.

**Client-only features** go where that client looks, never into the manifest's top level.
Agent Plugins clients use their extension namespace — `extensions.com.openai` for Codex
apps and hooks, a `com.github.copilot/` directory for Copilot agents and commands. Claude
Code has no namespace; it reads `agents/`, `commands/` and `hooks/hooks.json` at the plugin
root.

**Another plugin.** Put it in its own directory beside this one, with both manifests, and
add an entry to `.claude-plugin/marketplace.json` whose `source` is its relative path.

## Distribution

`.claude-plugin/marketplace.json` makes this repository a self-hosted marketplace: anyone can
add it by name, as in the table above. It does not list the plugin in any client's curated
directory. Those take separate submissions — Anthropic's `claude-plugins-official`, which
Claude Code's Discover view browses, accepts third-party plugins through its
[plugin directory submission form](https://clau.de/plugin-directory-submission).

## Verifying

```bash
claude plugin validate .
claude plugin validate ./agent-plugin
uvx --from skills-ref agentskills validate agent-plugin/skills/searching-documents
uv run pytest implementation_layer/unit_tests/test_agent_plugin.py
```

To try a change in Claude Code without installing it, run
`claude --plugin-dir ./agent-plugin`; it loads the plugin for that session only.

## License

MIT, same as the toolkit.
