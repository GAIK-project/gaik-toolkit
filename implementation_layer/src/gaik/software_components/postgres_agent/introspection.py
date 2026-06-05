"""Read-only schema introspection for the postgres_agent component."""

from __future__ import annotations

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
        allowlist: When given, only these tables are included.
        include_samples: When True, attach up to three sample rows per table.

    Returns:
        A ``SchemaInfo`` describing every (allowed) base table and view.
    """
    allowed = {t.lower() for t in allowlist} if allowlist else None

    table_rows = conn.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = %s AND table_type IN ('BASE TABLE', 'VIEW')
        ORDER BY table_name
        """,
        (schema_name,),
    ).fetchall()
    table_names = [
        r["table_name"] for r in table_rows if allowed is None or r["table_name"].lower() in allowed
    ]

    column_rows = conn.execute(
        """
        SELECT table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = %s
        ORDER BY table_name, ordinal_position
        """,
        (schema_name,),
    ).fetchall()

    pk_rows = conn.execute(
        """
        SELECT kcu.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = %s AND tc.constraint_type = 'PRIMARY KEY'
        """,
        (schema_name,),
    ).fetchall()
    primary_keys = {(r["table_name"], r["column_name"]) for r in pk_rows}

    fk_rows = conn.execute(
        """
        SELECT
            kcu.table_name AS table_name,
            kcu.column_name AS column_name,
            ccu.table_name AS foreign_table,
            ccu.column_name AS foreign_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name
         AND tc.table_schema = ccu.table_schema
        WHERE tc.table_schema = %s AND tc.constraint_type = 'FOREIGN KEY'
        """,
        (schema_name,),
    ).fetchall()
    foreign_keys = {
        (r["table_name"], r["column_name"]): f"{r['foreign_table']}.{r['foreign_column']}"
        for r in fk_rows
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
