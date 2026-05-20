"""PostgreSQL text-to-SQL query agent.

Connect ``PostgresAgent`` to a PostgreSQL database and ask questions in natural
language. The agent introspects the schema, generates a validated read-only SQL
query, runs it, and (optionally) synthesizes a natural-language answer. A
lightweight agentic loop feeds SQL errors back to the LLM and retries.

Scope (v1): READ-ONLY relational queries against a single schema. No writes, no
DDL, no data import. SQL is parsed and validated before execution, but the real
guarantee is a read-only database role -- see ``README.md``.

Main class:
    - PostgresAgent: text-to-SQL query agent over a PostgreSQL database

Example:
    >>> from gaik.software_components.postgres_agent import PostgresAgent
    >>> with PostgresAgent("postgresql://user:pass@localhost:5432/db") as agent:
    ...     result = agent.ask("How many orders did each customer place?")
    ...     print(result.answer)

Tool-style use (no LLM needed for these):
    >>> with PostgresAgent("postgresql://user:pass@localhost:5432/db") as agent:
    ...     schema = agent.get_schema()          # introspect tables/columns
    ...     rows = agent.run_sql("SELECT * FROM customers LIMIT 10")
"""

from .agent import PostgresAgent
from .models import (
    AnswerResult,
    ColumnInfo,
    GeneratedSQL,
    QueryResult,
    SchemaInfo,
    TableInfo,
)
from .sql_safety import UnsafeSQLError, validate_read_only

__all__ = [
    "PostgresAgent",
    "AnswerResult",
    "ColumnInfo",
    "GeneratedSQL",
    "QueryResult",
    "SchemaInfo",
    "TableInfo",
    "UnsafeSQLError",
    "validate_read_only",
]

__version__ = "0.1.0"
