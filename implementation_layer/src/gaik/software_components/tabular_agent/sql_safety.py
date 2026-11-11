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

from collections.abc import Callable

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
            A CTE name is allowed where that CTE is in scope; inside its own
            body (without ``RECURSIVE``) or in an earlier CTE the name is an
            ordinary table and is checked like one.

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

    # DuckDB identifiers are case-insensitive, quoted or not, so names compare
    # in lower case.
    allowed = {t.lower() for t in allowed_tables} if allowed_tables is not None else None

    def check_table(table: exp.Table, visible_ctes: frozenset[str]) -> None:
        name = (table.name or "").lower()
        schema = table.db or ""
        catalog = table.catalog or ""
        if catalog:
            raise UnsafeSQLError(f"Cross-database references are not allowed ('{catalog}').")
        if not schema and name in visible_ctes:
            return
        if schema and schema.lower() not in ("main", "temp"):
            raise UnsafeSQLError(f"Cross-schema reference is not allowed: '{schema}.{name}'.")
        if allowed is not None and name and name not in allowed:
            raise UnsafeSQLError(f"Table '{name}' is not in the allowed table list.")

    _walk_tables(statement, frozenset(), check_table)

    return statement.sql(dialect="duckdb")


def _walk_tables(
    node: exp.Expression,
    visible_ctes: frozenset[str],
    check: Callable[[exp.Table, frozenset[str]], None],
) -> None:
    """Call ``check`` on every table with the CTE names in scope at that point.

    A CTE is visible to the CTEs after it in the same ``WITH`` and to the query
    the ``WITH`` belongs to. It is visible inside its own body only under
    ``WITH RECURSIVE``. Everywhere else the same name is an ordinary table.
    """
    # sqlglot renamed this argument from "with" to "with_".
    with_ = node.args.get("with_") or node.args.get("with")
    if isinstance(with_, exp.With):
        recursive = bool(with_.args.get("recursive"))
        for cte in with_.expressions:
            name = (cte.alias or "").lower()
            in_body = visible_ctes | {name} if recursive and name else visible_ctes
            _walk_tables(cte, in_body, check)
            if name:
                visible_ctes = visible_ctes | {name}
    if isinstance(node, exp.Table):
        check(node, visible_ctes)
    for child in node.iter_expressions():
        if child is not with_:
            _walk_tables(child, visible_ctes, check)
