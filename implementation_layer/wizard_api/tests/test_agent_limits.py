"""Limits on chat message length, agent turns and live agent processes.

Each live session holds a CLI process in the API pod and every message is a
billed model call, so all three are bounded and configurable.
"""

import asyncio
import time

import pytest
from pydantic import ValidationError
from wizard_api import config
from wizard_api.routers.sessions import ChatRequest
from wizard_api.services import agent_service
from wizard_api.services.agent_tool_guard import ToolGuard


def test_a_chat_message_has_a_maximum_length() -> None:
    limit = config.max_chat_message_chars()

    assert ChatRequest(message="x" * limit).message
    with pytest.raises(ValidationError):
        ChatRequest(message="x" * (limit + 1))


@pytest.mark.parametrize("raw, expected", [("", 20), ("5", 5), ("0", 20), ("-3", 20), ("many", 20)])
def test_the_live_agent_limit_reads_a_positive_number(monkeypatch, raw, expected) -> None:
    monkeypatch.setenv("WIZARD_MAX_LIVE_AGENTS", raw)

    assert config.max_live_agents() == expected


class _Client:
    def __init__(self) -> None:
        self.disconnected = False

    async def disconnect(self) -> None:
        self.disconnected = True


def test_at_the_limit_the_longest_idle_agent_makes_room(monkeypatch) -> None:
    monkeypatch.setenv("WIZARD_MAX_LIVE_AGENTS", "2")
    sessions: dict = {}
    monkeypatch.setattr(agent_service, "AGENT_SESSIONS", sessions)

    async def scenario() -> None:
        for sid, idle in (("recent", 10), ("oldest", 500)):
            sessions[sid] = {
                "client": _Client(),
                "lock": asyncio.Lock(),
                "last_active": time.time() - idle,
            }
        await agent_service._make_room()

    asyncio.run(scenario())
    assert list(sessions) == ["recent"]


def test_when_every_agent_is_mid_turn_a_new_one_is_refused(monkeypatch) -> None:
    monkeypatch.setenv("WIZARD_MAX_LIVE_AGENTS", "1")
    sessions: dict = {}
    monkeypatch.setattr(agent_service, "AGENT_SESSIONS", sessions)

    async def scenario() -> None:
        lock = asyncio.Lock()
        await lock.acquire()
        sessions["busy"] = {"client": _Client(), "lock": lock, "last_active": time.time()}
        await agent_service._make_room()

    with pytest.raises(agent_service.AgentCapacityError):
        asyncio.run(scenario())
    assert list(sessions) == ["busy"]


def test_the_agent_has_a_turn_limit(tmp_path, monkeypatch) -> None:
    if not agent_service._SDK_AVAILABLE:
        pytest.skip("claude_agent_sdk is not installed")
    monkeypatch.setenv("WIZARD_AGENT_MAX_TURNS", "42")

    assert (
        agent_service._build_options(
            tmp_path, tmp_path / "out", guard=ToolGuard(tmp_path, tmp_path / "out")
        ).max_turns
        == 42
    )


def test_an_agent_just_handed_to_a_request_is_not_ended(monkeypatch) -> None:
    monkeypatch.setenv("WIZARD_MAX_LIVE_AGENTS", "1")
    sessions: dict = {}
    monkeypatch.setattr(agent_service, "AGENT_SESSIONS", sessions)

    async def scenario() -> None:
        sessions["fetched"] = {"client": _Client(), "lock": asyncio.Lock(), "last_active": 0}
        await agent_service.get_or_create_session("fetched", "/unused")
        await agent_service._make_room()

    with pytest.raises(agent_service.AgentCapacityError):
        asyncio.run(scenario())
    assert list(sessions) == ["fetched"]


def test_the_turn_limit_is_its_own_frame() -> None:
    frame = agent_service.sse(agent_service.TURN_LIMIT_FRAME)

    assert agent_service.frame_is_error(frame)
    assert agent_service.frame_is_turn_limit(frame)
    assert not agent_service.frame_is_turn_limit(agent_service.sse({"error": True}))
