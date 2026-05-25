"""Unit tests for the postgres_agent extra_instructions / answer_language hooks.

These exercise the prompt-construction paths without touching a real database or
a real LLM provider. Both the database connection and the LLM client are
replaced with simple stubs that capture the prompts they receive.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("psycopg")
pytest.importorskip("sqlglot")

from gaik.software_components.llm.base import ChatResponse  # noqa: E402
from gaik.software_components.postgres_agent.agent import (  # noqa: E402
    PostgresAgent,
)
from gaik.software_components.postgres_agent.models import (  # noqa: E402
    GeneratedSQL,
    QueryResult,
    SchemaInfo,
    TableInfo,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent(**kwargs) -> PostgresAgent:
    """Build a PostgresAgent without opening a real DB connection."""
    agent = PostgresAgent("postgresql://stub:stub@localhost:1/stub", **kwargs)
    # Replace the schema cache so get_schema() does not hit psycopg.
    agent._schema = SchemaInfo(
        schema_name=agent.schema_name,
        tables=[
            TableInfo(name="customers", columns=[]),
            TableInfo(name="orders", columns=[]),
        ],
    )
    return agent


def _stub_llm_for_sql(agent: PostgresAgent, captured: dict) -> None:
    """Stub the ProviderClient.chat_parsed path so generate_sql records its prompt.

    MagicMock satisfies the ``@runtime_checkable`` ProviderClient protocol via
    duck typing, so the agent takes the ProviderClient branch — we stub
    ``chat_parsed`` (which returns the parsed BaseModel directly).
    """

    def fake_chat_parsed(**kwargs):
        captured["messages"] = kwargs["messages"]
        return GeneratedSQL(sql="SELECT 1", reasoning="stub")

    client = MagicMock()
    # Protocol attributes (silence Mock-auto-truthiness corner cases).
    client.provider = "stub"
    client.model = "stub-model"
    client.chat_parsed.side_effect = fake_chat_parsed
    agent._llm_client = client
    agent._model = "stub-model"


def _stub_llm_for_answer(agent: PostgresAgent, captured: dict) -> None:
    """Stub the ProviderClient.chat path so _synthesize_answer records its prompt."""

    def fake_chat(**kwargs):
        captured["messages"] = kwargs["messages"]
        return ChatResponse(text="stub answer", model="stub-model", provider="stub")

    client = MagicMock()
    client.provider = "stub"
    client.model = "stub-model"
    client.chat.side_effect = fake_chat
    agent._llm_client = client
    agent._model = "stub-model"


# ---------------------------------------------------------------------------
# extra_instructions
# ---------------------------------------------------------------------------


def test_extra_instructions_default_is_none():
    agent = _make_agent()
    assert agent.extra_instructions is None


def test_extra_instructions_strips_whitespace():
    agent = _make_agent(extra_instructions="  glossary text  \n")
    assert agent.extra_instructions == "glossary text"


def test_extra_instructions_appended_to_sql_prompt():
    captured: dict = {}
    agent = _make_agent(
        extra_instructions="Glossary: discount_percent is the customer discount in %."
    )
    _stub_llm_for_sql(agent, captured)

    agent.generate_sql("Which customers have a discount?")

    user_prompt = captured["messages"][1]["content"]
    assert "Additional context:" in user_prompt
    assert "discount_percent" in user_prompt
    # The default schema text still comes first.
    assert user_prompt.index("Database schema") < user_prompt.index("Additional context:")


def test_no_extra_instructions_no_additional_context_marker():
    captured: dict = {}
    agent = _make_agent()
    _stub_llm_for_sql(agent, captured)

    agent.generate_sql("Hello?")

    user_prompt = captured["messages"][1]["content"]
    assert "Additional context:" not in user_prompt


def test_extra_instructions_combined_with_error_context():
    captured: dict = {}
    agent = _make_agent(extra_instructions="Use snake_case column names.")
    _stub_llm_for_sql(agent, captured)

    agent.generate_sql("Q", error_context="syntax error near FOO")

    user_prompt = captured["messages"][1]["content"]
    # Extra context comes before retry feedback.
    assert "Additional context:" in user_prompt
    assert "syntax error near FOO" in user_prompt
    assert user_prompt.index("Additional context:") < user_prompt.index(
        "previous attempt failed"
    )


# ---------------------------------------------------------------------------
# answer_language
# ---------------------------------------------------------------------------


def test_answer_language_default_is_english():
    agent = _make_agent()
    assert agent.answer_language == "en"


def test_answer_language_normalized_lowercase():
    agent = _make_agent(answer_language="FI")
    assert agent.answer_language == "fi"


def test_english_default_does_not_inject_directive():
    captured: dict = {}
    agent = _make_agent()
    _stub_llm_for_answer(agent, captured)

    qr = QueryResult(
        question="q", sql="SELECT 1", rows=[{"x": 1}], row_count=1, succeeded=True
    )
    agent._synthesize_answer("q", qr)

    system_prompt = captured["messages"][0]["content"]
    assert "Reply in" not in system_prompt


def test_finnish_injects_reply_directive():
    captured: dict = {}
    agent = _make_agent(answer_language="fi")
    _stub_llm_for_answer(agent, captured)

    qr = QueryResult(
        question="q", sql="SELECT 1", rows=[{"x": 1}], row_count=1, succeeded=True
    )
    agent._synthesize_answer("q", qr)

    system_prompt = captured["messages"][0]["content"]
    assert "Reply in Finnish." in system_prompt


def test_unknown_language_code_passes_through():
    captured: dict = {}
    agent = _make_agent(answer_language="xx")
    _stub_llm_for_answer(agent, captured)

    qr = QueryResult(
        question="q", sql="SELECT 1", rows=[{"x": 1}], row_count=1, succeeded=True
    )
    agent._synthesize_answer("q", qr)

    system_prompt = captured["messages"][0]["content"]
    assert "Reply in xx." in system_prompt


# ---------------------------------------------------------------------------
# Regression: previous-version constructor calls still work
# ---------------------------------------------------------------------------


def test_legacy_constructor_signature_still_works():
    # No extra_instructions, no answer_language — exactly the v0.1.0 API.
    agent = PostgresAgent(
        "postgresql://stub:stub@localhost:1/stub",
        schema_name="public",
        table_allowlist=["customers"],
        max_retries=2,
    )
    assert agent.extra_instructions is None
    assert agent.answer_language == "en"
    assert agent.table_allowlist == ["customers"]
