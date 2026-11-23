"""The user can release a session's agent, and ask in the chat for the other language.

Two dead ends from user testing. A finished user had no way to give the agent
back: it was held until 30 idle minutes had passed or its place was needed. And
"can you answer in English" was answered with "I cannot change the language":
the reply language follows the interface language, which the agent cannot set,
and nothing told it how the user could.
"""

import asyncio
import json

from conftest import requires_postgres
from wizard_api.services import agent_service
from wizard_api.services.agent_tool_guard import ToolGuard


class _Client:
    def __init__(self) -> None:
        self.disconnected = False

    async def disconnect(self) -> None:
        self.disconnected = True


def _live_agent(session_id: str) -> _Client:
    client = _Client()
    agent_service.AGENT_SESSIONS[session_id] = {
        "client": client,
        "lock": asyncio.Lock(),
        "last_active": 0.0,
        "user_id": "ender",
    }
    return client


@requires_postgres
def test_ending_the_agent_releases_it_and_keeps_the_conversation(client) -> None:
    created = client.post("/sessions", json={"user_id": "ender", "title": "End"}).json()
    sid = created["id"]
    client.post(
        f"/sessions/{sid}/messages",
        json={"user_content": "Hei", "assistant_content": "Hei, miten voin auttaa?"},
    )
    agent = _live_agent(sid)
    try:
        assert client.get(f"/sessions/{sid}").json()["agent_live"] is True

        res = client.post(f"/sessions/{sid}/agent/end")

        assert res.status_code == 200
        assert res.json() == {"ended": True}
        assert agent.disconnected
        detail = client.get(f"/sessions/{sid}").json()
        assert detail["agent_live"] is False
        assert [m["content"] for m in detail["metadata"]["messages"]] == [
            "Hei",
            "Hei, miten voin auttaa?",
        ]
        # Ending it twice is not an error: there is nothing left to end.
        assert client.post(f"/sessions/{sid}/agent/end").json() == {"ended": False}
    finally:
        agent_service.AGENT_SESSIONS.pop(sid, None)


@requires_postgres
def test_an_agent_in_the_middle_of_a_reply_is_not_ended(client) -> None:
    sid = client.post("/sessions", json={"user_id": "ender", "title": "Busy"}).json()["id"]
    agent = _live_agent(sid)
    turn = agent_service.begin_turn(sid, "Hei")
    try:
        res = client.post(f"/sessions/{sid}/agent/end")
    finally:
        asyncio.run(agent_service.end_turn(sid, turn))
        agent_service.AGENT_SESSIONS.pop(sid, None)

    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "agent_busy"
    assert not agent.disconnected


def test_the_agent_offers_the_other_language_as_a_button():
    async def scenario() -> tuple[str, str, list[str]]:
        turn = agent_service.begin_turn("lang-1", "Can you answer in English")
        try:
            good = await agent_service.offer_language_for_agent("lang-1", {"language": "EN "})
            bad = await agent_service.offer_language_for_agent("lang-1", {"language": "it"})
        finally:
            await agent_service.end_turn("lang-1", turn)
        return good, bad, turn.frames

    good, bad, frames = asyncio.run(scenario())

    assert "switches the interface to English" in good
    assert 'must be "fi" or "en"' in bad
    # One button, for the language the interface has; nothing for the other call.
    assert [json.loads(frame[6:]) for frame in frames] == [{"offer_locale": "en"}]


def test_without_a_reply_on_its_way_there_is_no_button_to_offer():
    told = asyncio.run(agent_service.offer_language_for_agent("lang-2", {"language": "fi"}))

    assert "FI / EN" in told


def test_the_bootstrap_says_what_to_do_when_asked_for_the_other_language(tmp_path):
    prompt = agent_service._bootstrap_prompt(tmp_path, "fi")

    assert "offer_language" in prompt
    assert "Never answer that you cannot change the language" in prompt
    # The pin itself is unchanged: the language still follows the interface.
    assert "regardless of the language the user writes in" in prompt


def test_the_tool_guard_lets_the_language_tool_through(tmp_path):
    assert ToolGuard(tmp_path, tmp_path).check(agent_service.OFFER_LANGUAGE_TOOL, {}) is None
