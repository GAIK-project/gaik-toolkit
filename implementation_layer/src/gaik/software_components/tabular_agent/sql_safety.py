"""Read-only SQL validation -- the security boundary of the tabular_agent.

Every SQL string the LLM produces passes through ``validate_read_only`` before
it can be executed. Anything that cannot be proven to be a single read-only
query over the loaded tables is rejected.

This is stricter than the postgres_agent equivalent, and deliberately so.
DuckDB reaches the filesystem and the network from *inside* a ``SELECT`` via
table functions -- ``SELECT * FROM read_csv('/etc/passwd')`` parses as a plain
``exp.Select``, so a statement-type check alone lets it through. Two extra
rules close that hole:

* file/network-reading table functions are rejected by node type, and
* **any function sqlglot does not recognise is rejected** (``exp.Anonymous``).
  ``glob('/**')`` parses as an anonymous call, so an allowlist is the only
  approach that holds; a denylist would have to enumerate every DuckDB
  extension function that will ever exist.

Like the postgres_agent, this is defence in depth rather than a sandbox. The
second layer is the connection itself, locked with ``enable_external_access =
false`` and ``lock_configuration = true`` before any generated SQL runs -- see
``loader.lock_down``.
"""

from __future__ import annotations

try:
    import sqlglot
    from sqlglot import exp
except ImportError as exc:
    raise ImportError(
        "tabular_agent requires 'sqlglot'. Install extras with 'pip install gaik[tabular-agent]'"
    ) from exc


class UnsafeSQLError(ValueError):
    """Raised when a SQL string is not a single, read-only query."""


# AST node types that indicate a write, DDL, or out-of-band command. The first
# group mirrors postgres_agent; the second is DuckDB-specific escape hatches.
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
    exp.Command,  # LOAD httpfs and friends parse as a generic Command
    exp.Set,
    exp.Attach,
    exp.Detach,
    exp.Copy,
    exp.Export,
    exp.Install,
    exp.Pragma,
    exp.Use,
)

# Table functions that read from outside the database. sqlglot models some of
# these as dedicated nodes; the rest are caught by the Anonymous rule below.
_FILE_ACCESS_NODES: tuple[type, ...] = (
    exp.ReadCSV,
    exp.ReadParquet,
)


def validate_read_only(sql: str, *, allowed_tables: list[str] | None = None) -> str:
    """Validate that ``sql`` is a single read-only query; return it cleaned.

    Args:
        sql: The SQL string to validate.
        allowed_tables: When given, the query may only touch these tables.
            CTE names defined within the query are always allowed.

    Returns:
        The re-rendered (normalized, semicolon-free) SQL -- exactly what should
        be executed.

    Raises:
        UnsafeSQLError: If the statement is not exactly one
            ``SELECT`` / ``WITH ... SELECT`` query, contains a write/DDL/command
            node, calls a file-reading or unrecognised function, references
            another database, or touches a table outside ``allowed_tables``.
    """
    if not sql or not sql.strip():
        raise UnsafeSQLError("Empty SQL statement.")

    try:
        parsed = sqlglot.parse(sql, read="duckdb")
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

    file_access = next(statement.find_all(*_FILE_ACCESS_NODES), None)
    if file_access is not None:
        raise UnsafeSQLError(
            f"Reading external files is not allowed ({type(file_access).__name__}). "
            "Query the already-loaded tables instead."
        )

    # Anything sqlglot cannot name is rejected outright. This is what stops
    # glob(), read_text(), read_blob() and every future DuckDB extension
    # function without needing to know them by name.
    unknown = next(statement.find_all(exp.Anonymous), None)
    if unknown is not None:
        raise UnsafeSQLError(
            f"Unrecognized function '{unknown.name}' is not allowed. "
            "Use standard SQL functions only."
        )

    allowed = {t.lower() for t in allowed_tables} if allowed_tables is not None else None
    cte_names = {cte.alias.lower() for cte in statement.find_all(exp.CTE) if cte.alias}

    for table in statement.find_all(exp.Table):
        name = (table.name or "").lower()
        schema = table.db or ""
        catalog = table.catalog or ""
        if catalog:
            raise UnsafeSQLError(f"Cross-database references are not allowed ('{catalog}').")
        if not schema and name in cte_names:
            continue
        if schema and schema.lower() not in ("main", "temp"):
            raise UnsafeSQLError(f"Cross-schema reference is not allowed: '{schema}.{name}'.")
        if allowed is not None and name and name not in allowed:
            raise UnsafeSQLError(f"Table '{name}' is not in the allowed table list.")

    return statement.sql(dialect="duckdb")
