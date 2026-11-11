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
  `INSERT`/`UPDATE`/`DELETE`, no DDL, no data import, no `FOR UPDATE`.
- **One schema.** The agent operates on a single schema (`schema_name`).
  Cross-schema and cross-database references are rejected, and unqualified
  table names are read from that schema only.
- **Standard functions only.** Text, number, date, JSON, array, aggregate and
  window functions work. Other functions, including your own and those of
  extensions, are rejected (see [Security model](#security-model)).
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

The agent executes LLM-generated SQL. Three layers limit what it can do:

1. **Validation** (`validate_read_only`, `sqlglot`-based) before anything is
   sent to the database. A query is rejected unless it is a single `SELECT` /
   `WITH ... SELECT` and passes these checks:
   - no DDL/DML, no `SELECT ... INTO`, no row locks (`FOR UPDATE`, `FOR SHARE`);
   - **functions come from an allowlist**: the ones `sqlglot` models as
     standard SQL plus the names in `sql_safety.SAFE_FUNCTIONS`. Functions
     that run SQL text, change settings, read files or sequences, or sleep are
     not on it, and neither are your own functions or extension functions.
     Schema-qualified function calls are rejected;
   - tables are in `schema_name` and, when `table_allowlist` is given, on it.
     Unqualified table names are rewritten to `schema.table`, so a name cannot
     resolve to a system catalog or another schema on the search path. The
     SQL that runs is this rewritten form; `QueryResult.sql` keeps the query
     as the LLM wrote it;
   - a CTE name counts as a CTE only where that CTE is in scope. Inside its
     own body (without `RECURSIVE`) or in an earlier CTE the name is a table
     and is checked like one;
   - identifiers are compared as PostgreSQL does: unquoted names fold to
     lower case, quoted names keep their case. `"Users"` and `users` are two
     tables.
2. **A read-only transaction per query.** `run_sql()` runs each query in its
   own transaction, started `READ ONLY` and always rolled back, with a
   `statement_timeout`. A write fails in PostgreSQL, and a session setting
   changed inside a query does not outlive it. The connection also sets
   `default_transaction_read_only=on`.
3. **The database role** the agent connects with.

**Validation is best-effort. The real guarantee is a read-only database role.**
A read-only transaction stops writes to tables, but not everything a
privileged role can do through functions, so do not give the agent a
superuser or the role that owns the schema.
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

Allowlist entries are table names as PostgreSQL stores them, so they are
case-sensitive: write `customers` for a table created as `customers` or
`Customers`, and `Users` only for one created as `"Users"`.

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
    extra_instructions: str | None = None,   # appended to the SQL prompt
    answer_language: str = "en",             # ISO 639-1 for the answer
)
```

`config` is only resolved on the first LLM call, so `get_schema()` and
`run_sql()` work without LLM credentials.

#### `extra_instructions`

Free-form text appended to the SQL-generation user prompt under
`Additional context:`. Use it to inject a domain glossary, naming conventions,
or canonical question→SQL examples. The agent stays schema-agnostic; this is
the hook for project-specific knowledge that lives outside the table/column
names.

```python
extra = """
Domain notes:
- discount_percent is the customer discount in %, 0–100.
- A "discount customer" has discount_percent > 0.

Examples:
Q: Which customers have a discount?
SQL: SELECT customer_id, name, discount_percent
     FROM customers WHERE discount_percent > 0;
"""

with PostgresAgent(dsn, extra_instructions=extra) as agent:
    print(agent.ask("Which customers have a discount?").answer)
```

#### `answer_language`

ISO 639-1 code (e.g. `"en"`, `"fi"`, `"sv"`, `"de"`, `"fr"`, `"es"`,
`"no"`, `"da"`). The default `"en"` does not touch the answer prompt. Any
other value appends `Reply in <language>.` to the answer-synthesis system
prompt; unknown codes are passed through verbatim.

This only affects the natural-language answer from `ask()` — the generated
SQL is always SQL, regardless of language.

See
[postgres_agent_with_context_example.py](../../../../examples/software_components/postgres_agent/postgres_agent_with_context_example.py)
for a complete example using both options.

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
