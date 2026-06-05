"""Read-only SQL validation -- the security boundary of the postgres_agent.

Every SQL string the LLM produces passes through ``validate_read_only`` before
it can be executed. Anything that cannot be proven to be a single read-only
query is rejected. This is best-effort defence in depth: the real guarantee is
a read-only database role (see the component README).
"""

from __future__ import annotations

try:
    import sqlglot
    from sqlglot import exp
except ImportError as exc:
    raise ImportError(
        "postgres_agent requires 'sqlglot'. Install extras with 'pip install gaik[postgres-agent]'"
    ) from exc


class UnsafeSQLError(ValueError):
    """Raised when a SQL string is not a single, read-only query."""


# AST node types that indicate a write, DDL, or out-of-band command.
_FORBIDDEN_NODES: tuple[type, ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Into,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Command,
    exp.Set,
)


def validate_read_only(
    sql: str,
    *,
    schema_name: str = "public",
    allowlist: list[str] | None = None,
) -> str:
    """Validate that ``sql`` is a single read-only query; return it cleaned.

    Args:
        sql: The SQL string to validate.
        schema_name: The only schema the query may reference.
        allowlist: When given, the query may only touch these tables.

    Returns:
        The re-rendered (normalized, semicolon-free) SQL -- exactly what should
        be executed.

    Raises:
        UnsafeSQLError: If the statement is not exactly one
            ``SELECT`` / ``WITH ... SELECT`` query, contains a write/DDL/command
            node, references another schema or database, or touches a table
            outside the allowlist.
    """
    if not sql or not sql.strip():
        raise UnsafeSQLError("Empty SQL statement.")

    try:
        parsed = sqlglot.parse(sql, read="postgres")
    except Exception as exc:
        raise UnsafeSQLError(f"Could not parse SQL: {exc}") from exc

    statements = [s for s in parsed if s is not None]
    if len(statements) != 1:
        raise UnsafeSQLError(f"Expected exactly one SQL statement, found {len(statements)}.")
    statement = statements[0]

    if not isinstance(statement, (exp.Select, exp.Union)):
        raise UnsafeSQLError(
            f"Only read-only SELECT queries are allowed (got {type(statement).__name__})."
        )

    forbidden = next(statement.find_all(*_FORBIDDEN_NODES), None)
    if forbidden is not None:
        raise UnsafeSQLError(
            f"Statement contains a forbidden operation: {type(forbidden).__name__}."
        )

    allowed = {t.lower() for t in allowlist} if allowlist is not None else None
    cte_names = {cte.alias.lower() for cte in statement.find_all(exp.CTE) if cte.alias}

    for table in statement.find_all(exp.Table):
        name = (table.name or "").lower()
        schema = table.db or ""
        catalog = table.catalog or ""
        if catalog:
            raise UnsafeSQLError(f"Cross-database references are not allowed ('{catalog}').")
        if schema and schema.lower() != schema_name.lower():
            raise UnsafeSQLError(f"Cross-schema reference is not allowed: '{schema}.{name}'.")
        if not schema and name in cte_names:
            continue
        if allowed is not None and name and name not in allowed:
            raise UnsafeSQLError(f"Table '{name}' is not in the allowed table list.")

    return statement.sql(dialect="postgres")
