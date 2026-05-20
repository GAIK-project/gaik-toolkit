# PostgreSQL Agent

A **text-to-SQL query agent**: connect it to a PostgreSQL database, ask a
question in natural language, and get an answer backed by a validated,
read-only SQL query.

The agent introspects the schema, asks an LLM for a SQL query, validates it,
runs it, and -- if the query fails -- feeds the error back to the LLM and
retries (a lightweight agentic loop).

## Scope & limitations

`postgres_agent` is a **read-only SQL assistant**, not a general database
connector:

- **Read-only.** Only `SELECT` / `WITH ... SELECT` queries. No
  `INSERT`/`UPDATE`/`DELETE`, no DDL, no data import.
- **One schema.** The agent operates on a single schema (`schema_name`).
  Cross-schema and cross-database references are rejected.
- **Relational tables only.** Not a CSV importer or an ETL tool.
- **Best for small / medium schemas.** The whole schema is placed in the LLM
  prompt. For very large databases, narrow it with `table_allowlist`.

## Installation

```bash
pip install "gaik[postgres-agent]"
```

For OpenAI/Azure no extra LLM dependency is needed. For Anthropic or Google,
also install `gaik[llm-anthropic]` or `gaik[llm-google]`.

## Quick start

```python
from gaik.software_components.postgres_agent import PostgresAgent

with PostgresAgent("postgresql://user:pass@localhost:5432/db") as agent:
    result = agent.ask("Which customer placed the most orders?")
    print(result.answer)          # natural-language answer
    print(result.query_result.sql)  # the SQL that produced it
```

`ask()` is the one-liner path. The connection and the LLM client are both
created lazily.

## Security model

The agent executes LLM-generated SQL. It is validated first
(`sqlglot`-based parsing rejects non-`SELECT` statements, multi-statements,
DDL/DML, and cross-schema references), and every connection is opened with
`default_transaction_read_only=on` plus a `statement_timeout`.

**Validation is best-effort. The real guarantee is a read-only database role.**
Create one and connect with it:

```sql
CREATE ROLE gaik_readonly LOGIN PASSWORD 'choose-a-strong-password';
GRANT CONNECT ON DATABASE mydb TO gaik_readonly;
GRANT USAGE ON SCHEMA public TO gaik_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO gaik_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO gaik_readonly;
```

Then narrow the agent to exactly the tables it should see with `table_allowlist`:

```python
with PostgresAgent(
    "postgresql://gaik_readonly:...@localhost:5432/mydb",
    table_allowlist=["customers", "orders"],
) as agent:
    print(agent.ask("How much did each customer spend in total?").answer)
```

A query that touches any table outside the allowlist is rejected before it runs.

## API

### Constructor

```python
PostgresAgent(
    connection_string: str,
    *,
    config: dict | None = None,          # LLM config; resolved lazily
    model: str | None = None,
    max_retries: int = 3,                # agentic retry attempts
    max_rows: int = 100,                 # hard cap on returned rows
    statement_timeout_ms: int = 10_000,
    table_allowlist: list[str] | None = None,
    schema_name: str = "public",
)
```

`config` is only resolved on the first LLM call, so `get_schema()` and
`run_sql()` work without LLM credentials.

### Methods

| Method | Needs | Description |
|--------|-------|-------------|
| `get_schema(*, refresh=False, include_samples=False)` | DB | Introspect tables, columns, PK/FK (cached). `include_samples` attaches sample rows. |
| `generate_sql(question, *, error_context=None)` | DB + LLM | Generate a read-only SQL query without running it. |
| `run_sql(sql)` | DB | Validate `sql` as read-only and execute it (row-capped). |
| `query(question)` | DB + LLM | Agentic loop: generate, validate, run, retry on error. |
| `ask(question)` | DB + LLM | Full pipeline: `query()` plus a natural-language answer. |

`get_schema()` and `run_sql()` need only a database connection, so they double
as tools for an external agent framework.

### Return types

- `get_schema()` -> `SchemaInfo` (has `to_prompt_text()` for a compact view)
- `generate_sql()` -> `GeneratedSQL` (`sql`, `reasoning`)
- `run_sql()` -> `list[dict]`
- `query()` -> `QueryResult` (`sql`, `rows`, `row_count`, `attempts`, `succeeded`, `error`)
- `ask()` -> `AnswerResult` (`answer`, `query_result`)

## Configuration

### Environment variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string (use in your app) |
| `AZURE_API_KEY` / `AZURE_ENDPOINT` | Azure OpenAI for SQL generation |
| `OPENAI_API_KEY` | Standard OpenAI as an alternative |

## Example

See
[postgres_agent_example.py](../../../../examples/software_components/postgres_agent/postgres_agent_example.py)
for a complete working example with a seeded demo database.
