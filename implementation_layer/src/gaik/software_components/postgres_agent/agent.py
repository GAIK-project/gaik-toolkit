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
    from psycopg.rows import dict_row
except ImportError as exc:
    raise ImportError(
        "PostgresAgent requires 'psycopg[binary]'. "
        "Install extras with 'pip install gaik[postgres-agent]'"
    ) from exc

from gaik.software_components.llm.base import ProviderClient
from gaik.software_components.llm.config import get_llm_config
from gaik.software_components.llm.factory import build_compat_client

from .introspection import introspect_schema
from .models import AnswerResult, GeneratedSQL, QueryResult, SchemaInfo
from .sql_safety import UnsafeSQLError, validate_read_only

logger = logging.getLogger(__name__)

_IDENTIFIER_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")

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


def _redact(connection_string: str) -> str:
    """Mask the password in a connection string for safe logging."""
    redacted = re.sub(r"(://[^:/?#@]+:)[^@/?#]+@", r"\1***@", connection_string)
    return re.sub(r"(password=)[^\s]+", r"\1***", redacted)


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

        with PostgresAgent("postgresql://user:pass@localhost:5432/db") as agent:
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
        table_allowlist: When given, queries may only touch these tables.
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
            catching that specific rejection downstream and retrying.
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
        table_allowlist: list[str] | None = None,
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
        self.connection_string = connection_string
        self.schema_name = schema_name
        self.max_retries = max(1, max_retries)
        self.max_rows = max(1, max_rows)
        self.statement_timeout_ms = max(0, statement_timeout_ms)
        self.table_allowlist = list(table_allowlist) if table_allowlist else None
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
            except psycopg.OperationalError as exc:
                raise psycopg.OperationalError(
                    f"Could not connect to {_redact(self.connection_string)}: {exc}"
                ) from None
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_schema(self, *, refresh: bool = False, include_samples: bool = False) -> SchemaInfo:
        """Introspect and cache the database schema.

        Args:
            refresh: Re-introspect even if a cached schema exists.
            include_samples: Attach up to three sample rows per table. Sample
                values are sent to the LLM, so this defaults to off.

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

    def generate_sql(self, question: str, *, error_context: str | None = None) -> GeneratedSQL:
        """Generate a read-only SQL query for ``question`` (no execution).

        Args:
            question: The natural-language question.
            error_context: Feedback from a previous failed attempt, fed back to
                the LLM so it can correct the query.

        Returns:
            A :class:`~gaik.software_components.postgres_agent.models.GeneratedSQL`.
        """
        client = self._get_llm_client()
        schema = self.get_schema()
        user_prompt = (
            f"Database schema (active schema: {self.schema_name}):\n"
            f"{schema.to_prompt_text()}\n\n"
            f"Question: {question}"
        )
        if self.extra_instructions:
            user_prompt += f"\n\nAdditional context:\n{self.extra_instructions}"
        if error_context:
            user_prompt += f"\n\nThe previous attempt failed -- fix it.\n{error_context}"
        messages = [
            {"role": "system", "content": _SQL_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

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
                    **self._temperature_kwargs(),
                    timeout=30,
                )
            )
            parsed = response.choices[0].message.parsed if response else None

        if not isinstance(parsed, GeneratedSQL):
            raise RuntimeError("LLM did not return a SQL query.")
        return parsed

    def run_sql(self, sql: str) -> list[dict]:
        """Validate ``sql`` as read-only and execute it.

        The query is wrapped so at most ``max_rows`` rows are returned. The
        connection is read-only, so any write is rejected by PostgreSQL.

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
        rows = conn.execute(wrapped).fetchall()
        return [dict(row) for row in rows]

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

        for attempt in range(1, self.max_retries + 1):
            result.attempts = attempt
            try:
                generated = self.generate_sql(question, error_context=error_context)
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
                msg = str(exc).strip()
                result.error = msg
                if attempt == 1:
                    error_context = (
                        f"PostgreSQL canceled the query after "
                        f"{self.statement_timeout_ms} ms (statement_timeout). "
                        f"Failed SQL:\n{result.sql}\n\n"
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
                result.error = str(exc).strip()
                error_context = (
                    f"PostgreSQL rejected the query: {str(exc).strip()}\nFailed SQL:\n{result.sql}"
                )
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
        user_prompt = (
            f"Question: {question}\n\n"
            f"SQL query used:\n{query_result.sql}\n\n"
            f"Query result ({query_result.row_count} row(s)):\n"
            f"{_format_rows_for_prompt(query_result.rows)}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        if isinstance(client, ProviderClient):
            response = _with_retries(
                lambda: client.chat(
                    messages=messages, model=self._model, **self._temperature_kwargs()
                )
            )
            return (response.text or "").strip() if response else ""

        response = _with_retries(
            lambda: client.chat.completions.create(
                model=self._model, messages=messages, **self._temperature_kwargs()
            )
        )
        if not response or not response.choices:
            return ""
        return (response.choices[0].message.content or "").strip()
