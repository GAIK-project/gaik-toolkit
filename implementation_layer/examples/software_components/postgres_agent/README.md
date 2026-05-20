# PostgreSQL Agent Example

Runnable end-to-end demo of `PostgresAgent` -- a read-only text-to-SQL query
agent. Ask a PostgreSQL database questions in natural language.

## Prerequisites

1. A local PostgreSQL instance:
   ```bash
   docker run -d --name gaik-pg -p 5432:5432 \
       -e POSTGRES_PASSWORD=postgres postgres:17
   ```
2. Install the toolkit:
   ```bash
   pip install "gaik[postgres-agent]"
   ```
3. LLM credentials in a `.env` file (Azure OpenAI shown):
   ```bash
   AZURE_API_KEY=your-key
   AZURE_ENDPOINT=https://your-endpoint.openai.azure.com/
   # Optional: override the demo database
   DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres
   ```

## Run

```bash
python postgres_agent_example.py
```

The example seeds an isolated `gaik_postgres_agent_demo` schema (4 customers,
6 orders), then demonstrates schema introspection, SQL generation, the agentic
`query()` loop, and a natural-language `ask()`.

## Files

- `postgres_agent_example.py` -- the end-to-end demo
- `seed_demo_db.py` -- creates and populates the isolated demo schema. Run it
  standalone with `python seed_demo_db.py`. It refuses to touch a non-localhost
  database unless `--force` is given.

## Notes

`PostgresAgent` is **read-only** by design: it generates and runs only `SELECT`
queries. For real databases, connect with a dedicated read-only role and pass a
`table_allowlist` -- see the
[component README](../../../src/gaik/software_components/postgres_agent/README.md).
