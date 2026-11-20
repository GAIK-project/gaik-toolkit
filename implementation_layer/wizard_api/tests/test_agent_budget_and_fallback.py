"""The agent's cost limit and fallback model (agent SDK ``max_budget_usd``, ``fallback_model``).

The CLI counts ``max_budget_usd`` for the whole agent process, across messages,
and ends a message over it with an ``error_max_budget_usd`` result. The chat
says so in the session's language, without a "Please continue." nudge, and the
agent is ended, so the next message resumes it with a count of its own. A
fallback model is passed only when it is another model than the agent's, and
the CLI's report of a switch to it is logged.
"""

import asyncio
import dataclasses
import json
import logging

import pytest
from wizard_api import config, ops_metrics
from wizard_api.services import agent_service
from wizard_api.services.agent_tool_guard import ToolGuard

needs_sdk = pytest.mark.skipif(
    not agent_service._SDK_AVAILABLE, reason="claude-agent-sdk not installed"
)
SID = "11111111-1111-4111-8111-111111111111"


@pytest.fixture(autouse=True)
def _no_limits_from_the_environment(monkeypatch):
    for name in ("WIZARD_AGENT_MAX_BUDGET_USD", "WIZARD_AGENT_FALLBACK_MODEL", "ANTHROPIC_MODEL"):
        monkeypatch.delenv(name, raising=False)


# --- config --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("", None),
        ("0", None),
        ("2.5", 2.5),
        (" 10 ", 10.0),
        ("-1", None),
        ("many", None),
        ("inf", None),
        ("nan", None),
    ],
)
def test_the_cost_limit_is_off_unless_a_positive_amount(monkeypatch, raw, expected) -> None:
    monkeypatch.setenv("WIZARD_AGENT_MAX_BUDGET_USD", raw)

    assert config.agent_max_budget_usd() == expected


@pytest.mark.parametrize("raw, expected", [("", None), ("  ", None), (" haiku-x ", "haiku-x")])
def test_the_fallback_model_is_off_unless_named(monkeypatch, raw, expected) -> None:
    monkeypatch.setenv("WIZARD_AGENT_FALLBACK_MODEL", raw)

    assert config.agent_fallback_model() == expected


# --- the options ---------------------------------------------------------------------


def _options(tmp_path):
    return agent_service._build_options(tmp_path, tmp_path, guard=ToolGuard(tmp_path, tmp_path))


@needs_sdk
def test_without_the_variables_the_agent_has_neither_option(tmp_path) -> None:
    options = _options(tmp_path)

    assert options.max_budget_usd is None
    assert options.fallback_model is None


@needs_sdk
def test_the_cost_limit_is_passed_to_the_agent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WIZARD_AGENT_MAX_BUDGET_USD", "4.5")

    assert _options(tmp_path).max_budget_usd == 4.5


@needs_sdk
def test_a_fallback_model_is_passed_only_when_it_is_another_model(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_MODEL", "main-model")
    monkeypatch.setenv("WIZARD_AGENT_FALLBACK_MODEL", "spare-model")
    assert _options(tmp_path).fallback_model == "spare-model"

    monkeypatch.setenv("WIZARD_AGENT_FALLBACK_MODEL", "main-model")
    assert _options(tmp_path).fallback_model is None


# --- a message that stops at the cost limit ------------------------------------------


def _result(subtype="success", is_error=False):
    from claude_agent_sdk import ResultMessage

    return ResultMessage(
        subtype=subtype,
        duration_ms=1,
        duration_api_ms=1,
        is_error=is_error,
        num_turns=3,
        session_id=SID,
        total_cost_usd=4.6,
        errors=["Reached maximum budget ($4.5)"] if is_error else None,
    )


def _text(text: str):
    wanted = {f.name for f in dataclasses.fields(agent_service.StreamEvent)}
    kwargs = {
        "uuid": "u",
        "session_id": "s",
        "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}},
        "parent_tool_use_id": None,
    }
    return agent_service.StreamEvent(**{k: v for k, v in kwargs.items() if k in wanted})


class _Client:
    """Streams ``messages`` for each query."""

    def __init__(self, messages) -> None:
        self.messages = messages
        self.queries: list[str] = []
        self.disconnected = False

    async def query(self, prompt, session_id="default") -> None:
        self.queries.append(prompt)

    async def receive_response(self):
        for message in self.messages:
            yield message

    async def disconnect(self) -> None:
        self.disconnected = True


def _turn(monkeypatch, messages, locale="en"):
    client = _Client(messages)
    agent = {"client": client, "lock": asyncio.Lock(), "last_active": 0.0, "locale": locale}
    monkeypatch.setattr(agent_service, "AGENT_SESSIONS", {"sid": agent})
    monkeypatch.setattr(agent_service, "_START_LOCKS", {})
    parts: list[str] = []

    async def run() -> list[str]:
        return [f async for f in agent_service.stream_turn_for(agent, "Q1", parts)]

    frames = asyncio.run(run())
    payloads = [json.loads(f.removeprefix("data: ").strip()) for f in frames]
    return client, agent, payloads, parts


@pytest.fixture()
def stops(monkeypatch):
    counted: list[int] = []

    class _Counter:
        def add(self, amount, attributes=None):
            counted.append(amount)

    monkeypatch.setattr(ops_metrics, "budget_stops", _Counter())
    monkeypatch.setenv("WIZARD_AGENT_MAX_BUDGET_USD", "4.5")
    return counted


@needs_sdk
def test_a_message_at_the_cost_limit_ends_with_a_plain_notice_and_no_nudge(
    monkeypatch, stops, caplog
) -> None:
    caplog.set_level(logging.WARNING, logger="wizard_api.services.agent_service")
    messages = [_text("I wrote the blueprint."), _result("error_max_budget_usd", is_error=True)]

    client, agent, payloads, parts = _turn(monkeypatch, messages)

    assert client.queries == ["Q1"]  # no "Please continue." after the stop
    assert not any(p.get("error") for p in payloads)
    assert payloads[-1] == {"done": True, "limit": "budget"}
    notice = agent_service.BUDGET_NOTICE["en"]
    assert payloads[-2] == {"delta": f"\n\n{notice}"}
    assert parts == [f"I wrote the blueprint.\n\n{notice}"]
    assert "cost limit" in notice and "continue" in notice
    assert stops == [1]
    [warning] = [r for r in caplog.records if "cost limit" in r.getMessage()]
    assert warning.levelno == logging.WARNING
    assert SID not in warning.getMessage() and "sid" not in warning.getMessage()


@needs_sdk
def test_the_agent_at_its_cost_limit_is_ended_so_the_next_message_resumes_it(
    monkeypatch, stops
) -> None:
    client, agent, _, _ = _turn(monkeypatch, [_result("error_max_budget_usd", is_error=True)])

    assert client.disconnected
    assert "sid" not in agent_service.AGENT_SESSIONS
    # The CLI session is still named, so the next message resumes it (#174).
    assert agent["sdk_session_id"] == SID


@needs_sdk
def test_the_notice_is_in_the_sessions_language(monkeypatch, stops) -> None:
    _, _, payloads, parts = _turn(
        monkeypatch, [_result("error_max_budget_usd", is_error=True)], locale="fi"
    )

    assert parts == [agent_service.BUDGET_NOTICE["fi"]]
    assert payloads[-2] == {"delta": agent_service.BUDGET_NOTICE["fi"]}
    assert "kustannusraja" in parts[0]


@needs_sdk
def test_the_turn_limit_is_answered_as_before(monkeypatch, stops) -> None:
    client, _, payloads, _ = _turn(monkeypatch, [_result("error_max_turns", is_error=True)])

    assert payloads[-1] == agent_service.TURN_LIMIT_FRAME
    assert stops == []
    assert not client.disconnected


# --- the fallback model ----------------------------------------------------------------


@needs_sdk
def test_a_switch_to_the_fallback_model_is_logged(monkeypatch, caplog) -> None:
    from claude_agent_sdk import SystemMessage

    caplog.set_level(logging.INFO, logger="wizard_api.services.agent_service")
    switched = SystemMessage(
        subtype="model_fallback",
        data={
            "type": "system",
            "subtype": "model_fallback",
            "trigger": "overloaded",
            "original_model": "main-model",
            "fallback_model": "spare-model",
            "content": "Switched to spare-model.",
        },
    )

    _, _, payloads, parts = _turn(monkeypatch, [switched, _text("Done."), _result()])

    assert payloads[-1] == {"done": True}
    assert parts == ["Done."]
    [record] = [r for r in caplog.records if "fallback model" in r.getMessage()]
    assert record.levelno == logging.INFO
    assert record.getMessage() == (
        "agent switched from main-model to its fallback model spare-model (trigger overloaded)"
    )


def test_the_budget_stops_start_at_zero_for_alerting() -> None:
    assert ops_metrics._PRIMED["budget_stops"] == [{"limit": "agent"}, {"limit": "usage_cap"}]
