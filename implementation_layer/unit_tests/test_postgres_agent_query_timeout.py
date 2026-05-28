"""Unit tests for PostgresAgent.query timeout handling.

When PostgreSQL fires ``statement_timeout`` (psycopg.errors.QueryCanceled),
retrying the same logical query at the same scale will time out again. The
agent should give the LLM exactly one shot at rewriting for performance and
then bail, instead of burning the full ``max_retries`` budget.
"""

from __future__ import annotations

from typing import Any, Iterator
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

pytest.importorskip("psycopg")
pytest.importorskip("sqlglot")

import psycopg  # noqa: E402

from gaik.software_components.llm.base import (  # noqa: E402
    ChatMessage,
    ChatResponse,
    ProviderClient,
)
from gaik.software_components.postgres_agent.agent import (  # noqa: E402
    PostgresAgent,
)
from gaik.software_components.postgres_agent.models import (  # noqa: E402
    GeneratedSQL,
    SchemaInfo,
    TableInfo,
)


class FakeProviderClient:
    """Explicit ProviderClient implementation for stubbing.

    A plain MagicMock no longer satisfies ``isinstance(_, ProviderClient)``
    on Python 3.12+ (runtime_checkable Protocols now inspect class
    attributes, not just method names), so tests need a concrete
    implementation.
    """

    provider: str = "stub"
    model: str = "stub-model"
    raw: Any = None

    def __init__(self, chat_parsed_impl=None, chat_impl=None) -> None:
        self._chat_parsed = chat_parsed_impl or (
            lambda **_: GeneratedSQL(sql="SELECT 1", reasoning="stub")
        )
        self._chat = chat_impl or (
            lambda **_: ChatResponse(text="stub", model=self.model, provider=self.provider)
        )

    def chat(self, messages: list[ChatMessage], **kwargs: Any) -> ChatResponse:
        return self._chat(messages=messages, **kwargs)

    def chat_parsed(
        self,
        messages: list[ChatMessage],
        response_format: type[BaseModel],
        **kwargs: Any,
    ) -> BaseModel:
        return self._chat_parsed(messages=messages, response_format=response_format, **kwargs)

    def chat_stream(
        self, messages: list[ChatMessage], **kwargs: Any
    ) -> Iterator[str]:
        yield "stub"

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        return [[0.0] for _ in texts]


def _make_agent(**kwargs) -> PostgresAgent:
    agent = PostgresAgent("postgresql://stub:stub@localhost:1/stub", **kwargs)
    agent._schema = SchemaInfo(
        schema_name=agent.schema_name,
        tables=[TableInfo(name="orders", columns=[])],
    )
    return agent


def _stub_llm_returns_sql(agent: PostgresAgent, sql: str, captured: dict) -> None:
    """Make generate_sql return ``sql`` every call, recording each prompt."""

    def fake(**kwargs):
        captured.setdefault("calls", []).append(kwargs["messages"])
        return GeneratedSQL(sql=sql, reasoning="stub")

    client = FakeProviderClient(chat_parsed_impl=fake)
    assert isinstance(client, ProviderClient)  # sanity
    agent._llm_client = client
    agent._model = "stub-model"


def _stub_conn_raises_query_canceled(agent: PostgresAgent) -> MagicMock:
    """Make every conn.execute() raise psycopg.errors.QueryCanceled.

    Note: ``MagicMock().closed`` is a truthy mock object — without an
    explicit ``False`` here, ``PostgresAgent._get_conn`` would treat the
    stub as closed and try to open a real psycopg connection.
    """
    conn = MagicMock()
    conn.closed = False
    conn.execute.side_effect = psycopg.errors.QueryCanceled(
        "canceling statement due to statement timeout"
    )
    agent._conn = conn
    return conn


def test_query_timeout_bails_after_one_retry():
    """A persistent timeout should consume exactly 2 attempts, not max_retries."""
    captured: dict = {}
    agent = _make_agent(max_retries=3, statement_timeout_ms=10_000)
    _stub_llm_returns_sql(agent, "SELECT * FROM orders", captured)
    _stub_conn_raises_query_canceled(agent)

    result = agent.query("How many orders?")

    assert not result.succeeded
    assert result.attempts == 2, (
        f"Expected to bail after attempt 2 (one retry with hint), "
        f"got attempts={result.attempts}"
    )
    assert "statement timeout" in (result.error or "").lower()


def test_query_timeout_retry_carries_rewrite_hint():
    """The retry must include a clear 'rewrite to do less work' instruction."""
    captured: dict = {}
    agent = _make_agent(max_retries=3, statement_timeout_ms=5_000)
    _stub_llm_returns_sql(agent, "SELECT * FROM orders", captured)
    _stub_conn_raises_query_canceled(agent)

    agent.query("Q")

    # Two LLM calls total: initial generation + one retry with hint.
    assert len(captured["calls"]) == 2
    retry_prompt = captured["calls"][1][1]["content"]
    assert "statement_timeout" in retry_prompt.lower()
    assert "5000" in retry_prompt  # the timeout value in ms
    assert "rewrite" in retry_prompt.lower()
    # The retry prompt must NOT just look like a generic "rejected" message —
    # it should call out the specific levers the LLM can pull.
    assert "exists" in retry_prompt.lower() or "narrow" in retry_prompt.lower()


def test_non_timeout_psycopg_error_still_retries_full_budget():
    """Regression: other psycopg errors keep the original 3-attempt loop."""
    captured: dict = {}
    agent = _make_agent(max_retries=3)
    _stub_llm_returns_sql(agent, "SELECT * FROM orders", captured)

    conn = MagicMock()
    conn.closed = False
    conn.execute.side_effect = psycopg.Error("syntax error at end of input")
    agent._conn = conn

    result = agent.query("Q")

    assert not result.succeeded
    assert result.attempts == 3
    assert "syntax error" in (result.error or "").lower()


def test_query_succeeds_after_timeout_rewrite():
    """If the LLM's rewrite executes successfully, the result is returned."""
    captured: dict = {}
    agent = _make_agent(max_retries=3, statement_timeout_ms=10_000)

    sql_to_return = ["SELECT * FROM orders WHERE 1=1", "SELECT id FROM orders LIMIT 1"]

    def fake(**kwargs):
        captured.setdefault("calls", []).append(kwargs["messages"])
        sql = sql_to_return.pop(0)
        return GeneratedSQL(sql=sql, reasoning="stub")

    client = FakeProviderClient(chat_parsed_impl=fake)
    agent._llm_client = client
    agent._model = "stub-model"

    cursor = MagicMock()
    cursor.fetchall.return_value = [{"id": 1}]
    conn = MagicMock()
    conn.closed = False
    conn.execute.side_effect = [
        psycopg.errors.QueryCanceled("canceling statement due to statement timeout"),
        cursor,
    ]
    agent._conn = conn

    result = agent.query("Q")

    assert result.succeeded
    assert result.attempts == 2
    assert result.row_count == 1
    assert result.sql == "SELECT id FROM orders LIMIT 1"
