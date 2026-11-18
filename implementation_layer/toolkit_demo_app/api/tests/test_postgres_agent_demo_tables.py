"""The demo's PostgresAgent is built with the demo schema's own tables."""

import pytest

pytest.importorskip("psycopg")


def test_demo_agent_reads_only_the_demo_tables(monkeypatch):
    from api.routers import postgres_agent

    monkeypatch.setenv("DATABASE_URL", "postgresql://demo:demo@localhost:1/demo")
    monkeypatch.setattr(postgres_agent, "_seed_demo_schema", lambda url: None)
    monkeypatch.setattr(postgres_agent, "_llm_config", lambda: None)

    agent = postgres_agent._make_agent()

    assert agent.table_allowlist == ["customers", "orders"]
    assert agent.schema_name == postgres_agent.DEMO_SCHEMA
