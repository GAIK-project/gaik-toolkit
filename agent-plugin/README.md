# gaik-toolkit agent plugin

A portable [Agent Plugins v1](https://agent-plugins.org) package containing the skills an
AI coding agent needs to build document-understanding pipelines with the
[`gaik`](https://pypi.org/project/gaik/) Python toolkit.

The skills carry decisions and failure modes that are expensive to rediscover — which
parser preserves a table's structure, why an extraction request is refused, and what a
confidence score is actually worth — rather than restating the API reference, which the
agent can read from the package itself.

## Skills

| Skill | Use it when |
|---|---|
| `parsing-documents` | Converting PDFs, scans, or Word files to text or markdown; tables come out wrong; parsing costs more than expected |
| `extracting-structured-data` | Pulling fields or line items into a schema; a request fails with a 400 or truncates; adding page/quote evidence; measuring accuracy |

Each skill is self-contained: `SKILL.md` holds the workflow, and `references/` holds detail
loaded only when the task needs it.

## Installing

This package follows the portable format, so any client that implements Agent Plugins v1
can load it from a directory. The two common cases:

**Claude Code** — add the repository as a plugin marketplace, then install:

```bash
/plugin marketplace add GAIK-project/gaik-toolkit
```

```bash
/plugin install gaik-toolkit@gaik-toolkit
```

**Any other Agent Plugins v1 client** — point it at this directory, or copy the directory
into wherever that client keeps plugins. Everything the format defines lives at a fixed
location, so nothing needs configuring.

**No plugin support at all** — copy `skills/parsing-documents/` and
`skills/extracting-structured-data/` into the agent's skills directory. They are ordinary
[Agent Skills](https://agentskills.io/specification) and do not depend on the plugin
wrapper.

## Layout

```text
agent-plugin/
├── plugin.json          # manifest — the only required file
└── skills/
    ├── parsing-documents/
    │   ├── SKILL.md
    │   └── references/
    └── extracting-structured-data/
        ├── SKILL.md
        └── references/
```

The format is deliberately small. Two things are worth knowing if you extend this package:

**Component locations are fixed and cannot be redirected.** `plugin.json` names and
describes the plugin; it cannot relocate `skills/`, and it cannot declare a component
inline. A client finds skills by looking in `skills/` for immediate child directories
containing a `SKILL.md` — it does not search deeper, so a skill nested two levels down is
invisible.

**v1 standardises exactly two component types**: skills, and MCP servers declared in an
`mcp.json` at the plugin root. Agents, slash commands, hooks, and prompts are outside the
portable contract. A client that wants them uses a reverse-domain extension namespace —
either a key under `extensions` in `plugin.json`, or a top-level directory named exactly
for that namespace, such as `com.example.client/`. Putting a client's own field at the
manifest's top level instead does not conform: the schema is closed, and a conforming
client reports and ignores the unknown field.

Both properties are what make the package portable — a client that implements none of the
extensions still loads every skill here correctly.

## Adding a skill

1. Create `skills/<skill-name>/SKILL.md` with `name` (matching the directory) and
   `description` in the frontmatter.
2. Write the description in the third person, and say **when** to use the skill, not only
   what it does — that text is the whole basis on which an agent decides to open it.
3. Put anything long in `references/` and tell `SKILL.md` when to read it, so it costs
   nothing until it is needed.

No registration step: the skill is discovered because of where it sits.

## Verifying the manifest

```bash
python -c "import json; json.load(open('agent-plugin/plugin.json'))"
```

The manifest requires only `$schema` and `name`. `name` must be 1–64 characters of
lowercase letters, digits, hyphens, and periods, starting and ending alphanumeric, with no
doubled hyphens or periods. Any schema violation other than an unknown top-level field is
fatal — the client rejects the whole plugin and loads none of its skills.

## License

MIT, same as the toolkit.
