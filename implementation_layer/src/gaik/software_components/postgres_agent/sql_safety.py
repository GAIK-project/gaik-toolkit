"""Read-only SQL validation -- the security boundary of the postgres_agent.

Every SQL string the LLM produces passes through ``validate_read_only`` before
it can be executed. Anything that cannot be proven to be a single read-only
query over the agent's schema is rejected:

* only one ``SELECT`` / ``WITH ... SELECT`` statement, without row locks;
* **only functions on an allowlist**. PostgreSQL has functions that run SQL
  text, change session settings, read files or have other side effects, and
  extensions add more, so a denylist cannot hold. Functions sqlglot models as
  their own node are standard SQL; every other call must be named in
  ``SAFE_FUNCTIONS``;
* every table reference is resolved the way PostgreSQL resolves it: a name is
  a CTE only where that CTE is in scope, quoted identifiers keep their case,
  and every other unqualified name is rewritten to ``schema.table`` so it can
  never resolve to a relation in another schema on the search path.

This is defence in depth. The agent also runs each query in a transaction
started ``READ ONLY`` and rolls it back, and the real guarantee is a read-only
database role (see the component README).
"""

from __future__ import annotations

from collections.abc import Callable

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

# Functions sqlglot has no node of its own for, and that only compute a value
# from their arguments. Anything else that parses as a generic call is rejected.
SAFE_FUNCTIONS: frozenset[str] = frozenset(
    # text
    "ascii bit_length btrim char_length character_length chr concat concat_ws format "
    "initcap left length lower lpad ltrim md5 octet_length overlay position quote_ident "
    "quote_literal quote_nullable regexp_count regexp_instr regexp_like regexp_match "
    "regexp_matches regexp_replace regexp_split_to_array regexp_split_to_table "
    "regexp_substr repeat replace reverse right rpad rtrim split_part starts_with "
    "string_to_array strpos substr substring to_hex translate trim unaccent upper "
    # numbers
    "abs cbrt ceil ceiling degrees div exp floor gcd greatest lcm least ln log log10 mod "
    "pi power radians random round scale sign sqrt trunc width_bucket "
    # dates and times
    "age clock_timestamp date_add date_bin date_part date_subtract date_trunc isfinite "
    "justify_days justify_hours justify_interval make_date make_interval make_time "
    "make_timestamp make_timestamptz now statement_timestamp timeofday timezone to_char "
    "to_date to_number to_timestamp transaction_timestamp "
    # aggregates and window functions
    "array_agg avg bit_and bit_or bool_and bool_or corr count covar_pop covar_samp "
    "cume_dist dense_rank every first_value json_agg json_object_agg jsonb_agg "
    "jsonb_object_agg lag last_value lead max min mode nth_value ntile percent_rank "
    "percentile_cont percentile_disc rank regr_intercept regr_r2 regr_slope row_number "
    "stddev stddev_pop stddev_samp string_agg sum var_pop var_samp variance "
    # conditionals and null handling
    "coalesce nullif num_nonnulls num_nulls "
    # arrays and set-returning helpers
    "array_append array_cat array_dims array_length array_lower array_ndims "
    "array_position array_positions array_prepend array_remove array_replace "
    "array_to_string array_upper cardinality generate_series generate_subscripts unnest "
    # json
    "json_array_elements json_array_elements_text json_array_length json_build_array "
    "json_build_object json_each json_each_text json_extract_path json_extract_path_text "
    "json_object_keys json_strip_nulls json_typeof jsonb_array_elements "
    "jsonb_array_elements_text jsonb_array_length jsonb_build_array jsonb_build_object "
    "jsonb_each jsonb_each_text jsonb_extract_path jsonb_extract_path_text "
    "jsonb_object_keys jsonb_pretty jsonb_set jsonb_strip_nulls jsonb_typeof row_to_json "
    "to_json to_jsonb "
    # text search and similarity
    "phraseto_tsquery plainto_tsquery similarity to_tsquery to_tsvector ts_headline "
    "ts_rank ts_rank_cd websearch_to_tsquery word_similarity".split()
)

# Checked against every function, including those sqlglot has a node for, so a
# sqlglot release that starts to model one of these cannot let it through.
_DENIED_FUNCTION_PREFIXES: tuple[str, ...] = ("pg_", "lo_", "dblink", "binary_upgrade")
_DENIED_FUNCTIONS: frozenset[str] = frozenset(
    "set_config current_setting nextval setval currval lastval txid_current "
    "query_to_xml query_to_xml_and_xmlschema query_to_xmlschema "
    "table_to_xml table_to_xml_and_xmlschema table_to_xmlschema "
    "schema_to_xml schema_to_xml_and_xmlschema schema_to_xmlschema "
    "database_to_xml database_to_xml_and_xmlschema database_to_xmlschema "
    "cursor_to_xml cursor_to_xmlschema ts_stat ts_rewrite crosstab".split()
)


def _fold(identifier: exp.Identifier) -> str:
    """The name PostgreSQL looks up: quoted keeps its case, unquoted folds to lower."""
    name = identifier.name
    return name if identifier.args.get("quoted") else name.lower()


def _check_functions(statement: exp.Expression) -> None:
    """Reject every function call that is not known to be free of side effects."""
    for func in statement.find_all(exp.Func):
        # exp.Anonymous and a few aggregate variants carry the called name as text.
        if isinstance(func, exp.Anonymous) or isinstance(func.this, str):
            names = {str(func.this).lower()}
            allowed = names <= SAFE_FUNCTIONS
        else:
            names = {name.lower() for name in type(func).sql_names()}
            allowed = True
        if not allowed or any(
            n in _DENIED_FUNCTIONS or n.startswith(_DENIED_FUNCTION_PREFIXES) for n in names
        ):
            raise UnsafeSQLError(
                f"Function '{sorted(names)[0]}' is not allowed. Use standard SQL functions "
                "for text, numbers, dates, JSON and aggregation only."
            )
        parent = func.parent
        qualified = (isinstance(parent, exp.Dot) and parent.expression is func) or (
            isinstance(parent, exp.Table) and (parent.args.get("db") or parent.args.get("catalog"))
        )
        if qualified:
            raise UnsafeSQLError(
                f"Schema-qualified function calls are not allowed ('{sorted(names)[0]}')."
            )


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
            alias = cte.args.get("alias")
            identifier = alias.this if alias is not None else None
            name = _fold(identifier) if isinstance(identifier, exp.Identifier) else None
            in_body = visible_ctes | {name} if recursive and name else visible_ctes
            _walk_tables(cte, in_body, check)
            if name:
                visible_ctes = visible_ctes | {name}
    if isinstance(node, exp.Table):
        check(node, visible_ctes)
    for child in node.iter_expressions():
        if child is not with_:
            _walk_tables(child, visible_ctes, check)


def validate_read_only(
    sql: str,
    *,
    schema_name: str = "public",
    allowlist: list[str] | None = None,
) -> str:
    """Validate that ``sql`` is a single read-only query; return it cleaned.

    Args:
        sql: The SQL string to validate.
        schema_name: The only schema the query may reference. It is read as an
            unquoted identifier, so it folds to lower case, as it does in the
            agent's ``search_path``.
        allowlist: When given, the query may only touch these tables. Entries
            are table names as PostgreSQL stores them, so they are
            case-sensitive: ``Users`` names the table created as ``"Users"``,
            and ``users`` the one created as ``users`` or ``Users``.

    Returns:
        The re-rendered SQL -- exactly what should be executed. It is
        normalized and semicolon-free, and every table reference that is not a
        CTE is qualified with ``schema_name``.

    Raises:
        UnsafeSQLError: If the statement is not exactly one
            ``SELECT`` / ``WITH ... SELECT`` query, contains a write/DDL/command
            node or a row lock, calls a function outside the allowlist,
            references another schema or database, or touches a table outside
            the allowlist.
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

    if next(statement.find_all(exp.Lock), None) is not None:
        raise UnsafeSQLError("Row locks (FOR UPDATE / FOR SHARE) are not allowed.")

    _check_functions(statement)

    schema_key = schema_name.lower()
    allowed = set(allowlist) if allowlist is not None else None

    def check_table(table: exp.Table, visible_ctes: frozenset[str]) -> None:
        if table.args.get("catalog"):
            raise UnsafeSQLError(f"Cross-database references are not allowed ('{table.catalog}').")
        identifier = table.this
        if not isinstance(identifier, exp.Identifier):
            return  # a function in FROM; _check_functions has covered it
        name = _fold(identifier)
        schema = table.args.get("db")
        if schema is not None:
            if _fold(schema) != schema_key:
                raise UnsafeSQLError(
                    f"Cross-schema reference is not allowed: '{schema.name}.{name}'."
                )
        elif name in visible_ctes:
            return
        else:
            # Unqualified names resolve through the search path, where system
            # schemas come first. Naming the schema removes that lookup.
            table.set("db", exp.to_identifier(schema_key, quoted=True))
        if allowed is not None and name not in allowed:
            raise UnsafeSQLError(f"Table '{name}' is not in the allowed table list.")

    _walk_tables(statement, frozenset(), check_table)

    return statement.sql(dialect="postgres")
