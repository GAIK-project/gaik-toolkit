# Tabular Agent examples

Ask CSV and Excel files questions in natural language.
[`TabularAgent`](../../../src/gaik/software_components/tabular_agent/) loads
them into DuckDB, profiles every column, generates a validated read-only SQL
query, runs it, and answers.

## Prerequisites

```bash
pip install "gaik[tabular-agent]"
```

Set LLM credentials in `implementation_layer/examples/.env` (Azure OpenAI shown;
`OPENAI_API_KEY` works too, with `LLM_PROVIDER=openai`):

```
AZURE_API_KEY=your-key
AZURE_ENDPOINT=https://your-endpoint.openai.azure.com/
```

## Generate the sample files

The `input/` files are produced by a script rather than committed by hand.
Everything in them is synthetic -- invented company names and made-up numbers,
safe to share.

```bash
python make_fixtures.py
```

| File | What it exercises |
|------|-------------------|
| `sales_clean.csv` | A tidy export -- the happy path, no LLM clean-up needed |
| `sales_semicolon.csv` | Nordic conventions: `;` separator, `,` decimals, UTF-8 BOM |
| `messy_report.xlsx` | A human-facing report: title rows, subtotals, trailing notes |
| `multi_sheet.xlsx` | Two sheets that only answer a question when joined |

## Run

```bash
python tabular_agent_example.py
```

Covers four things: a single CSV, a Nordic CSV answered in Finnish, a
cross-sheet join, and tool-style use (schema plus raw SQL, no LLM credentials
needed).

```bash
python tabular_agent_messy_excel_example.py
```

Prints the raw cell grid of a report-style spreadsheet, then the clean table
the agent ends up querying -- so you can see exactly which rows were removed.
Most of that work is deterministic and costs no tokens; `layout_inference`
controls only the extra LLM call.

## What to look at

Both examples print the SQL behind every answer. That is the point of the
component: the answer is checkable, because you can read the query that
produced it and re-run it yourself.

`get_schema().to_prompt_text()` shows what the model actually sees -- including
the distinct values of low-cardinality columns, which is what stops it from
filtering on categories that do not exist.
