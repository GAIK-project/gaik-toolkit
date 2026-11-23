"""API-internal secrets must never reach the wizard agent's environment.

The agent is a subprocess of this API with a Bash tool, and the Claude Agent
SDK merges its ``env`` option over the inherited ``os.environ``. The only thing
that keeps ``WIZARD_API_TOKEN`` and ``WIZARD_DATABASE_URL`` away from it is
``config`` taking them out of the process environment on first read. These
tests pin that behaviour. No SDK, CLI or Postgres needed.
"""

import os

from wizard_api import config
from wizard_api.services import agent_service

NAME = "WIZARD_TEST_SECRET"


def test_consume_takes_the_value_out_of_the_environment(monkeypatch):
    monkeypatch.setenv(NAME, "s3cret")
    config.forget_consumed_secret(NAME)

    assert config._consume_secret(NAME) == "s3cret"
    assert NAME not in os.environ
    # Later reads come from the cache, not the (now empty) environment.
    assert config._consume_secret(NAME) == "s3cret"

    config.forget_consumed_secret(NAME)
    assert config._consume_secret(NAME) is None


def test_a_value_set_again_is_consumed_again(monkeypatch):
    config.forget_consumed_secret(NAME)
    monkeypatch.setenv(NAME, "first")
    assert config._consume_secret(NAME) == "first"
    monkeypatch.setenv(NAME, "second")
    assert config._consume_secret(NAME) == "second"
    assert NAME not in os.environ
    config.forget_consumed_secret(NAME)


def test_service_token_is_consumed_from_the_environment(monkeypatch):
    monkeypatch.setenv("WIZARD_API_TOKEN", "tok-123")
    assert config.get_service_token() == "tok-123"
    assert "WIZARD_API_TOKEN" not in os.environ
    assert config.get_service_token() == "tok-123"


def test_whitespace_token_is_consumed_and_counts_as_unset(monkeypatch):
    monkeypatch.setenv("WIZARD_API_TOKEN", "   ")
    assert config.get_service_token() is None
    assert "WIZARD_API_TOKEN" not in os.environ


def test_database_url_is_consumed_from_the_environment(monkeypatch):
    # Re-set the URL to whatever the suite already runs against so the cached
    # value (and every Postgres-backed test after this one) stays unchanged.
    current = config.get_database_url()
    monkeypatch.setenv("WIZARD_DATABASE_URL", current)
    assert config.get_database_url() == current
    assert "WIZARD_DATABASE_URL" not in os.environ


def test_agent_subprocess_environment_carries_no_api_secrets(monkeypatch):
    monkeypatch.setenv("WIZARD_API_TOKEN", "tok-123")
    monkeypatch.setenv("WIZARD_DATABASE_URL", config.get_database_url())
    config.consume_api_secrets()

    env = agent_service._agent_env()
    for name in config.API_SECRET_ENV:
        assert name not in env
        assert name not in os.environ
    # The getters still work: the values live in config, not in the environment.
    assert config.get_service_token() == "tok-123"
