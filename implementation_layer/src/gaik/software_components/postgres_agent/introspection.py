"""Read-only schema introspection for the postgres_agent component."""

from __future__ import annotations

import logging
from typing import Any

try:
    import psycopg
    from psycopg import sql
except ImportError as exc:
    raise ImportError(
        "postgres_agent requires 'psycopg[binary]'. "
        "Install extras with 'pip install gaik[postgres-agent]'"
    ) from exc

from .models import ColumnInfo, SchemaInfo, TableInfo

logger = logging.getLogger(__name__)

_SAMPLE_ROW_COUNT = 3
_PRIMITIVE = (str, int, float, bool)


def _safe_value(value: Any) -> Any:
    """Coerce a database value to a JSON-friendly primitive for rendering."""
    if value is None or isinstance(value, _PRIMITIVE):
        return value
    return str(value)


def introspect_schema(
    conn: psycopg.Connection,
    *,
    schema_name: str = "public",
    allowlist: list[str] | None = None,
    include_samples: bool = False,
) -> SchemaInfo:
    """Introspect tables, columns, primary keys and foreign keys of a schema.

    Args:
        conn: An open psycopg connection.
        schema_name: The schema to introspect.
        allowlist: When given, only these tables are included; an empty list
            includes none, as in ``validate_read_only``. ``None`` includes
            every table in the schema.
        include_samples: When True, attach up to three sample rows per table.

    Returns:
        A ``SchemaInfo`` describing every (allowed) base table and view.
    """
    # Exact names, as the SQL validator compares them: "Users" is not "users".
    allowed = set(allowlist) if allowlist is not None else None

    table_rows = conn.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = %s AND table_type IN ('BASE TABLE', 'VIEW')
        ORDER BY table_name
        """,
        (schema_name,),
    ).fetchall()
    all_names = [r["table_name"] for r in table_rows]
    table_names = [name for name in all_names if allowed is None or name in allowed]
    if allowed is not None:
        _warn_unmatched_allowlist(allowed, all_names, schema_name)

    column_rows = conn.execute(
        """
        SELECT table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = %s
        ORDER BY table_name, ordinal_position
        """,
        (schema_name,),
    ).fetchall()

    # Keys come from pg_catalog, which every role can read. information_schema
    # shows a constraint only to a role with more than SELECT on its table, so
    # a read-only role would see no keys at all there.
    pk_rows = conn.execute(
        """
        SELECT c.relname AS table_name, a.attname AS column_name
        FROM pg_catalog.pg_constraint con
        JOIN pg_catalog.pg_class c ON c.oid = con.conrelid
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        CROSS JOIN LATERAL unnest(con.conkey) AS k(attnum)
        JOIN pg_catalog.pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum
        WHERE n.nspname = %s AND con.contype = 'p'
        """,
        (schema_name,),
    ).fetchall()
    primary_keys = {(r["table_name"], r["column_name"]) for r in pk_rows}

    # Each referencing column is paired with the referenced column at the same
    # position of the same constraint, so composite keys and constraints that
    # share a name on different tables pair correctly. Only references within the
    # schema are kept: the agent cannot query another schema, and "customers.id"
    # would read as the table of that name in this one. A key into a partitioned
    # table is stored once against the table and once more against each of its
    # partitions; only the first names the table a query joins, so a key into a
    # partition is left out when the same columns also reference the table the
    # partition belongs to. A key declared against one partition stays, and so do
    # keys copied onto the partitions of a referencing table, which point at the
    # table itself. The referenced columns are not compared: a partition attached
    # later can number its columns differently. When the table itself may not be
    # read, no partition is named in its place, as one holds only part of its rows.
    fk_rows = conn.execute(
        """
        SELECT
            c.relname AS table_name,
            a.attname AS column_name,
            fc.relname AS foreign_table,
            fa.attname AS foreign_column
        FROM pg_catalog.pg_constraint con
        JOIN pg_catalog.pg_class c ON c.oid = con.conrelid
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_catalog.pg_class fc ON fc.oid = con.confrelid AND fc.relnamespace = n.oid
        CROSS JOIN LATERAL unnest(con.conkey, con.confkey) AS k(attnum, fattnum)
        JOIN pg_catalog.pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum
        JOIN pg_catalog.pg_attribute fa ON fa.attrelid = con.confrelid AND fa.attnum = k.fattnum
        WHERE n.nspname = %s AND con.contype = 'f'
          AND NOT EXISTS (
            SELECT 1
            FROM pg_catalog.pg_inherits i
            JOIN pg_catalog.pg_constraint parent
              ON parent.confrelid = i.inhparent
             AND parent.conrelid = con.conrelid
             AND parent.conkey = con.conkey
             AND parent.contype = 'f'
            WHERE i.inhrelid = con.confrelid
          )
        ORDER BY c.relname, con.conname
        """,
        (schema_name,),
    ).fetchall()
    # A reference to a table the agent may not read is left out, so the prompt
    # names only tables a query can use.
    foreign_keys = {
        (r["table_name"], r["column_name"]): f"{r['foreign_table']}.{r['foreign_column']}"
        for r in fk_rows
        if allowed is None or r["foreign_table"] in allowed
    }

    columns_by_table: dict[str, list[ColumnInfo]] = {}
    for r in column_rows:
        table = r["table_name"]
        if table not in table_names:
            continue
        columns_by_table.setdefault(table, []).append(
            ColumnInfo(
                name=r["column_name"],
                data_type=r["data_type"],
                nullable=(r["is_nullable"] == "YES"),
                is_primary_key=(table, r["column_name"]) in primary_keys,
                references=foreign_keys.get((table, r["column_name"])),
            )
        )

    tables: list[TableInfo] = []
    for name in table_names:
        table = TableInfo(name=name, columns=columns_by_table.get(name, []))
        if include_samples:
            table.sample_rows = _fetch_sample_rows(conn, schema_name, name)
        tables.append(table)

    return SchemaInfo(schema_name=schema_name, tables=tables)


def _warn_unmatched_allowlist(allowed: set[str], names: list[str], schema_name: str) -> None:
    """Log each allowlist entry that names no table, with a case-insensitive hint."""
    by_lower: dict[str, list[str]] = {}
    for name in names:
        by_lower.setdefault(name.lower(), []).append(name)
    for entry in sorted(allowed - set(names)):
        candidates = by_lower.get(entry.lower())
        hint = (
            f"; names are case-sensitive, did you mean {', '.join(repr(c) for c in candidates)}?"
            if candidates
            else ""
        )
        logger.warning(
            "table_allowlist entry %r matches no table in schema %r%s", entry, schema_name, hint
        )


def _fetch_sample_rows(
    conn: psycopg.Connection,
    schema_name: str,
    table_name: str,
) -> list[dict]:
    """Fetch a few rows from a table, with values coerced to primitives."""
    query = sql.SQL("SELECT * FROM {}.{} LIMIT {}").format(
        sql.Identifier(schema_name),
        sql.Identifier(table_name),
        sql.Literal(_SAMPLE_ROW_COUNT),
    )
    try:
        rows = conn.execute(query).fetchall()
    except psycopg.Error:
        return []
    return [{k: _safe_value(v) for k, v in row.items()} for row in rows]
