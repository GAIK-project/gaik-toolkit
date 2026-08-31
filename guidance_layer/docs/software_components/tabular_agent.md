# Tabular Agent

A **text-to-SQL query agent for files**: point it at a CSV or Excel file, ask a
question in natural language, and get an answer backed by a validated,
read-only SQL query.

The agent loads your files into an in-memory DuckDB database, profiles every
column, asks an LLM for a SQL query, validates it, runs it, and — if the query
fails — feeds the error back to the LLM and retries.

It is the file-shaped sibling of [`postgres_agent`](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/src/gaik/software_components/postgres_agent): same
architecture, but the data source is spreadsheets rather than a database.

## Installation

```bash
pip install "gaik[tabular-agent]"
```

Pulls `duckdb` (query engine), `sqlglot` (SQL validation) and `openpyxl` (Excel
reading). For OpenAI/Azure no extra LLM dependency is needed; for Anthropic or
Google add `gaik[llm-anthropic]` or `gaik[llm-google]`.

## Quick Start

```python
from gaik.software_components.tabular_agent import TabularAgent

with TabularAgent("sales.xlsx") as agent:
    result = agent.ask("Which region had the highest total revenue?")
    print(result.answer)              # natural-language answer
    print(result.query_result.sql)    # the SQL that produced it
```

Several files at once, joined by the agent:

```python
with TabularAgent(["sales.csv", "headcount.csv"]) as agent:
    print(agent.ask("Which region has the highest revenue per employee?").answer)
```

Name the tables yourself when filenames are unhelpful:

```python
with TabularAgent({"sales": "raw_export_2026_final_v3.xlsx"}) as agent:
    print(agent.table_names)          # ['sales']
```

An Excel workbook contributes **one table per non-empty sheet**, named after the
sheet, so cross-sheet joins work out of the box.

## Features

### Supported formats

| Format | Extensions | Notes |
|--------|-----------|-------|
| CSV / TSV | `.csv`, `.tsv`, `.txt` | Delimiter, encoding and types auto-detected |
| Excel | `.xlsx`, `.xlsm`, `.xls` | One table per sheet; messy layouts handled |
| Parquet | `.parquet` | Types come from the file |
| JSON | `.json`, `.ndjson` | Records auto-detected |

### Nordic number formats

A column of `1 234,56` values is detected and converted to a real number, so
`SUM()` behaves. The conversion only fires when *every* value in the column is a
comma-decimal number, so free text containing commas is left alone.

### Messy spreadsheets

Real reports are laid out for humans: a title in row 1, a blank spacer, headers
in row 4, subtotals after every group, a "Notes:" block at the bottom. Two tiers
handle that, and the expensive one only runs when needed:

1. **Deterministic clean-up** (always, no LLM call). Blank edges are trimmed,
   the header row is detected, and on messy sheets subtotal and section rows are
   removed *structurally* — a subtotal blanks the descriptive columns but keeps
   the numbers, which needs no keyword match and so works in any language.
2. **LLM layout inference** (only when tier 1 flags a sheet as messy). The raw
   cell grid is shown to the model, which reports where the table starts and
   ends.

`layout_inference` controls **only the second tier**:

| Value | Behaviour |
|-------|-----------|
| `"auto"` (default) | Ask the LLM only for sheets that look messy |
| `"always"` | Ask for every sheet |
| `"never"` | Never ask; deterministic clean-up only, zero tokens |

Every removal is logged at `INFO`, so you can see what was dropped and why.

### Column profiling

`TabularSchema.to_prompt_text()` describes the data, not just its shape:

```
TABLE sales  -- from sales_clean.csv, 24 row(s)
(
  region VARCHAR  -- 4 distinct; values: North, East, West, South
  quarter VARCHAR  -- 3 distinct; values: Q1, Q2, Q3
  units BIGINT  -- 24 distinct; range 19..305
  revenue_eur DOUBLE  -- 12% NULL; 24 distinct; range 5700..36600
)
```

Listing the values a low-cardinality column actually holds is what stops the
model filtering on categories that do not exist. Profiling runs as ordinary
aggregate queries, so it costs no LLM tokens.

## Basic API

### TabularAgent

```python
TabularAgent(
    source: str | Path | Sequence[str | Path] | Mapping[str, str | Path],
    *,
    config: dict | None = None,          # LLM config; resolved lazily
    model: str | None = None,
    max_retries: int = 3,                # agentic retry attempts
    max_rows: int = 100,                 # hard cap on returned rows
    query_timeout_s: float = 10.0,
    memory_limit: str = "1GB",
    layout_inference: str = "auto",      # "auto" | "always" | "never"
    profile_samples: int = 3,
    extra_instructions: str | None = None,
    answer_language: str = "en",         # ISO 639-1 for the answer
    temperature: float | None = 0.0,
)
```

| Method | Needs | Description |
|--------|-------|-------------|
| `get_schema(*, refresh=False)` | files | Load and profile the tables (cached). |
| `table_names` | files | Names of the loaded tables. |
| `generate_sql(question, *, error_context=None)` | files + LLM | Generate SQL without running it. |
| `run_sql(sql)` | files | Validate `sql` as read-only and execute it (row-capped). |
| `query(question)` | files + LLM | Agentic loop: generate, validate, run, retry on error. |
| `ask(question)` | files + LLM | Full pipeline plus a natural-language answer. |

Return types:

- `get_schema()` → `TabularSchema` (has `to_prompt_text()`)
- `generate_sql()` → `GeneratedSQL` (`sql`, `reasoning`)
- `run_sql()` → `list[dict]`
- `query()` → `QueryResult` (`sql`, `rows`, `row_count`, `attempts`, `succeeded`, `error`)
- `ask()` → `AnswerResult` (`answer`, `query_result`)

`get_schema()` and `run_sql()` need no LLM credentials, so they double as tools
for an external agent framework.

### Configuration

`config` is a dict from `get_llm_config()`, resolved lazily on the first LLM
call. `extra_instructions` is appended to the SQL-generation prompt under
`Additional context:` — use it for a domain glossary or example question→SQL
pairs when column names are opaque.

`temperature` defaults to `0.0` so the same question yields the same SQL. Pass
`None` for reasoning deployments (o-series, gpt-5.x reasoning tiers), which
reject an explicit temperature.

## Security model

The agent executes LLM-generated SQL, so there are **two independent layers**.

**1. SQL validation.** Every query is parsed with `sqlglot` and rejected unless
it is a single read-only `SELECT`. This is stricter than the `postgres_agent`
equivalent, because DuckDB reaches the filesystem from *inside* a `SELECT`:

```sql
SELECT * FROM read_csv('/etc/passwd')   -- parses as a plain SELECT
SELECT * FROM glob('/**')               -- so does this
```

So beyond the usual write/DDL rejection, the validator refuses file-reading
table functions, `ATTACH` / `INSTALL` / `PRAGMA` / `COPY`, and **any function
`sqlglot` does not recognise** — an allowlist rather than a denylist, which is
what makes it hold for DuckDB extension functions that do not exist yet.

**2. A locked-down engine.** External access is enabled only while the loader
reads the paths you passed in. Before a single generated query runs:

```sql
SET enable_external_access = false;
SET lock_configuration = true;
```

After that DuckDB itself refuses to read files, install extensions, attach
databases, or re-enable any of it — even if a query bypassed layer 1. Queries
are further capped by `max_rows`, `query_timeout_s` and `memory_limit`.

**Why not run Python?** A pandas-style agent that `exec`s generated code is more
capable and far more dangerous: prompt injection through a spreadsheet cell
turns into remote code execution (CVE-2024-12366). Running that safely needs a
real sandbox, which is not available under OpenShift's `restricted-v2` security
context. Validated SQL trades charts and modelling for being auditable and
deployable anywhere.

Treat spreadsheet contents as untrusted input regardless: cell values reach the
LLM prompt, so a hostile file can attempt prompt injection. The two layers above
bound the blast radius to a wrong answer from your own data.

## Limitations

- Read-only; source files are never modified.
- No charts, regression or forecasting — SQL only.
- Best for small/medium files; the whole profiled schema goes in the prompt.
- Column names must mean something, or supply `extra_instructions`.
- In a messy sheet, a data row missing one of its *descriptive* fields is
  structurally indistinguishable from a subtotal and may be dropped. Rows
  missing a *numeric* value are always kept, and tidy sheets are never touched.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `AZURE_API_KEY` / `AZURE_ENDPOINT` | Azure OpenAI for SQL generation |
| `OPENAI_API_KEY` | Standard OpenAI as an alternative |
| `LLM_PROVIDER` | `openai`, `azure`, `anthropic`, `google` |

## Examples

- [tabular_agent_example.py](../../../implementation_layer/examples/software_components/tabular_agent/tabular_agent_example.py)
  — single CSV, Nordic CSV answered in Finnish, cross-sheet join, tool-style use
- [tabular_agent_messy_excel_example.py](../../../implementation_layer/examples/software_components/tabular_agent/tabular_agent_messy_excel_example.py)
  — the raw cell grid of a report-style sheet next to the clean table the agent queries

Run `make_fixtures.py` in that directory first to generate the sample files.

## Resources

- Component source and README:
  [software_components/tabular_agent](../../../implementation_layer/src/gaik/software_components/tabular_agent/)
- [Securing DuckDB](https://duckdb.org/docs/stable/operations_manual/securing_duckdb/overview)

## License

MIT — see the repository `LICENSE`.
