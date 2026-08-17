"""Tabular text-to-SQL query agent over CSV, Excel, Parquet and JSON files.

Point ``TabularAgent`` at one or more files and ask questions in natural
language. The agent loads them into an in-memory DuckDB database, profiles
every column, generates a validated read-only SQL query, runs it, and
(optionally) synthesizes a natural-language answer. A lightweight agentic loop
feeds SQL errors back to the LLM and retries.

Messy spreadsheets are handled in two tiers: deterministic heuristics find the
header row in clean exports at no token cost, and only when a sheet looks messy
(merged headers, title rows, trailing totals) is the LLM asked to locate the
real table.

Scope (v1): READ-ONLY analytical queries over the files you supply. No writes,
no DDL, no reading anything else. Generated SQL is validated *and* the DuckDB
connection is locked down before it runs -- see ``README.md``.

Main class:
    - TabularAgent: text-to-SQL query agent over tabular files

Example:
    >>> from gaik.software_components.tabular_agent import TabularAgent
    >>> with TabularAgent("sales.xlsx") as agent:
    ...     result = agent.ask("Which region had the highest total sales?")
    ...     print(result.answer)

Tool-style use (no LLM needed for these):
    >>> with TabularAgent(["sales.csv", "budget.csv"]) as agent:
    ...     schema = agent.get_schema()               # profile the loaded tables
    ...     rows = agent.run_sql("SELECT * FROM sales LIMIT 10")
"""

from .agent import TabularAgent
from .loader import (
    SUPPORTED_EXTENSIONS,
    TableLoadError,
    read_sheet_grid,
    render_grid,
)
from .models import (
    AnswerResult,
    ColumnProfile,
    GeneratedSQL,
    QueryResult,
    SheetLayout,
    TableProfile,
    TabularSchema,
)
from .sql_safety import UnsafeSQLError, validate_read_only

__all__ = [
    "TabularAgent",
    "AnswerResult",
    "ColumnProfile",
    "GeneratedSQL",
    "QueryResult",
    "SheetLayout",
    "SUPPORTED_EXTENSIONS",
    "TableLoadError",
    "TableProfile",
    "TabularSchema",
    "UnsafeSQLError",
    "read_sheet_grid",
    "render_grid",
    "validate_read_only",
]

__version__ = "0.1.0"
