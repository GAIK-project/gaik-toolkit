"""Profile loaded tables so the LLM knows what the data actually contains.

A bare column list tells a model the column is called ``status``; a profile
tells it the column holds exactly ``open``, ``closed`` and ``pending``. That
difference is what stops generated SQL from filtering on values that never
occur, and it is the single biggest accuracy lever in a text-to-SQL agent.

Everything here runs as ordinary aggregate queries against the already-loaded
DuckDB tables, so profiling costs no LLM tokens.
"""

from __future__ import annotations

import logging
from typing import Any

from .models import ColumnProfile, TableProfile, TabularSchema

logger = logging.getLogger(__name__)

# Columns with at most this many distinct values get their values listed in
# full; above it, only a few samples are shown.
CATEGORICAL_MAX_DISTINCT = 12
# Hard cap on listed values, so one wide categorical cannot flood the prompt.
TOP_VALUE_LIMIT = 12

_NUMERIC_PREFIXES = (
    "TINYINT",
    "SMALLINT",
    "INTEGER",
    "BIGINT",
    "HUGEINT",
    "UTINYINT",
    "USMALLINT",
    "UINTEGER",
    "UBIGINT",
    "FLOAT",
    "DOUBLE",
    "DECIMAL",
    "REAL",
)
_TEMPORAL_PREFIXES = ("DATE", "TIME", "TIMESTAMP", "INTERVAL")


def _is_rangeable(data_type: str) -> bool:
    """True for types where a min/max range is meaningful to report."""
    upper = data_type.upper()
    return upper.startswith(_NUMERIC_PREFIXES) or upper.startswith(_TEMPORAL_PREFIXES)


def _render(value: Any) -> str:
    """Render a cell value compactly for the schema text."""
    if value is None:
        return "NULL"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value).strip()


def profile_tables(
    con: Any,
    tables: dict[str, str],
    *,
    sample_values: int = 3,
) -> TabularSchema:
    """Build a :class:`TabularSchema` describing every loaded table.

    Args:
        con: An open DuckDB connection holding the tables.
        tables: ``{table_name: source description}`` from the loader.
        sample_values: How many example values to show for non-categorical
            columns.

    Returns:
        A schema with one :class:`TableProfile` per table.
    """
    profiles: list[TableProfile] = []
    for name, source in tables.items():
        try:
            profiles.append(_profile_table(con, name, source, sample_values))
        except Exception as exc:  # a broken profile must not kill the agent
            logger.warning("Could not profile table '%s': %s", name, exc)
            profiles.append(TableProfile(name=name, source=source))
    return TabularSchema(tables=profiles)


def _profile_table(con: Any, name: str, source: str, sample_values: int) -> TableProfile:
    """Profile one table: row count plus a profile for every column."""
    row_count = con.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
    described = con.execute(f'DESCRIBE "{name}"').fetchall()

    columns: list[ColumnProfile] = []
    for row in described:
        column_name, data_type = row[0], row[1]
        columns.append(
            _profile_column(
                con,
                table=name,
                column=column_name,
                data_type=data_type,
                row_count=row_count,
                sample_values=sample_values,
            )
        )
    return TableProfile(name=name, source=source, row_count=row_count, columns=columns)


def _profile_column(
    con: Any,
    *,
    table: str,
    column: str,
    data_type: str,
    row_count: int,
    sample_values: int,
) -> ColumnProfile:
    """Gather counts, range and representative values for a single column."""
    quoted = f'"{table}"."{column}"'
    non_null, distinct = con.execute(
        f'SELECT count({quoted}), count(DISTINCT {quoted}) FROM "{table}"'
    ).fetchone()
    null_fraction = 0.0 if row_count == 0 else 1.0 - (non_null / row_count)

    profile = ColumnProfile(
        name=column,
        data_type=data_type,
        null_fraction=round(null_fraction, 4),
        distinct_count=distinct,
    )

    if non_null == 0:
        return profile

    if _is_rangeable(data_type):
        low, high = con.execute(f'SELECT min({quoted}), max({quoted}) FROM "{table}"').fetchone()
        profile.min_value = _render(low)
        profile.max_value = _render(high)

    if 0 < distinct <= CATEGORICAL_MAX_DISTINCT:
        rows = con.execute(
            f'SELECT {quoted} FROM "{table}" WHERE {quoted} IS NOT NULL '
            f"GROUP BY 1 ORDER BY count(*) DESC LIMIT {TOP_VALUE_LIMIT}"
        ).fetchall()
        profile.top_values = [_render(r[0]) for r in rows]
    elif sample_values > 0 and not _is_rangeable(data_type):
        rows = con.execute(
            f'SELECT DISTINCT {quoted} FROM "{table}" WHERE {quoted} IS NOT NULL '
            f"LIMIT {int(sample_values)}"
        ).fetchall()
        profile.samples = [_render(r[0]) for r in rows]

    return profile
