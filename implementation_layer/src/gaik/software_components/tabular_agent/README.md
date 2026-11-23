# Tabular Agent

A **text-to-SQL query agent for files**: point it at a CSV or Excel file, ask a
question in natural language, and get an answer backed by a validated,
read-only SQL query.

The agent loads your files into an in-memory DuckDB database, profiles every
column, asks an LLM for a SQL query, validates it, runs it, and -- if the query
fails -- feeds the error back to the LLM and retries (a lightweight agentic
loop).

It is the file-shaped sibling of [`postgres_agent`](../postgres_agent/):
same architecture, but the data source is spreadsheets rather than a database.

## Scope & limitations

- **Read-only.** Only `SELECT` / `WITH ... SELECT` queries. Your source files
  are never modified, and nothing outside the loaded tables is reachable.
- **Analytical questions, not data science.** Aggregation, filtering, grouping
  and joins across files. No charts, no regression, no forecasting -- there is
  no Python execution anywhere in this component, by design (see
  *Security model*).
- **Best for small / medium files.** Everything is held in memory, and the
  whole profiled schema goes into the LLM prompt.
- **Column names must mean something.** A sheet whose headers are `Column1`,
  `Column2` gives the model nothing to reason about. Use `extra_instructions`
  to supply a glossary when the names are opaque.
- **Subtotal rows in messy sheets are detected structurally.** A data row that
  is missing one of its *descriptive* fields looks exactly like a subtotal row
  and may be dropped. Rows missing a *numeric* value are always kept, and tidy
  sheets are never touched. Removals are logged at `INFO`; check the log if a
  row count looks wrong.

## Installation

```bash
pip install "gaik[tabular-agent]"
```

For OpenAI/Azure no extra LLM dependency is needed. For Anthropic or Google,
also install `gaik[llm-anthropic]` or `gaik[llm-google]`.

## Quick start

```python
from gaik.software_components.tabular_agent import TabularAgent

with TabularAgent("sales.xlsx") as agent:
    result = agent.ask("Which region had the highest total revenue?")
    print(result.answer)              # natural-language answer
    print(result.query_result.sql)    # the SQL that produced it
```

`ask()` is the one-liner path. Files are loaded, and the LLM client created,
lazily on first use.

### Several files at once

```python
with TabularAgent(["sales.csv", "headcount.csv"]) as agent:
    print(agent.ask("Which region has the highest revenue per employee?").answer)
```

Name the tables yourself with a mapping -- useful when filenames are ugly:

```python
with TabularAgent({"sales": "raw_export_2026_final_v3.xlsx"}) as agent:
    print(agent.table_names)          # ['sales']
```

An Excel workbook contributes **one table per non-empty sheet**, named after
the sheet, so cross-sheet joins work out of the box.

## Supported formats

| Format | Extensions | Notes |
|--------|-----------|-------|
| CSV / TSV | `.csv`, `.tsv`, `.txt` | Delimiter, encoding and types auto-detected |
| Excel | `.xlsx`, `.xlsm`, `.xls` | One table per sheet; messy layouts handled |
| Parquet | `.parquet` | Types come from the file |
| JSON | `.json`, `.ndjson` | Records auto-detected |

**Nordic number formats work.** A column of `1 234,56` values (thousands
grouped by a space, a no-break space or a dot, or not grouped) is detected and
converted to a real number, so `SUM()` behaves. The conversion only fires when
*every* value in the column is a comma-decimal number, so free text containing
commas is left alone, and when at least one value cannot be a thousands
separator (`3,5`, `0,250`, `1 234,56`): a column holding only values like
`1,200` and `12,000` may be US thousands grouping, so it stays text rather than
becoming 1.2 and 12.0. That holds for a column of three-decimal values such as
`1,500` and `2,250` too. A sign (`+1,5`) is fine; a value with a unit
(`12,5 %`, `1 234,56 €`) stays text, so the unit is not dropped from it.

## Messy spreadsheets

Real reports are laid out for humans: a title in row 1, a blank spacer, headers
in row 4, subtotals after every group, a "Notes:" block at the bottom. Two
tiers handle that, and the expensive one only runs when it is needed:

1. **Deterministic clean-up** (always, no LLM call). Blank edges are trimmed,
   the header row is found by looking for the first mostly-populated,
   mostly-textual row, and columns are named after the header text as a CSV's
   are (`Määrä` stays `Määrä`; a blank header becomes `column_<n>`, a repeat
   gets a suffix). On sheets that look messy,
   interleaved subtotal and section rows are then removed *structurally* -- a
   subtotal blanks the descriptive columns but keeps the numbers, which is
   recognisable without matching words like "total" or "yhteensä", so it works
   in any language. Tidy sheets are never flagged, so nothing is removed from
   them.
2. **LLM layout inference** (only when tier 1 flags the sheet as messy). The
   raw cell grid is shown to the model, which reports where the table actually
   starts and ends. This catches what shape analysis cannot: a trailing
   commentary block whose rows happen to be as wide as the data, a second table
   further down the sheet, or spacer columns in the middle.

`layout_inference` controls **only the second tier** -- the LLM call. Tier 1 is
part of loading and always applies:

| Value | Behaviour |
|-------|-----------|
| `"auto"` (default) | Ask the LLM only for sheets that look messy |
| `"always"` | Ask for every sheet |
| `"never"` | Never ask; deterministic clean-up only, zero tokens |

If inference fails or returns something nonsensical, the agent logs a warning
and falls back to the heuristic result rather than erroring. Every removal is
logged at `INFO`, so you can always see what was dropped and why:

```
INFO Layout inferred for report.xlsx / Sales: rows 0-1 are titles, row 2 is the header...
INFO Dropped 3 subtotal/section row(s) from a messy sheet
```

## Security model

The agent executes LLM-generated SQL, so there are **two independent layers**.

**1. SQL validation.** Every generated query is parsed with `sqlglot` and
rejected unless it is a single read-only `SELECT`. This is deliberately
stricter than the `postgres_agent` equivalent, because DuckDB can reach the
filesystem and the network from *inside* a `SELECT`:

```sql
SELECT * FROM read_csv('/etc/passwd')   -- parses as a plain SELECT
SELECT * FROM glob('/**')               -- so does this
```

So on top of the usual write/DDL rejection, the validator refuses file-reading
table functions, `ATTACH` / `INSTALL` / `PRAGMA` / `COPY`, and **any function
`sqlglot` does not recognise**. That last rule is an allowlist rather than a
denylist, which is what makes it hold for DuckDB extension functions that do
not exist yet.

Queries may only read the loaded tables. A CTE name counts as a CTE only where
that CTE is in scope; inside its own body (without `RECURSIVE`) or in an
earlier CTE the name is a table and must be one of the loaded ones.

The SQL that runs is rendered from the checked syntax tree. A query that
`sqlglot` cannot render without dropping part of it, or that it reads without
one of a function's arguments (such as a time zone given to `date_trunc`), is
rejected, so the agent asks the LLM for another one. The argument check also
covers functions `sqlglot` reads with a parser of their own (such as `arg_max`
and `quantile_cont`), and it runs the same with sqlglot's compiled build
(`sqlglot[c]`).

**2. A locked-down engine.** External access is enabled only while *our own*
loader reads the paths you passed in. Before a single generated query runs, the
connection is closed off permanently:

```sql
SET enable_external_access = false;
SET lock_configuration = true;
```

After that, DuckDB itself refuses to read files, install extensions, attach
databases, or re-enable any of it -- even if a query somehow bypassed layer 1.
Queries are additionally capped by `max_rows`, `query_timeout_s` and
`memory_limit`.

**Why not run Python?** A pandas-style agent that `exec`s generated code is
strictly more capable and strictly more dangerous: prompt injection through a
spreadsheet cell turns straight into remote code execution (this is
[CVE-2024-12366](https://kb.cert.org/vuls/id/148244)). Running such code safely
needs a real sandbox, which is not available under OpenShift's `restricted-v2`
security context. Validated SQL gives up charts and modelling in exchange for
being auditable and deployable anywhere.

Treat spreadsheet contents as untrusted input regardless: cell values reach the
LLM prompt, so a hostile file can attempt prompt injection. Every piece of file
content the model sees (the sheet grid for layout inference, table and column
names with their example values, a DuckDB error, the query rows for the answer)
goes in its own `<source_material>` data block, apart from the rules in the
system message ([`source_material`](../source_material.py)). This lowers the
chance that a cell steers the SQL or the answer; it does not remove it. The blast
radius is bounded to "a wrong answer from your own data" by the two layers above.

## API

### Constructor

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
    limits: InputLimits | None = None,   # file size and rows per sheet/file
)
```

`limits` (default `InputLimits()`) holds `max_file_bytes` (100 MiB, checked in the
constructor; an .xlsx may unpack to 10 × that) and `max_table_rows` (1,000,000 per sheet
or flat file, checked while loading). A file over a limit raises `InputLimitError`.
`max_rows` is a different thing: it caps the rows a query returns. Excel rows are written
through a private temporary directory (mode 0700) that is removed after loading.

`config` is only resolved on the first LLM call, so `get_schema()` and
`run_sql()` work without LLM credentials.

#### `extra_instructions`

Free-form text appended to the SQL-generation prompt under
`Additional context:`. Use it for a domain glossary, unit conventions, or
canonical question→SQL examples -- the hook for knowledge that is not visible
in the column names.

```python
extra = """
Domain notes:
- revenue_eur is net of VAT.
- "active customer" means at least one order in the last 12 months.
"""

with TabularAgent("orders.xlsx", extra_instructions=extra) as agent:
    print(agent.ask("How many active customers do we have?").answer)
```

#### `answer_language`

ISO 639-1 code (`"en"`, `"fi"`, `"sv"`, `"de"`, `"fr"`, `"es"`, `"no"`,
`"da"`). Only affects the natural-language answer -- the generated SQL is
always SQL. Unknown codes are passed through verbatim.

#### `temperature`

Defaults to `0.0` so the same question yields the same SQL. Pass `None` to omit
the parameter entirely: reasoning deployments (OpenAI's o-series, gpt-5.x
reasoning tiers) reject an explicit temperature and run at their own setting.

### Methods

| Method | Needs | Description |
|--------|-------|-------------|
| `get_schema(*, refresh=False)` | files | Load and profile the tables (cached). |
| `table_names` | files | Names of the loaded tables. |
| `generate_sql(question, *, error_context=None)` | files + LLM | Generate SQL without running it. |
| `run_sql(sql)` | files | Validate `sql` as read-only and execute it (row-capped). |
| `query(question)` | files + LLM | Agentic loop: generate, validate, run, retry on error. |
| `ask(question)` | files + LLM | Full pipeline: `query()` plus a natural-language answer. |

`get_schema()` and `run_sql()` need no LLM credentials, so they double as tools
for an external agent framework.

### Return types

- `get_schema()` -> `TabularSchema` (has `to_prompt_text()` for a compact view)
- `generate_sql()` -> `GeneratedSQL` (`sql`, `reasoning`)
- `run_sql()` -> `list[dict]`
- `query()` -> `QueryResult` (`sql`, `rows`, `row_count`, `attempts`, `succeeded`, `error`)
- `ask()` -> `AnswerResult` (`answer`, `query_result`)

### What the LLM actually sees

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
model from filtering on categories that do not exist, and is the single biggest
accuracy lever in the component. A table or column name that is not a plain
identifier (with a space, a sign, a leading digit or a letter outside ASCII, such
as `"Hinta (€)"` or `"Määrä"`), or that is an SQL keyword (`"order"`, `"from"`,
`"limit"`), is shown in double quotes, so the model writes it as one name that
the query reads as a column.

## Configuration

### Environment variables

| Variable | Description |
|----------|-------------|
| `AZURE_API_KEY` / `AZURE_ENDPOINT` | Azure OpenAI for SQL generation |
| `OPENAI_API_KEY` | Standard OpenAI as an alternative |
| `LLM_PROVIDER` | Provider used when `config` is omitted: any `get_llm_config()` provider (`azure` by default, or e.g. `openai`, `aitta`, `google`, `anthropic`) |

## Examples

See
[tabular_agent_example.py](../../../../examples/software_components/tabular_agent/tabular_agent_example.py)
for the basic flow and
[tabular_agent_messy_excel_example.py](../../../../examples/software_components/tabular_agent/tabular_agent_messy_excel_example.py)
for the messy-spreadsheet path. Run `make_fixtures.py` in that directory first
to generate the sample files.
