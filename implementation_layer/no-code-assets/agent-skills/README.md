# GAIK agent skills

All GAIK agent skills live here, packaged as one portable
[Agent Plugins v1](https://agent-plugins.org) plugin, `gaik-toolkit`. Add the repository as a
plugin marketplace and every skill below is available in Claude, Claude Code, Codex, Copilot
and VS Code. Each skill is also an ordinary [Agent Skill](https://agentskills.io/specification)
that can be copied or uploaded on its own.

## Skills

Every skill is a directory under `skills/` with a `SKILL.md` (the workflow the agent follows)
and a `README.md` (what the skill does, for people).

**For developers building with the [`gaik`](https://pypi.org/project/gaik/) package.** These
carry decisions and failure modes that are expensive to rediscover — which parser preserves a
table's structure, why an extraction request is refused, why a hybrid search quietly became
vector-only — rather than restating the API reference.

| Skill | Use it when |
|---|---|
| [`parsing-documents`](skills/parsing-documents) | Converting PDFs, scans, or Word files to text or markdown; tables come out wrong; parsing costs more than expected |
| [`extracting-structured-data`](skills/extracting-structured-data) | Pulling fields or line items into a schema; a request fails with a 400 or truncates; adding page/quote evidence; measuring accuracy |
| [`searching-documents`](skills/searching-documents) | Adding semantic or hybrid (pgvector + full-text) search over documents; Finnish text; deciding whether a search found anything; measuring retrieval |
| [`generate-structured-reports`](skills/generate-structured-reports) | Writing a source-cited report from mixed files (PDF, Word, spreadsheets, recordings, images) with the gaik report writer, following a template or proposing one; every statement traced to a verified quote, with gaps and conflicts shown |

**Ready-to-run use cases.** No code needed. `brief-to-slides` runs anywhere; the other four
are written for Claude Desktop and need a local MCP server, which each skill's README sets up.

| Skill | What it does | Needs |
|---|---|---|
| [`brief-to-slides`](skills/brief-to-slides) | Builds an editable PowerPoint deck with speaker notes, exact timing and citations from a topic, an audience and a length | — |
| [`incident-report-writing`](skills/incident-report-writing) | Turns a spoken incident or safety observation into a Word report | gaik-transcriber MCP server |
| [`construction-diary-creation`](skills/construction-diary-creation) | Turns a site manager's spoken day into a Työmaapäiväkirja | gaik-transcriber MCP server |
| [`purchase-order-processing`](skills/purchase-order-processing) | Matches a purchase order and its BOMs against a price list and writes a priced sales order | Filesystem MCP server |
| [`report-writing`](skills/report-writing) | Consolidates recordings, notes and documents into one structured Word report | Filesystem and gaik-transcriber MCP servers |

`report-writing` has Claude write the report itself in Claude Desktop. `generate-structured-reports` runs gaik's normalize, curate and synthesize pipeline instead, with quotes checked against the sources, and needs an agent that can run Python.

Long detail sits in `references/` (or `reference/`) and is loaded only when the task needs it.
The Claude Desktop skills also carry their setup files beside `SKILL.md`: `setup.bat` and
`transcription-MCP/`. Their sample recordings, purchase orders, price list and example output
are not part of the plugin; they are in the repository under
[`implementation_layer/no-code-assets/samples/`](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/no-code-assets/samples),
and each skill's README links its own.

## Data, services and credentials

The plugin contains instructions, reference text, scripts and two PowerPoint templates. It
declares no MCP server, hook or command, and it sends nothing anywhere by itself. A skill
reaches an outside service only when the agent follows it, and only the services below.
Each one receives the user's own content, under that provider's terms.

| Skill | Sends data to | What is sent | Credential it reads |
|---|---|---|---|
| `parsing-documents` | The LLM provider the user configures in gaik: OpenAI, Azure OpenAI, Anthropic (direct or Microsoft Foundry), Google Gemini / Vertex AI, CSC Aitta, or a provider reached through LiteLLM; a Docling API server whose address the user gives | Page images and text of the documents being parsed. The local parsers (PyMuPDF, python-docx, Docling) send nothing. | That provider's API key from the environment, such as `OPENAI_API_KEY`, `AZURE_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `AITTA_API_KEY` |
| `extracting-structured-data` | The LLM provider the user configures, as above | Document text or page images, and the extraction schema | As above |
| `searching-documents` | The configured embedding and LLM provider; the user's PostgreSQL database | Document chunks and search queries | As above, and the database URL |
| `generate-structured-reports` | The configured LLM provider; OpenAI or Azure OpenAI for recordings | Text of the user's source files, transcribed audio and the report draft | As above |
| `incident-report-writing`, `construction-diary-creation`, `report-writing` | OpenAI (Whisper and GPT models) through the local `gaik-transcriber` MCP server | The audio or video file the user names | `OPENAI_API_KEY`, which `setup.bat` asks for and writes to `transcription-MCP/.env` beside the server; a key already set in the environment takes precedence |
| `purchase-order-processing` | Nothing outside the machine; Claude reads the files through the local filesystem MCP server | — | — |
| `brief-to-slides` | Web pages the user links or the agent researches; the browser fetches Google Fonts when an HTML preview opens | Search queries and page addresses | — |

**Installs.** Skills that run code install packages from public registries: gaik and
its dependencies from PyPI (`gaik==0.8.4` with the extra the task needs), `mcp`,
`python-dotenv`, `python-pptx`, `pillow`, `cairosvg`, `lxml` and `playwright` from PyPI,
Playwright's Chromium build, the font packages and `lucide-static` from npm for
`brief-to-slides`, and `@modelcontextprotocol/server-filesystem` from npm for the Claude
Desktop MCP setup. Those commands name exact versions, and the packages' own dependencies
resolve when the user installs them. `generate-structured-reports` installs `gaik[report-writer]`,
and a provider's gaik extra when it is missing, without a version pin. After the user agrees,
it also downloads Pandoc from its official release through pypandoc. Its `SKILL.md`
describes both.

**Credentials.** No credential is stored in this plugin. The skills use whatever API key
the user has set for gaik in their environment or in a local `.env` file, and they send it
only to the provider it belongs to. The `setup.bat` scripts ask the user for the key and
write it to a `.env` file on the user's machine. That file stays there and is never part
of the plugin or the repository.

## Directory review notes

- `skills/brief-to-slides/assets/template.pptx` (391 KiB) and `blank-template.pptx` are
  the decks the skill builds on, so they stay in the plugin and their review hold is
  accepted. Without them the skill cannot keep a template's layouts, fonts and theme.
- The skills ask for no `userConfig` value. The keys are gaik's ordinary environment
  variables, which gaik also reads outside the agent, and Codex has no `userConfig`.

## Installing

One package serves every client. The repository root carries a marketplace file,
`.claude-plugin/marketplace.json`, that Claude, Claude Code, Codex, Copilot CLI and VS Code
all read.

| Client | Commands |
|---|---|
| Claude Desktop, claude.ai | **Customize → Plugins → Add → Add marketplace → Add from a repository**, enter `GAIK-project/gaik-toolkit`, **Sync**, then **Add** the plugin on the Discover tab |
| Claude Code | `/plugin marketplace add GAIK-project/gaik-toolkit`, then `/plugin install gaik-toolkit@gaik-toolkit` |
| Codex | `codex plugin marketplace add GAIK-project/gaik-toolkit`, then `codex plugin add gaik-toolkit@gaik-toolkit` |
| Copilot CLI | `copilot plugin marketplace add GAIK-project/gaik-toolkit`, then `copilot plugin install gaik-toolkit@gaik-toolkit` |
| VS Code | add `GAIK-project/gaik-toolkit` to the `chat.plugins.marketplaces` setting, or run **Chat: Install Plugin From Source** |
| ChatGPT workspace | an admin opens **Admin Console → Plugins → Add → Import marketplace** and enters `https://github.com/GAIK-project/gaik-toolkit` as the source |
| Other Agent Plugins v1 clients | point the client at this directory |
| No plugin support | copy the directories under `skills/` into the agent's skills directory |
| One skill only | download its `.zip` from the [demo app](https://gaik-demo.2.rahtiapp.fi/skills) and upload it in Claude: **Customize → Skills → Add → Upload skill** |

Claude Code 2.1.278 and Codex 0.149.1 were tested end to end (September 2026), and the
Claude Desktop route on claude.ai in October 2026. The other rows follow those clients'
documentation. Claude's **Sync automatically** option, on by default, keeps the plugin up to
date as this repository changes.

## Layout

The root also holds the plugin icon that the Claude and OpenAI directory listings show.

```text
agent-skills/   (implementation_layer/no-code-assets/)
├── plugin.json          # Agent Plugins v1 manifest
├── .claude-plugin/
│   └── plugin.json      # Claude Code's own manifest; also the directory listing fields
├── LICENSE
└── skills/
    ├── parsing-documents/
    ├── extracting-structured-data/
    ├── searching-documents/
    │   ├── SKILL.md
    │   ├── README.md
    │   └── references/
    ├── generate-structured-reports/   # also scripts/: the stage helper
    ├── brief-to-slides/        # also assets/ and scripts/
    ├── incident-report-writing/
    ├── construction-diary-creation/
    ├── purchase-order-processing/
    └── report-writing/
        ├── SKILL.md
        ├── README.md           # setup guide
        ├── reference/
        ├── setup.bat           # installs the MCP servers for Claude Desktop
        └── transcription-MCP/
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
installed it. The test below fails if the two versions disagree. Then run
`uv run python implementation_layer/toolkit_demo_app/scripts/build_no_code_catalog.py`: the demo
app's skills page serves a generated copy of these skills and shows the plugin version.

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
claude plugin validate ./implementation_layer/no-code-assets/agent-skills
uvx --from skills-ref agentskills validate implementation_layer/no-code-assets/agent-skills/skills/searching-documents
uv run pytest implementation_layer/unit_tests/test_agent_plugin.py
```

To try a change in Claude Code without installing it, run
`claude --plugin-dir ./implementation_layer/no-code-assets/agent-skills`; it loads the plugin for that session only.

## License

MIT, same as the toolkit.
