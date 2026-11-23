"""An agent that fails mid-turn, or while starting, must not harm the next turn.

Three ways the agent bridge used to go wrong, each with its own tests:

* reading the agent's output failed (the CLI died, the SDK reported an error): the
  turn never ended, because the reader task kept the exception to itself and the
  caller went on sending heartbeats until the turn's time limit, with the session
  locked. A stream that just ended without a result was not reported either;
* two first messages for one session both started an agent, and one was lost;
* a bootstrap that failed after the connection left the process running.

The agent client is replaced by a fake with the one property that matters here:
like the real SDK client it has a single message stream for every query, and
``receive_response()`` reads up to the next result.
"""

import asyncio
import dataclasses
import json
import re

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
from wizard_api.services import agent_service as svc

pytestmark = pytest.mark.skipif(not svc._SDK_AVAILABLE, reason="claude-agent-sdk not installed")

SDK_ID = "11111111-1111-4111-8111-111111111111"


def _result(**overrides) -> "ResultMessage":
    fields = dict(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=False,
        num_turns=1,
        session_id=SDK_ID,
    )
    fields.update(overrides)
    return ResultMessage(**fields)


def _assistant(text: str) -> "AssistantMessage":
    wanted = {f.name for f in dataclasses.fields(AssistantMessage)}
    kwargs = {"content": [TextBlock(text=text)], "model": "fake"}
    return AssistantMessage(**{k: v for k, v in kwargs.items() if k in wanted})


def _stream_event(text: str):
    wanted = {f.name for f in dataclasses.fields(svc.StreamEvent)}
    kwargs = {
        "uuid": "u",
        "session_id": "s",
        "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}},
        "parent_tool_use_id": None,
    }
    return svc.StreamEvent(**{k: v for k, v in kwargs.items() if k in wanted})


class FakeClient:
    """Answers ``query("Qn ...")`` with "answer to Qn", in four pieces."""

    instances: list["FakeClient"] = []

    def __init__(self, *, fail_query=False, fail_receive=False, never_finish=False, silent=False):
        FakeClient.instances.append(self)
        self.stream: asyncio.Queue = asyncio.Queue()
        self.disconnected = False
        self.fail_query = fail_query
        self.fail_receive = fail_receive
        self.never_finish = never_finish
        self.silent = silent  # ends the stream without a result
        self.tasks: list[asyncio.Task] = []

    async def connect(self):
        await asyncio.sleep(0.05)

    async def disconnect(self):
        self.disconnected = True

    async def query(self, prompt, session_id="default"):
        if self.fail_query:
            raise RuntimeError("query failed")
        found = re.search(r"Q\d", prompt)
        label = found.group() if found else "bootstrap"

        async def produce():
            pieces = [f"answer to {label} part {i}. " for i in range(4)]
            for piece in pieces:
                await asyncio.sleep(0.03)
                await self.stream.put(_stream_event(piece))
            if self.never_finish:
                await asyncio.sleep(3600)
            await self.stream.put(_assistant("".join(pieces)))
            if not self.silent:
                await self.stream.put(_result())

        self.tasks.append(asyncio.create_task(produce()))

    async def receive_response(self):
        if self.fail_receive:
            raise RuntimeError("the CLI died")
        while True:
            message = await self.stream.get()
            yield message
            if isinstance(message, ResultMessage):
                return


@pytest.fixture(autouse=True)
def _fresh_agent_state(monkeypatch):
    FakeClient.instances = []
    monkeypatch.setattr(svc, "AGENT_SESSIONS", {})
    monkeypatch.setattr(svc, "_START_LOCKS", {})
    monkeypatch.setattr(svc, "_STARTING", {})
    monkeypatch.setattr(svc, "_build_options", lambda *args, **kwargs: None)
    monkeypatch.setattr(svc, "ClaudeSDKClient", lambda options=None: FakeClient())


def _agent(client: FakeClient, session_id="sid") -> dict:
    session = {
        "client": client,
        "lock": asyncio.Lock(),
        "last_active": 0.0,
        "locale": "en",
        "user_id": "u1",
    }
    svc.AGENT_SESSIONS[session_id] = session
    return session


def _payloads(frames: list[str]) -> list[dict]:
    return [json.loads(f.removeprefix("data: ").strip()) for f in frames]


# --- a turn that finishes normally -------------------------------------------------


def test_a_turn_that_finishes_normally_is_left_alone() -> None:
    async def scenario():
        client = FakeClient()
        agent = _agent(client)
        parts: list[str] = []
        frames = [f async for f in svc.stream_turn_for(agent, "Q1 first", parts)]
        return client, parts, frames

    client, parts, frames = asyncio.run(scenario())

    assert _payloads(frames)[-1] == {"done": True}
    assert "answer to Q1 part 3" in "".join(parts)
    assert not client.disconnected
    assert "sid" in svc.AGENT_SESSIONS


# --- the turn that never ended -------------------------------------------------------


def test_an_error_while_reading_the_agent_ends_the_turn_with_an_error_frame() -> None:
    async def scenario():
        client = FakeClient(fail_receive=True)
        agent = _agent(client)

        async def read():
            return [f async for f in svc.stream_turn_for(agent, "Q1 first", [])]

        frames = await asyncio.wait_for(read(), timeout=5)
        return client, agent, frames

    client, agent, frames = asyncio.run(scenario())

    assert any(p.get("error") for p in _payloads(frames))
    assert not agent["lock"].locked()
    # an agent that failed is ended, so the next message starts a new one
    assert client.disconnected
    assert "sid" not in svc.AGENT_SESSIONS


def test_a_stream_that_ends_without_a_result_is_reported_not_left_open() -> None:
    async def scenario():
        client = FakeClient(silent=True)
        agent = _agent(client)
        # the agent's process is gone: the stream ends instead of giving a result
        original = client.receive_response

        async def ends_early():
            async for message in original():
                yield message
                if isinstance(message, AssistantMessage):
                    return

        client.receive_response = ends_early

        async def read():
            return [f async for f in svc.stream_turn_for(agent, "Q1 first", [])]

        frames = await asyncio.wait_for(read(), timeout=5)
        return client, frames

    client, frames = asyncio.run(scenario())

    assert any(p.get("error") for p in _payloads(frames))
    assert not any(p.get("done") for p in _payloads(frames))
    assert client.disconnected


def test_a_message_the_agent_cannot_take_ends_the_agent() -> None:
    async def scenario():
        client = FakeClient(fail_query=True)
        agent = _agent(client)
        with pytest.raises(RuntimeError, match="query failed"):
            async for _ in svc.stream_turn_for(agent, "Q1 first", []):
                pass
        return client, agent

    client, agent = asyncio.run(scenario())

    assert client.disconnected
    assert not agent["lock"].locked()
    assert "sid" not in svc.AGENT_SESSIONS


# --- the agents that were started and lost ---------------------------------------------


def test_two_first_messages_for_one_session_start_one_agent(tmp_path) -> None:
    async def scenario():
        return await asyncio.gather(
            svc.get_or_create_session("s1", str(tmp_path), "en", user_id="u1"),
            svc.get_or_create_session("s1", str(tmp_path), "en", user_id="u1"),
        )

    first, second = asyncio.run(scenario())

    assert len(FakeClient.instances) == 1
    assert first is second
    assert svc.AGENT_SESSIONS["s1"] is first


def test_a_failed_bootstrap_does_not_leave_the_agent_running(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(svc, "ClaudeSDKClient", lambda options=None: FakeClient(fail_query=True))

    with pytest.raises(RuntimeError, match="query failed"):
        asyncio.run(svc.get_or_create_session("s2", str(tmp_path), "en", user_id="u1"))

    assert [c.disconnected for c in FakeClient.instances] == [True]
    assert "s2" not in svc.AGENT_SESSIONS
    assert svc._STARTING == {}


def test_a_bootstrap_that_never_finishes_is_ended(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(svc, "_BOOTSTRAP_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(svc, "ClaudeSDKClient", lambda options=None: FakeClient(never_finish=True))

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(svc.get_or_create_session("s3", str(tmp_path), "en", user_id="u1"))

    assert [c.disconnected for c in FakeClient.instances] == [True]
    assert "s3" not in svc.AGENT_SESSIONS


def test_a_failed_resume_ends_the_client_it_started(tmp_path, monkeypatch) -> None:
    made: list[FakeClient] = []

    class FailsToConnect(FakeClient):
        async def connect(self):
            raise RuntimeError("cannot resume")

    def factory(options=None):
        client = FailsToConnect() if not made else FakeClient()
        made.append(client)
        return client

    monkeypatch.setattr(svc, "ClaudeSDKClient", factory)
    monkeypatch.setattr(svc, "transcript_exists", lambda resume_id: True)

    asyncio.run(
        svc.get_or_create_session(
            "s4", str(tmp_path), "en", resume_id=SDK_ID, transcript=[], user_id="u1"
        )
    )

    assert made[0].disconnected  # the client of the failed resume
    assert not made[1].disconnected  # the one that took over
