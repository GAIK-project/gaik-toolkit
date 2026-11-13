# Operations and MCP Server

Two packages beside the software components. Neither changes a component.

- `gaik.operations`: one blocking function per common task, with shared settings.
- `gaik.mcp_server`: the same functions, and `FieldsToDocx`, as MCP tools for agents.

Both are in gaik from the release after 0.8.14.

## Operations

```bash
pip install "gaik[operations]"
```

| Function | Returns | Model calls |
| --- | --- | --- |
| `parse_document(path)` | `ParsedDocument(text, pages, kind)` for a PDF, DOCX, `.txt` or `.md` file | 0 |
| `transcribe_audio(path, language=None, context="")` | `Transcript(text, duration_s, language, model, failed_segments)` | 1 per part |
| `generate_fields(requirement)` | `list[FieldDefinition]` | 2 or more |
| `extract_fields(text, fields, instructions="", evidence=True)` | `list[ExtractedField(name, label, value, evidence, verdict)]` | 1 |
| `classify_text(text, labels, instructions=None, jev=None)` | `Classification(label, confidence, probabilities, model, backend)` | 1 |

```python
from gaik.operations import FieldDefinition, classify_text, extract_fields, parse_document

document = parse_document("service_note.txt")  # no model call

fields = [
    FieldDefinition(name="site", label="Site"),
    FieldDefinition(name="visit_date", type="date", label="Date of visit"),
]
for item in extract_fields(document.text, fields):
    print(item.label, item.value, item.evidence, item.verdict)

result = classify_text(
    document.text,
    {"urgent": "Needs action today", "normal": "Can wait for the next visit"},
)
print(result.label, result.confidence)
```

Every function takes `settings=OperationSettings(config=None, provider=None, timeout=120.0,
quiet=True, work_dir=None, temperature=0.0, reasoning_effort=None)`. Helpers:
`build_schema(fields)` (the extraction schema, no model call),
`await run_async(fn, *args, deadline=None, **kwargs)` (a blocking call in a worker thread) and
`quiet_stdout()` (keep what the current thread or asyncio task prints out of stdout).

Full reference: [operations README](../../implementation_layer/src/gaik/operations/README.md).

## MCP server

```bash
pip install "gaik[mcp]"

gaik-mcp --root . --env-file .env                                 # stdio
GAIK_MCP_TOKEN=<32 or more random characters> gaik-mcp --transport http   # http://127.0.0.1:8000/mcp
```

Tools: `parse_document`, `transcribe_audio`, `generate_fields`, `extract_fields`,
`classify_text`, `fields_to_word`.

- Path arguments must stay inside the root folder (`--root`, `GAIK_MCP_ROOT`). There is no
  root by default on either transport, and then every path is refused; a whole drive or the
  home folder is refused as a root. A file can also be sent as `content_base64` with a
  `filename`.
- Limits: `GAIK_MCP_MAX_FILE_MB` (25), `GAIK_MCP_MAX_TEXT_CHARS` (100000, also for labels
  and field definitions in all), `GAIK_MCP_TIMEOUT` (120 seconds per model request).
- HTTP does not start without `GAIK_MCP_TOKEN` of at least 32 characters; every request
  needs `Authorization: Bearer <token>`. Other Host headers than `localhost` and
  `127.0.0.1` are allowed with `--allowed-host`.
- `fields_to_word` with `overwrite` replaces an existing Word file under the root, so the
  tool is marked destructive and a client can ask its user first.
- The text the tools return is content of a file, not instructions for the agent; the tool
  descriptions say so.
- No tool sends mail, fetches a URL, runs code or lists a folder.

Full reference: [MCP server README](../../implementation_layer/src/gaik/mcp_server/README.md).
Client configuration for Claude Code, Cursor, Codex and VS Code:
[examples/mcp_server](../../implementation_layer/examples/mcp_server/README.md).
