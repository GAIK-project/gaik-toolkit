"""Tabular text-to-SQL query agent over CSV, Excel, Parquet and JSON files.

``TabularAgent`` loads spreadsheet-shaped files into an in-memory DuckDB
database, profiles every column, turns a natural-language question into a
validated read-only SQL query, runs it, and (optionally) synthesizes a
natural-language answer. A lightweight agentic loop feeds SQL errors back to
the LLM and retries.

Scope (v1): READ-ONLY analytical queries over files the caller supplies. The
agent never writes to the source files and never reaches outside the tables it
loaded -- generated SQL is validated, and the DuckDB connection is locked down
before any of it runs. See the component README.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from openai import APIError, APITimeoutError, RateLimitError

try:
    import duckdb
except ImportError as exc:
    raise ImportError(
        "TabularAgent requires 'duckdb'. Install extras with 'pip install gaik[tabular-agent]'"
    ) from exc

from gaik.software_components.llm.base import ProviderClient
from gaik.software_components.llm.config import get_llm_config
from gaik.software_components.llm.factory import build_compat_client

from .loader import load_sources, lock_down, normalize_sources
from .models import (
    AnswerResult,
    GeneratedSQL,
    QueryResult,
    SheetLayout,
    TabularSchema,
)
from .profiling import profile_tables
from .sql_safety import UnsafeSQLError, validate_read_only

logger = logging.getLogger(__name__)

# Caps on how much query output is fed to the LLM when synthesizing an answer.
ANSWER_MAX_ROWS = 50
ANSWER_MAX_CELL_CHARS = 200

_SQL_SYSTEM_PROMPT = (
    "You are a DuckDB SQL expert. Given a description of loaded tables and a "
    "question, write exactly one read-only SQL query that answers it.\n"
    "Rules:\n"
    "- Output a single SELECT statement; a leading WITH (CTE) is allowed.\n"
    "- Never write INSERT, UPDATE, DELETE, COPY, ATTACH, INSTALL, or any DDL.\n"
    "- Never read external files: no read_csv, read_parquet, read_json, or glob. "
    "All data is already loaded into the tables shown.\n"
    "- Use only the tables and columns shown in the schema.\n"
    "- Column statistics are given. Respect them: filter on values that actually "
    "occur, and remember which columns contain NULLs.\n"
    "- Text stored as numbers or dates has already been typed by the loader; "
    "cast explicitly when a comparison needs it.\n"
    "- When the question cannot be answered from the data, return a query that "
    "yields no rows and explain why in the reasoning."
)

_ANSWER_SYSTEM_PROMPT = (
    "You answer questions about a dataset using ONLY the provided SQL result. "
    "Be concise and factual. If the result has no rows, say that no matching "
    "data was found. Never invent data that is not in the result."
)

_LAYOUT_SYSTEM_PROMPT = (
    "You are given the top-left corner of a spreadsheet as a tab-separated grid, "
    "one line per row, each prefixed with its 0-based row index.\n"
    "Identify where the actual data table lives:\n"
    "- header_row: the row holding column headers.\n"
    "- data_start_row: the first row of real data.\n"
    "- data_end_row: the last row of real data, or null if the data runs to the "
    "end. Use this to exclude trailing totals, notes, or signature blocks.\n"
    "- skip_columns: 0-based indices of columns that are spacers or notes.\n"
    "Report titles, blank spacer rows, subtotal rows and footnotes are NOT data. "
    "All indices refer to the row numbers shown in the grid."
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


class TabularAgent:
    """Ask CSV, Excel, Parquet or JSON files questions in natural language.

    The high-level entry point is :meth:`ask`. Lower-level methods
    (:meth:`get_schema`, :meth:`run_sql`) need no LLM credentials and can be
    used as tools by an external agent framework, while :meth:`generate_sql`
    and :meth:`query` additionally need an LLM.

    Scope: read-only analytical queries over the loaded files. The agent never
    modifies the source files. Generated SQL is validated, and the DuckDB
    connection is locked so it cannot reach the filesystem or the network.

    Example::

        from gaik.software_components.tabular_agent import TabularAgent

        with TabularAgent("sales.xlsx") as agent:
            result = agent.ask("Which region grew most in Q3?")
            print(result.answer)
            print(result.query_result.sql)

    Args:
        source: A file path, a sequence of paths, or a ``{table_name: path}``
            mapping when you want to name the tables yourself. Excel workbooks
            contribute one table per non-empty sheet.
        config: LLM config from ``get_llm_config()``. Resolved lazily on the
            first LLM call, so loading and SQL execution work without LLM
            credentials.
        model: Optional model override; defaults to the config's model.
        max_retries: Attempts the agentic loop makes when SQL fails.
        max_rows: Hard cap on rows returned by :meth:`run_sql`.
        query_timeout_s: Wall-clock limit for a single query (0 disables it).
        memory_limit: DuckDB memory cap, e.g. ``"1GB"``.
        layout_inference: When the LLM may be asked to locate the real table
            inside a messy spreadsheet. ``"auto"`` (default) asks only when the
            deterministic heuristics flag a sheet as messy, so clean files cost
            no extra tokens; ``"always"`` asks for every sheet; ``"never"``
            relies on the heuristics alone.
        profile_samples: Example values shown per non-categorical column.
        extra_instructions: Optional free-form text appended to the
            SQL-generation user prompt under "Additional context:". Use this for
            a domain glossary, unit conventions, or example question→SQL pairs.
        answer_language: ISO 639-1 code (e.g. ``"en"``, ``"fi"``, ``"sv"``) for
            the synthesized natural-language answer. Defaults to ``"en"``.
        temperature: Sampling temperature sent with every LLM call. Defaults to
            ``0.0`` so the same question yields the same SQL. Pass ``None`` to
            omit the parameter entirely: reasoning deployments (OpenAI's
            o-series, gpt-5.x reasoning tiers) reject an explicit temperature
            and run at their own fixed setting.
    """

    def __init__(
        self,
        source: str | Path | Sequence[str | Path] | Mapping[str, str | Path],
        *,
        config: dict | None = None,
        model: str | None = None,
        max_retries: int = 3,
        max_rows: int = 100,
        query_timeout_s: float = 10.0,
        memory_limit: str = "1GB",
        layout_inference: Literal["auto", "always", "never"] = "auto",
        profile_samples: int = 3,
        extra_instructions: str | None = None,
        answer_language: str = "en",
        temperature: float | None = 0.0,
    ) -> None:
        if layout_inference not in ("auto", "always", "never"):
            raise ValueError(
                f"Invalid layout_inference '{layout_inference}': "
                "must be 'auto', 'always', or 'never'."
            )
        self.sources = normalize_sources(source)
        self.max_retries = max(1, max_retries)
        self.max_rows = max(1, max_rows)
        self.query_timeout_s = max(0.0, query_timeout_s)
        self.memory_limit = memory_limit
        self.layout_inference = layout_inference
        self.profile_samples = max(0, profile_samples)
        self.extra_instructions = extra_instructions.strip() if extra_instructions else None
        self.answer_language = (answer_language or "en").strip().lower()
        self.temperature = temperature

        self._config = config
        self._model = model
        self._llm_client: Any = None
        self._conn: Any = None
        self._tables: dict[str, str] = {}
        self._schema: TabularSchema | None = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def _get_conn(self) -> Any:
        """Return (and lazily build) the locked-down DuckDB connection.

        Loading happens exactly once. External access is enabled only for the
        duration of the load -- which reads nothing but the caller's own paths
        -- and is switched off irreversibly before any generated SQL can run.
        """
        if self._conn is None:
            conn = duckdb.connect(":memory:")
            try:
                conn.execute(f"SET memory_limit = '{self.memory_limit}'")
                self._tables = load_sources(
                    conn,
                    self.sources,
                    layout_inference=self.layout_inference,
                    infer_layout=self._infer_layout,
                )
                lock_down(conn)
            except Exception:
                conn.close()
                raise
            self._conn = conn
        return self._conn

    def close(self) -> None:
        """Close the DuckDB connection and drop the loaded tables."""
        if self._conn is not None:
            self._conn.close()
        self._conn = None
        self._schema = None

    def __enter__(self) -> TabularAgent:
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
        """``{"temperature": x}``, or nothing at all when it is ``None``."""
        return {} if self.temperature is None else {"temperature": self.temperature}

    def _parse_structured(self, messages: list[dict], schema: type) -> Any:
        """Run one structured-output LLM call, whichever client type is in use."""
        client = self._get_llm_client()
        if isinstance(client, ProviderClient):
            return _with_retries(
                lambda: client.chat_parsed(
                    messages=messages, response_format=schema, model=self._model
                )
            )
        response = _with_retries(
            lambda: client.beta.chat.completions.parse(
                model=self._model,
                messages=messages,
                response_format=schema,
                **self._temperature_kwargs(),
                timeout=30,
            )
        )
        return response.choices[0].message.parsed if response else None

    # ------------------------------------------------------------------
    # Loading hooks
    # ------------------------------------------------------------------

    def _infer_layout(self, sheet_label: str, grid: str) -> SheetLayout:
        """Ask the LLM where the real table sits inside a messy sheet."""
        messages = [
            {"role": "system", "content": _LAYOUT_SYSTEM_PROMPT},
            {"role": "user", "content": f"Sheet: {sheet_label}\n\n{grid}"},
        ]
        parsed = self._parse_structured(messages, SheetLayout)
        if not isinstance(parsed, SheetLayout):
            raise RuntimeError("LLM did not return a sheet layout.")
        return parsed

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_schema(self, *, refresh: bool = False) -> TabularSchema:
        """Load the files (once) and profile every resulting table.

        Args:
            refresh: Re-profile even if a cached schema exists.

        Returns:
            A :class:`~gaik.software_components.tabular_agent.models.TabularSchema`.
        """
        if self._schema is None or refresh:
            conn = self._get_conn()
            self._schema = profile_tables(conn, self._tables, sample_values=self.profile_samples)
        return self._schema

    @property
    def table_names(self) -> list[str]:
        """Names of the loaded tables (loads the files if needed)."""
        self._get_conn()
        return list(self._tables)

    def generate_sql(self, question: str, *, error_context: str | None = None) -> GeneratedSQL:
        """Generate a read-only SQL query for ``question`` (no execution).

        Args:
            question: The natural-language question.
            error_context: Feedback from a previous failed attempt, fed back to
                the LLM so it can correct the query.

        Returns:
            A :class:`~gaik.software_components.tabular_agent.models.GeneratedSQL`.
        """
        schema = self.get_schema()
        user_prompt = f"Loaded tables:\n{schema.to_prompt_text()}\n\nQuestion: {question}"
        if self.extra_instructions:
            user_prompt += f"\n\nAdditional context:\n{self.extra_instructions}"
        if error_context:
            user_prompt += f"\n\nThe previous attempt failed -- fix it.\n{error_context}"

        parsed = self._parse_structured(
            [
                {"role": "system", "content": _SQL_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            GeneratedSQL,
        )
        if not isinstance(parsed, GeneratedSQL):
            raise RuntimeError("LLM did not return a SQL query.")
        return parsed

    def run_sql(self, sql: str) -> list[dict]:
        """Validate ``sql`` as read-only and execute it.

        The query is wrapped so at most ``max_rows`` rows are returned, and is
        interrupted if it exceeds ``query_timeout_s``.

        Args:
            sql: A single read-only SQL query.

        Returns:
            The result rows as a list of dicts.

        Raises:
            UnsafeSQLError: If ``sql`` is not a single read-only query over the
                loaded tables.
            duckdb.Error: If DuckDB rejects or fails the query.
        """
        conn = self._get_conn()
        validated = validate_read_only(sql, allowed_tables=list(self._tables))
        wrapped = f"SELECT * FROM (\n{validated}\n) AS gaik_query LIMIT {self.max_rows}"

        timer: threading.Timer | None = None
        if self.query_timeout_s > 0:
            timer = threading.Timer(self.query_timeout_s, conn.interrupt)
            timer.daemon = True
            timer.start()
        try:
            cursor = conn.execute(wrapped)
            columns = [d[0] for d in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            if timer is not None:
                timer.cancel()

    def query(self, question: str) -> QueryResult:
        """Answer ``question`` with data: generate SQL, run it, retry on error.

        Args:
            question: The natural-language question.

        Returns:
            A :class:`~gaik.software_components.tabular_agent.models.QueryResult`
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
            except duckdb.InterruptException:
                # The timeout fired. Re-running the same logical query at the
                # same scale would time out again, so give the LLM exactly one
                # targeted shot at a cheaper rewrite, then bail. This keeps wall
                # time bounded for the caller.
                msg = f"Query exceeded the {self.query_timeout_s}s time limit."
                result.error = msg
                if attempt == 1:
                    error_context = (
                        f"{msg} Failed SQL:\n{result.sql}\n\n"
                        "Rewrite the query to do less work: drop unused JOINs, "
                        "narrow the filters, aggregate earlier, or remove ORDER BY "
                        "over the full table. Do NOT resubmit the same query."
                    )
                    continue
                logger.warning("TabularAgent.query bailed on timeout after attempt %d", attempt)
                return result
            except duckdb.Error as exc:
                result.error = str(exc).strip()
                error_context = (
                    f"DuckDB rejected the query: {str(exc).strip()}\nFailed SQL:\n{result.sql}"
                )
                continue
            result.rows = rows
            result.row_count = len(rows)
            result.succeeded = True
            result.error = None
            return result

        logger.warning(
            "TabularAgent.query failed after %d attempt(s): %s", result.attempts, result.error
        )
        return result

    def ask(self, question: str) -> AnswerResult:
        """Answer ``question`` in natural language, backed by a SQL query.

        Args:
            question: The natural-language question.

        Returns:
            An :class:`~gaik.software_components.tabular_agent.models.AnswerResult`.
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
