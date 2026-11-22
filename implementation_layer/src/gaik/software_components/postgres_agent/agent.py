"""PostgreSQL text-to-SQL query agent.

``PostgresAgent`` connects to a PostgreSQL database, turns a natural-language
question into a validated read-only SQL query, runs it, and (optionally)
synthesizes a natural-language answer. A lightweight agentic loop feeds SQL
errors back to the LLM and retries.

Scope (v1): READ-ONLY relational queries against a single schema. The agent
never writes -- no INSERT/UPDATE/DELETE/DDL, no data import. LLM-generated SQL
is parsed and validated before execution, but the real guarantee is a
read-only database role: see the component README.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from openai import APIError, APITimeoutError, RateLimitError

try:
    import psycopg
    from psycopg.rows import dict_row, tuple_row
except ImportError as exc:
    raise ImportError(
        "PostgresAgent requires 'psycopg[binary]'. "
        "Install extras with 'pip install gaik[postgres-agent]'"
    ) from exc

from gaik.software_components.llm.base import ProviderClient
from gaik.software_components.llm.config import get_llm_config
from gaik.software_components.llm.factory import build_compat_client
from gaik.software_components.llm.parameters import normalize_chat_kwargs
from gaik.software_components.source_material import SourceMaterial, source_material_messages

from .introspection import introspect_schema
from .models import AnswerResult, GeneratedSQL, QueryResult, SchemaInfo
from .sql_safety import UnsafeSQLError, validate_read_only

logger = logging.getLogger(__name__)

_IDENTIFIER_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")
_SYSTEM_SCHEMAS = frozenset({"information_schema", "pg_catalog", "pg_toast"})


def _check_table_allowlist(table_allowlist: object) -> list[str]:
    """Return the tables the agent may read, or raise when none are named."""
    example = "for example table_allowlist=['customers', 'orders']"
    if isinstance(table_allowlist, str):
        raise ValueError(
            f"table_allowlist must be a list of table names, not a string ({example})."
        )
    if not table_allowlist:
        raise ValueError(
            "PostgresAgent needs table_allowlist: the tables and views it may read, "
            f"{example}. The agent reads no table that is not on the list."
        )
    names = list(table_allowlist)  # type: ignore[call-overload]
    if not all(isinstance(name, str) and name.strip() for name in names):
        raise ValueError(f"table_allowlist entries must be non-empty table names ({example}).")
    return names


# Caps on how much query output is fed to the LLM when synthesizing an answer.
ANSWER_MAX_ROWS = 50
ANSWER_MAX_CELL_CHARS = 200

_SQL_SYSTEM_PROMPT = (
    "You are a PostgreSQL expert. Given a database schema and a question, write "
    "exactly one read-only SQL query that answers it.\n"
    "Rules:\n"
    "- Output a single SELECT statement; a leading WITH (CTE) is allowed.\n"
    "- Never write INSERT, UPDATE, DELETE, or any DDL.\n"
    "- Use only the tables and columns shown in the schema.\n"
    "- Do not schema-qualify table names; the correct schema is already active.\n"
    "- When the question cannot be answered from the schema, return a query that "
    "yields no rows and explain why in the reasoning."
)

_ANSWER_SYSTEM_PROMPT = (
    "You answer questions about a database using ONLY the provided SQL result. "
    "Be concise and factual. If the result has no rows, say that no matching "
    "data was found. Never invent data that is not in the result."
)

# Language code -> human-readable name for the answer-synthesis directive.
# Codes not listed here are passed through as-is in the directive.
_LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "fi": "Finnish",
    "sv": "Swedish",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "no": "Norwegian",
    "da": "Danish",
}


def _redact(text: str) -> str:
    """Mask credentials in text that may quote a connection string, for debug logs.

    Covers the user and password of a URI (also percent-encoded), ``password=`` and
    ``PGPASSWORD=`` in keyword form or as a URI query parameter, quoted or not.
    Error messages never carry the connection string; this is for debug logging only.
    """
    redacted = re.sub(r"(://)[^/?#\s]*@", r"\1***@", text)
    return re.sub(
        r"""((?:pg)?password\s*=\s*)('(?:[^'\\]|\\.)*'|"[^"]*"|\S+)""",
        r"\1***",
        redacted,
        flags=re.IGNORECASE,
    )


def _db_error(exc: BaseException) -> str:
    """A short, generic description of a database error: its kind and SQLSTATE.

    The driver's own text is left out: it can quote the connection settings, the
    query's literals or values from the table.
    """
    name = type(exc).__name__
    if name == "OperationalError":
        kind = "connection or server error"
    elif name in {"Error", "DatabaseError", "InterfaceError"}:
        kind = "database error"
    else:
        kind = re.sub(r"(?<!^)(?=[A-Z])", " ", name).lower()
    sqlstate = getattr(exc, "sqlstate", None)
    return f"{kind} (SQLSTATE {sqlstate})" if sqlstate else kind


# What a failed connection says, matched in the driver's text and reported in these
# words only, so a message never quotes the connection string. First match wins.
_CONNECT_REASONS = (
    ("invalid connection option", "invalid connection string"),
    ('missing "="', "invalid connection string"),
    ("invalid uri", "invalid connection string"),
    ("invalid integer value", "invalid connection string"),
    ("invalid dsn", "invalid connection string"),
    ("invalid connection string", "invalid connection string"),
    ("invalid sslmode", "invalid connection string"),
    ("password authentication failed", "authentication failed"),
    ("authentication failed", "authentication failed"),
    ("no password supplied", "no password given"),
    ("could not translate host name", "unknown host"),
    ("name or service not known", "unknown host"),
    ("nodename nor servname", "unknown host"),
    ("connection refused", "connection refused"),
    ("timeout expired", "connection timed out"),
    ("timed out", "connection timed out"),
    ("no pg_hba.conf entry", "this host or user may not connect"),
    ("does not exist", "the database or role does not exist"),
    ("ssl", "SSL negotiation failed"),
)


def _connect_reason(exc: BaseException) -> str:
    """Why a connection failed, in fixed words, with the SQLSTATE when there is one."""
    text = str(exc).lower()
    for marker, reason in _CONNECT_REASONS:
        if marker in text:
            sqlstate = getattr(exc, "sqlstate", None)
            return f"{reason} (SQLSTATE {sqlstate})" if sqlstate else reason
    return _db_error(exc)


def _with_retries(call: Any, *, tries: int = 4) -> Any:
    """Retry an LLM call on transient API errors with exponential backoff."""
    for attempt in range(tries):
        try:
            return call()
        except (RateLimitError, APITimeoutError, APIError):
            if attempt == tries - 1:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("_with_retries: loop terminated without return or raise")


def _unique_column_names(names: list[str]) -> list[str]:
    """Keep the first of each name and number its repeats: count, count_2, count_3.

    A number is never one that another result column already carries.
    """
    taken = set(names)
    used: set[str] = set()
    unique = []
    for name in names:
        candidate, n = name, 1
        while candidate in used:
            n += 1
            candidate = f"{name}_{n}"
            if candidate in taken:
                candidate = name  # that name belongs to a real column; try the next number
        used.add(candidate)
        unique.append(candidate)
    return unique


def _format_rows_for_prompt(rows: list[dict]) -> str:
    """Render query rows compactly, capping row count and cell length."""
    if not rows:
        return "(no rows)"
    lines: list[str] = []
    for row in rows[:ANSWER_MAX_ROWS]:
        cells = []
        for key, value in row.items():
            text = "NULL" if value is None else str(value)
            if len(text) > ANSWER_MAX_CELL_CHARS:
                text = text[:ANSWER_MAX_CELL_CHARS] + "…"
            cells.append(f"{key}={text}")
        lines.append(" | ".join(cells))
    if len(rows) > ANSWER_MAX_ROWS:
        lines.append(f"... ({len(rows) - ANSWER_MAX_ROWS} more row(s) not shown)")
    return "\n".join(lines)


class PostgresAgent:
    """Ask a PostgreSQL database questions in natural language.

    The high-level entry point is :meth:`ask`. Lower-level methods
    (:meth:`get_schema`, :meth:`run_sql`) need only a database connection and
    can be used as tools by an external agent framework, while :meth:`generate_sql`
    and :meth:`query` additionally need an LLM.

    Scope: read-only relational queries against a single schema. The agent
    never writes. Validation is best-effort -- connect with a read-only
    database role for a real guarantee.

    Example::

        from gaik.software_components.postgres_agent import PostgresAgent

        with PostgresAgent(
            "postgresql://user:pass@localhost:5432/db",
            table_allowlist=["customers", "orders"],
        ) as agent:
            result = agent.ask("Which customer placed the most orders?")
            print(result.answer)

    Args:
        connection_string: PostgreSQL connection URI.
        config: LLM config from ``get_llm_config()``. Resolved lazily on the
            first LLM call, so schema/SQL tools work without LLM credentials.
        model: Optional model override; defaults to the config's model.
        max_retries: Attempts the agentic loop makes when SQL fails.
        max_rows: Hard cap on rows returned by :meth:`run_sql`.
        statement_timeout_ms: Per-statement timeout (0 disables it).
        table_allowlist: Required. The tables and views the agent may read, as
            PostgreSQL stores their names (case-sensitive: ``"Users"`` is the
            table created as ``"Users"``). Only these appear in the schema the
            LLM sees, and a query that touches any other table, view or
            system catalog is refused before it runs. Type casts are checked
            against the list too: a cast to an ``oid`` or ``reg*`` type, or to
            a type that is neither built in nor a listed table, is refused, as
            are session and server details such as ``version()``. A listed
            table's rows include those of its partitions and of tables that
            inherit from it. A missing list raises
            ``TypeError`` and an empty one ``ValueError`` at construction;
            releases up to gaik 0.11.0 read every table in ``schema_name``
            when no list was given.
        schema_name: The single schema the agent operates on.
        extra_instructions: Optional free-form text appended to the SQL-generation
            user prompt under "Additional context:". Use this for a domain glossary,
            naming conventions, or example question→SQL pairs. The agent stays
            schema-agnostic; this is the hook to inject project-specific knowledge.
        answer_language: ISO 639-1 code (e.g. ``"en"``, ``"fi"``, ``"sv"``) for the
            synthesized natural-language answer. Defaults to ``"en"``.
        temperature: Sampling temperature sent with every LLM call. Defaults to
            ``0.0`` so the same question yields the same SQL, which is what a
            query agent wants. Pass ``None`` to omit the parameter entirely:
            reasoning deployments (OpenAI's o-series, gpt-5.x reasoning tiers)
            reject an explicit temperature with *"Unsupported value:
            'temperature' does not support 0 with this model"* and run at their
            own fixed setting. Without this, using one of those models meant
            catching that specific rejection downstream and retrying. GPT-6 and
            GPT-5.6 drop it automatically unless ``reasoning_effort="none"``.
    """

    def __init__(
        self,
        connection_string: str,
        *,
        config: dict | None = None,
        model: str | None = None,
        max_retries: int = 3,
        max_rows: int = 100,
        statement_timeout_ms: int = 10_000,
        table_allowlist: list[str],
        schema_name: str = "public",
        extra_instructions: str | None = None,
        answer_language: str = "en",
        temperature: float | None = 0.0,
    ) -> None:
        if not connection_string or not connection_string.strip():
            raise ValueError("connection_string must be a non-empty PostgreSQL URI.")
        if not _IDENTIFIER_RE.fullmatch(schema_name):
            raise ValueError(
                f"Invalid schema_name '{schema_name}': "
                "must contain only letters, digits, and underscores."
            )
        if schema_name.lower() in _SYSTEM_SCHEMAS or schema_name.lower().startswith("pg_"):
            raise ValueError(
                f"schema_name '{schema_name}' is a PostgreSQL system schema; "
                "the agent reads only tables in an application schema."
            )
        self.connection_string = connection_string
        # An unquoted identifier, as in search_path and the validator: fold it once
        # so introspection looks for the schema PostgreSQL actually created.
        self.schema_name = schema_name.lower()
        self.max_retries = max(1, max_retries)
        self.max_rows = max(1, max_rows)
        self.statement_timeout_ms = max(0, statement_timeout_ms)
        self.table_allowlist = _check_table_allowlist(table_allowlist)
        self.extra_instructions = extra_instructions.strip() if extra_instructions else None
        self.answer_language = (answer_language or "en").strip().lower()
        self.temperature = temperature

        self._config = config
        self._model = model
        self._llm_client: Any = None
        self._conn: psycopg.Connection | None = None
        self._schema: SchemaInfo | None = None
        self._schema_has_samples = False

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def _get_conn(self) -> psycopg.Connection:
        """Return (and lazily open) a read-only database connection."""
        if self._conn is None or self._conn.closed:
            options = (
                "-c default_transaction_read_only=on "
                f"-c statement_timeout={self.statement_timeout_ms} "
                f"-c search_path={self.schema_name}"
            )
            try:
                self._conn = psycopg.connect(
                    self.connection_string,
                    row_factory=dict_row,
                    autocommit=True,
                    options=options,
                )
            except psycopg.Error as exc:
                # The driver's text can quote parts of the connection string: it goes
                # to the debug log only, with credentials and quoted parts masked.
                logger.debug(
                    "PostgreSQL connection failed: %s",
                    re.sub(r'"[^"]*"', '"***"', _redact(str(exc))),
                )
                error = type(exc)(
                    "Could not connect to the PostgreSQL database: "
                    f"{_connect_reason(exc)}. Check the connection string and that the "
                    "server is reachable."
                )
                error.sqlstate = exc.sqlstate
                error._gaik_safe_message = True  # query() may pass this text on as is
                raise error from None
            # Transactions opened on this connection start as BEGIN READ ONLY,
            # whatever the session default is by then.
            self._conn.read_only = True
        return self._conn

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None and not self._conn.closed:
            self._conn.close()
        self._conn = None

    def __enter__(self) -> PostgresAgent:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _get_llm_client(self) -> Any:
        """Return (and lazily build) the LLM client."""
        if self._llm_client is None:
            config = self._config or get_llm_config()
            self._config = config
            if self._model is None:
                self._model = config.get("model")
            self._llm_client = build_compat_client(config)
        return self._llm_client

    def _temperature_kwargs(self) -> dict[str, float]:
        """``{"temperature": x}``, or nothing at all when it is ``None``.

        Splatted into every LLM call so a reasoning deployment can be used
        without the caller catching *"Unsupported value: 'temperature'"* and
        retrying. Note that the structured-output path via
        :class:`ProviderClient` never sent a temperature to begin with, so SQL
        generation already worked on those models; it was answer synthesis that
        failed.
        """
        return {} if self.temperature is None else {"temperature": self.temperature}

    def _openai_kwargs(self) -> dict[str, Any]:
        """Temperature for the raw OpenAI/Azure client, adapted to the model family.

        GPT-6 and GPT-5.6 accept a temperature only with ``reasoning_effort="none"``,
        so the default ``0.0`` is dropped for them rather than rejected with a 400.
        """
        return normalize_chat_kwargs(self._model, self._temperature_kwargs(), config=self._config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_schema(self, *, refresh: bool = False, include_samples: bool = False) -> SchemaInfo:
        """Introspect and cache the database schema.

        Args:
            refresh: Re-introspect even if a cached schema exists.
            include_samples: Attach up to three sample rows per table to the
                returned schema. They are for the caller: :meth:`generate_sql`
                leaves them out of its prompt, so sample values never reach the LLM.

        Returns:
            A :class:`~gaik.software_components.postgres_agent.models.SchemaInfo`.
        """
        need_refresh = (
            refresh or self._schema is None or (include_samples and not self._schema_has_samples)
        )
        if need_refresh:
            conn = self._get_conn()
            self._schema = introspect_schema(
                conn,
                schema_name=self.schema_name,
                allowlist=self.table_allowlist,
                include_samples=include_samples,
            )
            self._schema_has_samples = include_samples
        return self._schema

    def generate_sql(
        self, question: str, *, error_context: str | None = None, advice: str | None = None
    ) -> GeneratedSQL:
        """Generate a read-only SQL query for ``question`` (no execution).

        Args:
            question: The natural-language question.
            error_context: Feedback from a previous failed attempt, fed back to
                the LLM so it can correct the query. It can quote the data, so it
                goes in a data block.
            advice: The caller's own guidance for the retry, such as how to make a
                timed-out query cheaper. It is an instruction, so it stays outside
                the data blocks.

        Returns:
            A :class:`~gaik.software_components.postgres_agent.models.GeneratedSQL`.
        """
        client = self._get_llm_client()
        # Sample rows cached by get_schema(include_samples=True) stay out of the prompt.
        schema = self.get_schema()
        schema = schema.model_copy(
            update={"tables": [t.model_copy(update={"sample_rows": []}) for t in schema.tables]}
        )
        # Table and column names come from the database, and a database error can quote its
        # data: each goes in a data block. The question and the caller's extra
        # instructions stay outside the blocks.
        material = SourceMaterial()
        user_prompt = (
            f"Database schema (active schema: {self.schema_name}):\n"
            + material.wrap(schema.to_prompt_text(), label="database schema")
            + f"\n\nQuestion: {question}"
        )
        if self.extra_instructions:
            user_prompt += f"\n\nAdditional context:\n{self.extra_instructions}"
        if error_context:
            user_prompt += "\n\nThe previous attempt failed -- fix it.\n" + material.wrap(
                error_context, label="previous attempt"
            )
        if advice:
            user_prompt += f"\n\n{advice}"
        messages = source_material_messages(_SQL_SYSTEM_PROMPT, user_prompt)

        if isinstance(client, ProviderClient):
            parsed = _with_retries(
                lambda: client.chat_parsed(
                    messages=messages,
                    response_format=GeneratedSQL,
                    model=self._model,
                )
            )
        else:
            response = _with_retries(
                lambda: client.beta.chat.completions.parse(
                    model=self._model,
                    messages=messages,
                    response_format=GeneratedSQL,
                    **self._openai_kwargs(),
                    timeout=30,
                )
            )
            parsed = response.choices[0].message.parsed if response else None

        if not isinstance(parsed, GeneratedSQL):
            raise RuntimeError("LLM did not return a SQL query.")
        return parsed

    def run_sql(self, sql: str) -> list[dict]:
        """Validate ``sql`` as read-only and execute it.

        The query is wrapped so at most ``max_rows`` rows are returned. It runs
        in its own transaction, started ``READ ONLY`` and always rolled back,
        so PostgreSQL rejects any write and no session setting changed by a
        query outlives it.

        Args:
            sql: A single read-only SQL query.

        Returns:
            The result rows as a list of dicts.

        Raises:
            UnsafeSQLError: If ``sql`` is not a single read-only query.
            psycopg.Error: If PostgreSQL rejects or fails the query.
        """
        validated = validate_read_only(
            sql, schema_name=self.schema_name, allowlist=self.table_allowlist
        )
        wrapped = f"SELECT * FROM (\n{validated}\n) AS gaik_query LIMIT {self.max_rows}"
        conn = self._get_conn()
        with conn.transaction(force_rollback=True):
            cursor = conn.execute(wrapped)
            # Tuples, not dict_row: two result columns with one name (count, count)
            # would otherwise collapse into one key and lose a value.
            cursor.row_factory = tuple_row
            rows = cursor.fetchall()
            names = _unique_column_names([col.name for col in cursor.description or []])
        return [dict(zip(names, row)) for row in rows]

    def query(self, question: str) -> QueryResult:
        """Answer ``question`` with data: generate SQL, run it, retry on error.

        Args:
            question: The natural-language question.

        Returns:
            A :class:`~gaik.software_components.postgres_agent.models.QueryResult`
            with the SQL used, the rows, and the attempt count.
        """
        result = QueryResult(question=question)
        self.get_schema()
        error_context: str | None = None
        advice: str | None = None

        for attempt in range(1, self.max_retries + 1):
            result.attempts = attempt
            try:
                generated = self.generate_sql(question, error_context=error_context, advice=advice)
                advice = None
                result.sql = generated.sql
                result.reasoning = generated.reasoning
                rows = self.run_sql(generated.sql)
            except UnsafeSQLError as exc:
                result.error = str(exc)
                error_context = f"The generated query was rejected as unsafe: {exc}"
                continue
            except psycopg.errors.QueryCanceled as exc:
                # statement_timeout fired. Retrying the same logical query at
                # the same scale will time out again, so give the LLM exactly
                # one targeted shot at rewriting for performance, then bail.
                # This keeps wall time bounded for the caller.
                logger.debug("PostgreSQL canceled the query: %s", _redact(str(exc)))
                if "statement timeout" in str(exc).lower():
                    result.error = (
                        "The query ran past the statement timeout of "
                        f"{self.statement_timeout_ms} ms and was canceled."
                    )
                else:
                    result.error = "The query was canceled (SQLSTATE 57014)."
                if attempt == 1:
                    error_context = (
                        f"PostgreSQL canceled the query after "
                        f"{self.statement_timeout_ms} ms (statement_timeout). "
                        f"Failed SQL:\n{result.sql}"
                    )
                    advice = (
                        "Rewrite the query to do less work: prefer EXISTS over "
                        "correlated subqueries, narrow the date range, drop "
                        "unused JOINs, push filters into derived tables, or "
                        "remove ORDER BY on un-indexed columns. Do NOT resubmit "
                        "the same query."
                    )
                    continue
                logger.warning(
                    "PostgresAgent.query bailed on QueryCanceled after attempt %d",
                    attempt,
                )
                return result
            except psycopg.Error as exc:
                # Only the kind of error and its SQLSTATE reach the result and the
                # model: the driver's text can carry values from the database.
                logger.debug("PostgreSQL failed the query: %s", _redact(str(exc)))
                if getattr(exc, "_gaik_safe_message", False):
                    result.error = str(exc)
                elif isinstance(exc, psycopg.OperationalError):
                    result.error = f"The database could not run the query: {_db_error(exc)}."
                else:
                    result.error = f"PostgreSQL rejected the query: {_db_error(exc)}."
                error_context = f"{result.error}\nFailed SQL:\n{result.sql}"
                continue
            result.rows = rows
            result.row_count = len(rows)
            result.succeeded = True
            result.error = None
            return result

        logger.warning(
            "PostgresAgent.query failed after %d attempt(s): %s",
            result.attempts,
            result.error,
        )
        return result

    def ask(self, question: str) -> AnswerResult:
        """Answer ``question`` in natural language, backed by a SQL query.

        Args:
            question: The natural-language question.

        Returns:
            An :class:`~gaik.software_components.postgres_agent.models.AnswerResult`.
        """
        query_result = self.query(question)
        if not query_result.succeeded:
            answer = (
                f"I could not answer this question. The query failed after "
                f"{query_result.attempts} attempt(s): {query_result.error}"
            )
        else:
            answer = self._synthesize_answer(question, query_result)
        return AnswerResult(question=question, answer=answer, query_result=query_result)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _synthesize_answer(self, question: str, query_result: QueryResult) -> str:
        """Turn query rows into a concise natural-language answer."""
        client = self._get_llm_client()
        system_prompt = _ANSWER_SYSTEM_PROMPT
        if self.answer_language != "en":
            language = _LANGUAGE_NAMES.get(self.answer_language, self.answer_language)
            system_prompt += f" Reply in {language}."
        # The rows are the database's content: a value cannot add to the rules for the answer.
        material = SourceMaterial()
        user_prompt = (
            f"Question: {question}\n\n"
            "SQL query used:\n"
            + material.wrap(query_result.sql or "", label="SQL query used")
            + f"\n\nQuery result ({query_result.row_count} row(s)):\n"
            + material.wrap(_format_rows_for_prompt(query_result.rows), label="query result")
        )
        messages = source_material_messages(system_prompt, user_prompt)

        if isinstance(client, ProviderClient):
            response = _with_retries(
                lambda: client.chat(
                    messages=messages, model=self._model, **self._temperature_kwargs()
                )
            )
            return (response.text or "").strip() if response else ""

        response = _with_retries(
            lambda: client.chat.completions.create(
                model=self._model, messages=messages, **self._openai_kwargs()
            )
        )
        if not response or not response.choices:
            return ""
        return (response.choices[0].message.content or "").strip()
