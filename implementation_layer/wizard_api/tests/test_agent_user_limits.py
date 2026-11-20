"""Per-user limits on live agent processes and chat turns.

``WIZARD_MAX_LIVE_AGENTS`` bounds the agents of the whole API process, so one
user opening sessions in several tabs could take every slot. Each user now has
their own cap (``WIZARD_MAX_LIVE_AGENTS_PER_USER``); over it they get a 429
``agent_busy``, and no other user's agent is ended to make room for them.
"""

import asyncio
import time

import pytest
from helpers import requires_postgres
from wizard_api import config
from wizard_api.services import agent_service


class _Client:
    def __init__(self) -> None:
        self.disconnected = False

    async def disconnect(self) -> None:
        self.disconnected = True


def _agent(user_id: str, *, idle: float = 0, busy: bool = False) -> dict:
    lock = asyncio.Lock()
    if busy:
        asyncio.run(lock.acquire())  # held: the agent is mid-turn
    return {
        "client": _Client(),
        "lock": lock,
        "last_active": time.time() - idle,
        "user_id": user_id,
    }


@pytest.fixture
def agents(monkeypatch):
    """A clean agent table, and a start that registers an agent without the SDK."""
    sessions: dict = {}
    monkeypatch.setattr(agent_service, "AGENT_SESSIONS", sessions)
    monkeypatch.setattr(agent_service, "_STARTING", {})
    monkeypatch.setattr(agent_service, "_SDK_AVAILABLE", True)

    async def fake_start(
        session_id, output_dir, locale, resume_id, transcript, user_id, budget_usd=None
    ):
        sessions[session_id] = _agent(user_id)
        return sessions[session_id]

    monkeypatch.setattr(agent_service, "_start_session", fake_start)
    monkeypatch.setenv("WIZARD_MAX_LIVE_AGENTS", "10")
    monkeypatch.setenv("WIZARD_MAX_LIVE_AGENTS_PER_USER", "2")
    return sessions


def _start(session_id: str, user_id: str) -> dict:
    return asyncio.run(agent_service.get_or_create_session(session_id, "/unused", user_id=user_id))


@pytest.mark.parametrize("raw, expected", [("", 2), ("5", 5), ("0", 2), ("-1", 2), ("x", 2)])
def test_the_per_user_agent_limit_reads_a_positive_number(monkeypatch, raw, expected) -> None:
    monkeypatch.setenv("WIZARD_MAX_LIVE_AGENTS_PER_USER", raw)

    assert config.max_live_agents_per_user() == expected


def test_a_user_at_their_cap_is_refused_and_another_user_still_gets_a_slot(agents) -> None:
    agents["a1"] = _agent("alice", busy=True)
    agents["a2"] = _agent("alice", busy=True)

    with pytest.raises(agent_service.AgentUserLimitError):
        _start("a3", "alice")
    bob = _start("b1", "bob")

    assert bob["user_id"] == "bob"
    assert sorted(agents) == ["a1", "a2", "b1"]


def test_a_user_over_their_cap_never_ends_another_users_agent(agents) -> None:
    agents["b-idle"] = _agent("bob", idle=3600)
    agents["a1"] = _agent("alice", busy=True)
    agents["a2"] = _agent("alice", busy=True)

    with pytest.raises(agent_service.AgentUserLimitError):
        _start("a3", "alice")

    assert not agents["b-idle"]["client"].disconnected
    assert sorted(agents) == ["a1", "a2", "b-idle"]


def test_at_their_cap_a_users_own_longest_idle_agent_makes_room(agents) -> None:
    agents["b-idle"] = _agent("bob", idle=7200)
    agents["a-old"] = _agent("alice", idle=3600)
    agents["a-new"] = _agent("alice", idle=120)

    _start("a3", "alice")

    assert sorted(agents) == ["a-new", "a3", "b-idle"]


def test_an_agent_still_starting_counts_against_its_user(agents, monkeypatch) -> None:
    agents["a1"] = _agent("alice", busy=True)
    monkeypatch.setattr(agent_service, "_STARTING", {"a2": "alice"})

    with pytest.raises(agent_service.AgentUserLimitError):
        _start("a3", "alice")


def test_waking_an_already_live_agent_is_not_counted_again(agents) -> None:
    agents["a1"] = _agent("alice", busy=True)
    agents["a2"] = _agent("alice", busy=True)

    assert _start("a2", "alice") is agents["a2"]


def test_the_global_cap_still_applies_below_every_users_own_cap(agents, monkeypatch) -> None:
    monkeypatch.setenv("WIZARD_MAX_LIVE_AGENTS", "2")
    agents["a1"] = _agent("alice", busy=True)
    agents["b1"] = _agent("bob", busy=True)

    with pytest.raises(agent_service.AgentCapacityError):
        _start("c1", "carol")
    assert sorted(agents) == ["a1", "b1"]


def test_the_global_cap_still_ends_the_longest_idle_agent(agents, monkeypatch) -> None:
    monkeypatch.setenv("WIZARD_MAX_LIVE_AGENTS", "2")
    agents["a-idle"] = _agent("alice", idle=3600)
    agents["b1"] = _agent("bob", busy=True)

    _start("c1", "carol")

    assert sorted(agents) == ["b1", "c1"]


# --- chat turns per minute ---------------------------------------------------


@pytest.fixture
def turns(monkeypatch):
    monkeypatch.setattr(agent_service, "_CHAT_TURNS", {})


@pytest.mark.parametrize("raw, expected", [("", 0), ("0", 0), ("6", 6), ("-2", 0), ("x", 0)])
def test_the_chat_turn_rate_is_off_unless_set(monkeypatch, raw, expected) -> None:
    monkeypatch.setenv("WIZARD_MAX_CHAT_TURNS_PER_MINUTE", raw)

    assert config.max_chat_turns_per_minute() == expected


def test_the_chat_turn_rate_is_off_by_default(monkeypatch, turns) -> None:
    monkeypatch.delenv("WIZARD_MAX_CHAT_TURNS_PER_MINUTE", raising=False)
    for _ in range(100):
        agent_service.record_chat_turn("alice", now=0)

    agent_service.check_chat_rate("alice", now=1)


def test_a_user_over_the_chat_turn_rate_waits_for_the_oldest_turn(monkeypatch, turns) -> None:
    monkeypatch.setenv("WIZARD_MAX_CHAT_TURNS_PER_MINUTE", "2")
    agent_service.record_chat_turn("alice", now=100)
    agent_service.record_chat_turn("alice", now=110)

    with pytest.raises(agent_service.ChatRateLimitError) as refused:
        agent_service.check_chat_rate("alice", now=120)
    assert refused.value.retry_after_s == 40
    agent_service.check_chat_rate("bob", now=120)  # another user is not affected
    agent_service.check_chat_rate("alice", now=160)  # the oldest turn has aged out


# --- the 429 the chat endpoint answers -----------------------------------------


@requires_postgres
def test_a_user_over_their_agent_cap_gets_429_agent_busy(client, monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_get_or_create_session(session_id, output_dir, locale=None, **kwargs):
        calls.append(kwargs)
        raise agent_service.AgentUserLimitError("You already have 2 wizard sessions working.")

    monkeypatch.setattr(agent_service, "get_or_create_session", fake_get_or_create_session)
    sid = client.post("/sessions", json={"user_id": "cap-user", "title": "Cap"}).json()["id"]

    res = client.post(f"/sessions/{sid}/chat", json={"message": "hei"})

    assert res.status_code == 429
    detail = res.json()["detail"]
    assert detail["error"] == "agent_busy"
    assert detail["message"] == "You already have 2 wizard sessions working."
    assert detail["trace_id"]
    assert res.headers["retry-after"] == "30"
    assert calls[0]["user_id"] == "cap-user"  # counted for the session's owner


@requires_postgres
def test_a_user_over_the_chat_turn_rate_gets_429_before_an_agent_is_woken(
    client, monkeypatch
) -> None:
    monkeypatch.setenv("WIZARD_MAX_CHAT_TURNS_PER_MINUTE", "1")
    monkeypatch.setattr(agent_service, "_CHAT_TURNS", {})
    started: list[str] = []

    async def fake_get_or_create_session(session_id, output_dir, locale=None, **kwargs):
        started.append(session_id)
        return {"lock": asyncio.Lock()}

    async def fake_stream_turn_for(agent, message, parts):
        yield agent_service.sse({"done": True})

    monkeypatch.setattr(agent_service, "get_or_create_session", fake_get_or_create_session)
    monkeypatch.setattr(agent_service, "stream_turn_for", fake_stream_turn_for)
    sid = client.post("/sessions", json={"user_id": "rate-user", "title": "Rate"}).json()["id"]

    assert client.post(f"/sessions/{sid}/chat", json={"message": "yksi"}).status_code == 200
    res = client.post(f"/sessions/{sid}/chat", json={"message": "kaksi"})

    assert res.status_code == 429
    assert res.json()["detail"]["error"] == "chat_rate_limited"
    assert 1 <= int(res.headers["retry-after"]) <= 60
    assert len(started) == 1
