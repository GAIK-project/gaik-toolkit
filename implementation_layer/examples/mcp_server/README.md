# MCP server: client configuration

How to add the [GAIK MCP server](../../src/gaik/mcp_server/README.md) to an agent, and a
client script that runs without credentials.

```bash
pip install "gaik[mcp]"
python mcp_client_example.py     # lists the tools, parses a text file, writes a Word file
```

Two ways to connect:

- **stdio**: the agent starts `gaik-mcp` on your machine. Paths are limited to `--root`;
  without it every path is refused.
- **HTTP**: someone runs `gaik-mcp --transport http` and the agent connects to its URL with a
  bearer token of at least 32 characters.

Keep keys out of the configuration file. With stdio, put the provider variables
(`LLM_PROVIDER`, `AZURE_API_KEY`, `AZURE_ENDPOINT`, ...) in a `.env` file that is not
committed and pass `--env-file .env`. With HTTP, keep the token in the environment variable
`GAIK_MCP_TOKEN`. `<host>` below stands for your server's address.

The file formats below were checked against each client's documentation in November 2026.
Clients change these often; check the linked page when something does not load.

## Claude Code

[Documentation](https://code.claude.com/docs/en/mcp)

```bash
# stdio
claude mcp add gaik -- gaik-mcp --root . --env-file .env

# HTTP
claude mcp add --transport http gaik https://<host>/mcp --header "Authorization: Bearer <token>"
```

Or a `.mcp.json` in the project folder, which the team can share: [`mcp.json`](./mcp.json)
for stdio and [`mcp_http.json`](./mcp_http.json) for HTTP (copy one to `.mcp.json`).
`${GAIK_MCP_TOKEN}` is replaced by the environment variable when the file is read.

```json
{
  "mcpServers": {
    "gaik": {
      "command": "gaik-mcp",
      "args": ["--root", ".", "--env-file", ".env"]
    }
  }
}
```

## Cursor

[Documentation](https://cursor.com/docs/context/mcp). File: `.cursor/mcp.json` in the project,
or `~/.cursor/mcp.json` for every project.

```json
{
  "mcpServers": {
    "gaik": {
      "command": "gaik-mcp",
      "args": ["--root", "${workspaceFolder}", "--env-file", "${workspaceFolder}/.env"]
    }
  }
}
```

HTTP:

```json
{
  "mcpServers": {
    "gaik": {
      "url": "https://<host>/mcp",
      "headers": { "Authorization": "Bearer ${env:GAIK_MCP_TOKEN}" }
    }
  }
}
```

## Codex

[Documentation](https://learn.chatgpt.com/docs/extend/mcp). File: `~/.codex/config.toml`, or
`.codex/config.toml` in a trusted project.

```toml
[mcp_servers.gaik]
command = "gaik-mcp"
args = ["--root", ".", "--env-file", ".env"]
```

HTTP, with the token read from an environment variable:

```toml
[mcp_servers.gaik]
url = "https://<host>/mcp"
bearer_token_env_var = "GAIK_MCP_TOKEN"
```

From the command line:

```bash
codex mcp add gaik -- gaik-mcp --root . --env-file .env
codex mcp add gaik --url https://<host>/mcp --bearer-token-env-var GAIK_MCP_TOKEN
```

## VS Code

[Documentation](https://code.visualstudio.com/docs/agents/reference/mcp-configuration). VS Code
reads two formats.

**`.mcp.json` at the workspace root**, top-level key `mcpServers`: the file Claude Code reads,
so [`mcp.json`](./mcp.json) and [`mcp_http.json`](./mcp_http.json) work as they are. This is
the format the documentation names for new configurations; in November 2026 it is behind the
setting `chat.mcp.workspaceRootConfig.enabled`. It has no `envFile` and no input prompts, so
the server reads its keys with `--env-file`, and `${GAIK_MCP_TOKEN}` in a header is replaced
by the environment variable.

**`.vscode/mcp.json`**, top-level key `servers`: the older editor format. The documentation
keeps it for existing setups and plans to remove it in February 2027.

```json
{
  "servers": {
    "gaik": {
      "type": "stdio",
      "command": "gaik-mcp",
      "args": ["--root", "${workspaceFolder}"],
      "envFile": "${workspaceFolder}/.env"
    }
  }
}
```

HTTP, with the token asked once and stored by VS Code:

```json
{
  "inputs": [
    { "type": "promptString", "id": "gaik-token", "description": "GAIK MCP token", "password": true }
  ],
  "servers": {
    "gaik": {
      "type": "http",
      "url": "https://<host>/mcp",
      "headers": { "Authorization": "Bearer ${input:gaik-token}" }
    }
  }
}
```

## Notes

- `gaik-mcp` must be on the PATH of the process that starts it. With a virtual environment,
  give the full path of the script, or use the environment's Python:
  `"command": "<path to python>", "args": ["-m", "gaik.mcp_server", "--root", "."]`.
- A relative `--root` and `--env-file` are read from the folder the client starts the server
  in, which is usually the project folder. The server does not start when the `--env-file`
  file is missing: leave the flag out when you have no such file. `parse_document` and
  `fields_to_word` need no keys.
- Some clients start their servers in the filesystem root or in the home folder. The server
  then refuses `--root .` and exits with code 2, because the agent would get every document
  on the drive: give the project folder as an absolute path.
- The agent can read the documents and recordings under the root and write `.docx` files
  there; `fields_to_word` with `overwrite` replaces an existing Word file. The tool is marked
  destructive, so keep the client's confirmation for it on.
- The HTTP examples assume TLS in front of the server. For a server on your own machine use
  `http://127.0.0.1:8000/mcp`, as [`mcp_http.json`](./mcp_http.json) does.
- A host name other than `localhost` and `127.0.0.1` has to be allowed on the server:
  `gaik-mcp --transport http --allowed-host <host>`.
