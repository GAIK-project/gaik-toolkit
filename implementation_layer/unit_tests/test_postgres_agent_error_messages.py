"""PostgresAgent errors carry no connection details and no database error text.

A failed connection raises with a generic message, whatever form the connection string
takes. A failed query reaches the result, the answer and the model's retry prompt as
the kind of error and its SQLSTATE only.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

pytest.importorskip("psycopg")
pytest.importorskip("sqlglot")

import psycopg  # noqa: E402
from gaik.software_components.postgres_agent import agent as agent_module  # noqa: E402
from gaik.software_components.postgres_agent.agent import PostgresAgent  # noqa: E402
from gaik.software_components.postgres_agent.models import (  # noqa: E402
    GeneratedSQL,
    SchemaInfo,
    TableInfo,
)

from ._pg_agent_fake_client import FakeProviderClient  # noqa: E402

DSNS = [
    "postgresql://admin:s3cr3t-pw@db.internal:5432/sales",
    "postgresql://admin:s3cr3t%2Dpw@db.internal/sales",
    "postgresql://db.internal/sales?user=admin&password=s3cr3t-pw",
    "host=db.internal user=admin password=s3cr3t-pw dbname=sales",
    "host=db.internal user=admin password='s3cr3t-pw x' dbname=sales",
]


@pytest.mark.parametrize("dsn", DSNS)
@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (
            psycopg.OperationalError(
                'connection to server at "db.internal" (10.0.0.5), port 5432 failed: FATAL:  '
                'password authentication failed for user "admin"'
            ),
            "authentication failed",
        ),
        (
            psycopg.ProgrammingError('missing "=" after "s3cr3t-pw" in connection info string'),
            "invalid connection string",
        ),
        (
            psycopg.OperationalError(
                'could not translate host name "db.internal" to address: unknown'
            ),
            "unknown host",
        ),
        (psycopg.OperationalError("something new about admin"), "connection or server error"),
    ],
    ids=["password", "invalid", "host", "other"],
)
def test_a_failed_connection_names_no_connection_detail(monkeypatch, caplog, dsn, error, reason):
    def fail(*_a, **_k):
        raise error

    monkeypatch.setattr(agent_module.psycopg, "connect", fail)
    agent = PostgresAgent(dsn, table_allowlist=["customers", "orders"])

    with caplog.at_level(logging.DEBUG, logger=agent_module.__name__):
        with pytest.raises(type(error)) as caught:
            agent._get_conn()

    message = str(caught.value)
    assert message.startswith(f"Could not connect to the PostgreSQL database: {reason}.")
    for detail in ("s3cr3t", "admin", "db.internal", "10.0.0.5", "sales"):
        assert detail not in message
    assert caught.value.__cause__ is None and caught.value.__suppress_context__
    assert "s3cr3t" not in caplog.text


@pytest.mark.parametrize(
    "dsn",
    [*DSNS, "PGPASSWORD=s3cr3t-pw host=db.internal", "host=h password=s3cr3t&pw user=u"],
)
def test_redact_masks_every_password_form(dsn):
    assert "s3cr3t" not in agent_module._redact(f"failed for {dsn} at startup")


def _agent_with_failing_query(error: Exception, prompts: list) -> PostgresAgent:
    agent = PostgresAgent(
        "postgresql://stub:stub@localhost:1/stub", max_retries=2, table_allowlist=["t"]
    )
    agent._schema = SchemaInfo(schema_name="public", tables=[TableInfo(name="t", columns=[])])

    def generate(**kwargs):
        prompts.append(kwargs["messages"][-1]["content"])
        return GeneratedSQL(sql="SELECT CAST(name AS int) FROM t", reasoning="stub")

    agent._llm_client = FakeProviderClient(chat_parsed_impl=generate)
    agent._model = "stub-model"
    conn = MagicMock()
    conn.closed = False
    conn.execute.side_effect = error
    agent._conn = conn
    return agent


def test_a_rejected_query_reaches_result_answer_and_model_without_database_text():
    prompts: list = []
    error = psycopg.errors.InvalidTextRepresentation(
        'invalid input syntax for type integer: "Jane Doe, 555-0100"'
    )
    agent = _agent_with_failing_query(error, prompts)

    answer = agent.ask("Q")

    expected = "PostgreSQL rejected the query: invalid text representation (SQLSTATE 22P02)."
    assert answer.query_result.error == expected
    assert expected in answer.answer
    assert expected in prompts[1] and "SELECT CAST(name AS int) FROM t" in prompts[1]
    for text in (answer.query_result.error, answer.answer, *prompts):
        # The whole number: a prompt's random source_material id can hold "555".
        assert "Jane" not in text and "555-0100" not in text


def test_a_canceled_query_reports_the_timeout_without_database_text():
    prompts: list = []
    error = psycopg.errors.QueryCanceled("canceling statement: detail with Jane Doe")
    agent = _agent_with_failing_query(error, prompts)

    result = agent.query("Q")

    assert result.error == "The query was canceled (SQLSTATE 57014)."
    assert len(prompts) == 2
    assert not any("Jane" in prompt for prompt in prompts)


def test_a_timed_out_query_names_the_statement_timeout():
    error = psycopg.errors.QueryCanceled("canceling statement due to statement timeout")
    agent = _agent_with_failing_query(error, [])

    result = agent.query("Q")

    assert result.error == "The query ran past the statement timeout of 10000 ms and was canceled."


def test_a_lost_connection_is_not_reported_as_a_rejected_query(monkeypatch):
    prompts: list = []
    agent = _agent_with_failing_query(
        psycopg.OperationalError("server closed the connection unexpectedly at db.internal"),
        prompts,
    )
    assert agent.query("Q").error == (
        "The database could not run the query: connection or server error."
    )

    def fail(*_a, **_k):
        raise psycopg.OperationalError('connection to server at "db.internal" refused')

    agent._conn.closed = True  # the next attempt reconnects, and that fails
    monkeypatch.setattr(agent_module.psycopg, "connect", fail)
    result = agent.query("Q")
    assert result.error.startswith(
        "Could not connect to the PostgreSQL database: connection or server error."
    )
    assert not any("db.internal" in prompt for prompt in prompts)
