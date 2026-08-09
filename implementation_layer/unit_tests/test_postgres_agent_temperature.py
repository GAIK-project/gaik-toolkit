"""Unit tests for the postgres_agent ``temperature`` parameter.

The agent used to hardcode ``temperature=0`` on every LLM call. That is the
right default for a query agent — the same question should produce the same
SQL — but reasoning deployments (OpenAI's o-series, the gpt-5.x reasoning
tiers) reject an explicit temperature outright:

    Unsupported value: 'temperature' does not support 0 with this model.

so they could not be used at all without catching that one error downstream and
retrying the call without the parameter. ``temperature=None`` now omits it.

No database and no real provider: the LLM client is the shared
``FakeProviderClient`` so the agent's ``isinstance(_, ProviderClient)`` branch
is the one under test (see ``_pg_agent_fake_client.py`` for why a MagicMock is
not enough).
"""

from __future__ import annotations

import pytest

pytest.importorskip("psycopg")
pytest.importorskip("sqlglot")

from gaik.software_components.llm.base import ChatResponse  # noqa: E402
from gaik.software_components.postgres_agent.agent import PostgresAgent  # noqa: E402
from gaik.software_components.postgres_agent.models import (  # noqa: E402
    QueryResult,
    SchemaInfo,
    TableInfo,
)

from ._pg_agent_fake_client import FakeProviderClient  # noqa: E402


def _make_agent(**kwargs) -> PostgresAgent:
    agent = PostgresAgent("postgresql://stub:stub@localhost:1/stub", **kwargs)
    agent._schema = SchemaInfo(
        schema_name=agent.schema_name,
        tables=[TableInfo(name="customers", columns=[])],
    )
    return agent


def _capture_synthesis_kwargs(agent: PostgresAgent, captured: dict) -> None:
    """Route ``_synthesize_answer`` through a client that records its kwargs."""

    def chat_impl(**kwargs):
        captured.update(kwargs)
        return ChatResponse(text="an answer", model="stub-model", provider="stub")

    agent._llm_client = FakeProviderClient(chat_impl=chat_impl)


def _result() -> QueryResult:
    return QueryResult(
        question="how many?",
        sql="SELECT 1",
        rows=[{"n": 1}],
        row_count=1,
        attempts=1,
        succeeded=True,
    )


def test_default_sends_temperature_zero():
    """The default has to stay 0.0: reproducible SQL is the whole point."""
    agent = _make_agent()
    captured: dict = {}
    _capture_synthesis_kwargs(agent, captured)

    agent._synthesize_answer("how many?", _result())

    assert captured["temperature"] == 0.0


def test_none_omits_the_parameter_entirely():
    """Not 'temperature=None' — the key must be absent, or the API still 400s."""
    agent = _make_agent(temperature=None)
    captured: dict = {}
    _capture_synthesis_kwargs(agent, captured)

    agent._synthesize_answer("how many?", _result())

    assert "temperature" not in captured


def test_an_explicit_value_is_passed_through():
    agent = _make_agent(temperature=0.7)
    captured: dict = {}
    _capture_synthesis_kwargs(agent, captured)

    agent._synthesize_answer("how many?", _result())

    assert captured["temperature"] == 0.7


@pytest.mark.parametrize("temperature", [0.0, None, 0.7])
def test_answer_is_returned_whatever_the_setting(temperature):
    """The parameter must not change the contract, only the request."""
    agent = _make_agent(temperature=temperature)
    _capture_synthesis_kwargs(agent, {})

    assert agent._synthesize_answer("how many?", _result()) == "an answer"


def test_structured_output_path_never_sent_a_temperature():
    """Documents why SQL generation already worked on reasoning models.

    ``chat_parsed`` is called without one, so only answer synthesis ever hit the
    rejection. If a future change starts sending it here, that regression should
    be a deliberate decision rather than a surprise in production.
    """
    agent = _make_agent()
    captured: dict = {}

    def chat_parsed_impl(**kwargs):
        captured.update(kwargs)
        from gaik.software_components.postgres_agent.models import GeneratedSQL

        return GeneratedSQL(sql="SELECT 1", reasoning="stub")

    agent._llm_client = FakeProviderClient(chat_parsed_impl=chat_parsed_impl)
    agent.generate_sql("how many customers?")

    assert "temperature" not in captured
