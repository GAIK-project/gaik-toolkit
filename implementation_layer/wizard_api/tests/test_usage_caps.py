"""Spend caps per session, per user and per deployment month, and sessions per user.

The cost of each chat turn is added to the session, the user and the month
(services/usage_caps.py). A reached cap refuses the next message before an agent
is woken (402 usage_cap), an agent starts with what the caps have left as its
budget, and the chat says once when most of a cap is used. A user may create a
set number of sessions; removing one gives its place back, not its spend.
"""

import asyncio
import json
import threading
import time
import uuid
from datetime import UTC, datetime

import pytest
from conftest import requires_postgres
from sqlalchemy.orm import sessionmaker
from wizard_api import config
from wizard_api.db import get_db
from wizard_api.main import app
from wizard_api.models import UsageTotal, WizardSession
from wizard_api.ownership import USER_HEADER
from wizard_api.services import agent_service, usage_caps
from wizard_api.services.agent_service import sse

NOV = datetime(2026, 11, 20, 12, tzinfo=UTC)
DEC = datetime(2026, 12, 1, 0, 5, tzinfo=UTC)


@pytest.fixture
def caps(monkeypatch):
    """Turn the caps on with round numbers: 5 per session, 10 per user, 100 a month."""

    def set_caps(session="5", user="10", deployment="100", sessions="3", ratio=None):
        monkeypatch.setenv("WIZARD_SESSION_MAX_COST_USD", session)
        monkeypatch.setenv("WIZARD_USER_MAX_COST_USD", user)
        monkeypatch.setenv("WIZARD_DEPLOYMENT_MAX_COST_USD", deployment)
        monkeypatch.setenv("WIZARD_MAX_SESSIONS_PER_USER", sessions)
        if ratio is not None:
            monkeypatch.setenv("WIZARD_COST_WARN_RATIO", ratio)

    set_caps()
    return set_caps


# --- settings ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name, default",
    [
        ("WIZARD_SESSION_MAX_COST_USD", 5.4),
        ("WIZARD_USER_MAX_COST_USD", 10.8),
        ("WIZARD_DEPLOYMENT_MAX_COST_USD", 2000.0),
    ],
)
def test_a_cost_cap_is_on_by_default_and_zero_turns_it_off(monkeypatch, name, default) -> None:
    read = {
        "WIZARD_SESSION_MAX_COST_USD": config.session_max_cost_usd,
        "WIZARD_USER_MAX_COST_USD": config.user_max_cost_usd,
        "WIZARD_DEPLOYMENT_MAX_COST_USD": config.deployment_max_cost_usd,
    }[name]
    monkeypatch.delenv(name, raising=False)
    assert read() == default
    for typo in ("-1", "lots", "inf", "nan"):
        monkeypatch.setenv(name, typo)
        assert read() == default, typo  # a typo does not lift the cap
    monkeypatch.setenv(name, " 7.5 ")
    assert read() == 7.5
    monkeypatch.setenv(name, "0")
    assert read() is None


def test_sessions_per_user_default_to_three_and_zero_is_no_limit(monkeypatch) -> None:
    monkeypatch.delenv("WIZARD_MAX_SESSIONS_PER_USER", raising=False)
    assert config.max_sessions_per_user() == 3
    for typo in ("-2", "three"):
        monkeypatch.setenv("WIZARD_MAX_SESSIONS_PER_USER", typo)
        assert config.max_sessions_per_user() == 3
    monkeypatch.setenv("WIZARD_MAX_SESSIONS_PER_USER", "5")
    assert config.max_sessions_per_user() == 5
    monkeypatch.setenv("WIZARD_MAX_SESSIONS_PER_USER", "0")
    assert config.max_sessions_per_user() is None


@pytest.mark.parametrize(
    "raw, expected", [("", 0.8), ("0.9", 0.9), ("0", 0.8), ("1", 0.8), ("x", 0.8)]
)
def test_the_warning_share_stays_between_zero_and_one(monkeypatch, raw, expected) -> None:
    monkeypatch.setenv("WIZARD_COST_WARN_RATIO", raw)
    assert config.cost_warn_ratio() == expected


def test_the_month_is_counted_in_utc() -> None:
    assert usage_caps.month(NOV) == "2026-11"
    assert usage_caps.month(DEC) == "2026-12"


# --- the agent's budget --------------------------------------------------------------


def test_the_agent_gets_the_smaller_of_its_own_limit_and_what_the_caps_left(monkeypatch) -> None:
    monkeypatch.delenv("WIZARD_AGENT_MAX_BUDGET_USD", raising=False)
    assert agent_service._agent_budget(None) is None
    assert agent_service._agent_budget(2.5) == 2.5
    assert agent_service._budget_is_cap(2.5)

    monkeypatch.setenv("WIZARD_AGENT_MAX_BUDGET_USD", "4")
    assert agent_service._agent_budget(None) == 4
    assert agent_service._agent_budget(9) == 4
    assert not agent_service._budget_is_cap(9)
    assert agent_service._agent_budget(1.5) == 1.5
    assert agent_service._budget_is_cap(1.5)


def test_a_stop_at_a_cap_set_budget_says_the_usage_limit_is_reached() -> None:
    parts: list[str] = []
    frames = list(
        agent_service._budget_stop({"locale": "fi", "budget_from_caps": True}, "Tein", parts)
    )

    assert agent_service.CAP_NOTICE["fi"] in parts[0]
    assert "jatka" not in parts[0]  # the next message is refused, so no "continue"
    assert json.loads(frames[-1][6:]) == {"done": True, "limit": "budget"}


def test_a_cap_stop_is_logged_and_counted_as_the_caps(monkeypatch, caplog) -> None:
    from wizard_api import ops_metrics

    counted: list = []

    class _Counter:
        def add(self, amount, attributes=None):
            counted.append(attributes)

    monkeypatch.setattr(ops_metrics, "budget_stops", _Counter())
    caplog.set_level("WARNING", logger="wizard_api.services.agent_service")
    list(
        agent_service._budget_stop(
            {"locale": "en", "budget_from_caps": True, "budget_usd": 2.5}, "", []
        )
    )

    assert counted == [{"limit": "usage_cap"}]
    assert "2.50 USD the usage caps left" in caplog.text
    assert "None" not in caplog.text


def test_a_stop_at_the_agents_own_limit_still_says_go_on() -> None:
    parts: list[str] = []
    list(agent_service._budget_stop({"locale": "en"}, "", parts))

    assert parts == [agent_service.BUDGET_NOTICE["en"]]


# --- the ledger ----------------------------------------------------------------------


def _session(db, user="ann", cost=None) -> WizardSession:
    metadata = {usage_caps.SESSION_COST_KEY: cost} if cost is not None else {}
    row = WizardSession(user_id=user, output_dir="/tmp/x", session_metadata=metadata)
    db.add(row)
    db.commit()
    return row


def _total(db, scope, key) -> UsageTotal | None:
    db.expire_all()
    return db.get(UsageTotal, (scope, key))


@requires_postgres
def test_a_turns_cost_counts_for_the_session_the_user_and_the_month(db_session, caps) -> None:
    row = _session(db_session)

    usage_caps.record_cost(db_session, "ann", 1.25, session=row, now=NOV)
    usage_caps.record_cost(db_session, "ann", 0.5, session=row, now=NOV)

    db_session.refresh(row)
    assert usage_caps.session_spent(row) == pytest.approx(1.75)
    assert _total(db_session, "user", "ann").cost_usd == pytest.approx(1.75)
    assert _total(db_session, "deployment", "2026-11").cost_usd == pytest.approx(1.75)
    usage_caps.record_cost(db_session, "ann", 0.25, session=row, now=DEC)
    assert _total(db_session, "deployment", "2026-12").cost_usd == pytest.approx(0.25)


@requires_postgres
def test_nothing_is_recorded_for_a_turn_without_cost(db_session, caps) -> None:
    row = _session(db_session)

    assert usage_caps.record_cost(db_session, "ann", 0.0, session=row) == []
    assert _total(db_session, "user", "ann") is None


@requires_postgres
def test_a_session_deleted_mid_turn_still_counts_for_its_owner(db_session, caps) -> None:
    usage_caps.record_cost(db_session, "ann", 2.0, session=None, now=NOV)

    assert _total(db_session, "user", "ann").cost_usd == pytest.approx(2.0)
    assert _total(db_session, "deployment", "2026-11").cost_usd == pytest.approx(2.0)


@requires_postgres
def test_each_cap_is_warned_of_once_when_its_share_is_used(db_session, caps) -> None:
    caps(ratio="0.8")
    row = _session(db_session)

    assert usage_caps.record_cost(db_session, "ann", 3.9, session=row, now=NOV) == []
    assert usage_caps.record_cost(db_session, "ann", 0.2, session=row, now=NOV) == ["session"]
    assert usage_caps.record_cost(db_session, "ann", 0.2, session=row, now=NOV) == []
    other = _session(db_session)
    assert usage_caps.record_cost(db_session, "ann", 3.7, session=other, now=NOV) == ["user"]
    assert usage_caps.record_cost(db_session, "ann", 0.1, session=other, now=NOV) == []


@requires_postgres
def test_a_turn_that_did_not_complete_leaves_the_warning_for_the_next(db_session, caps) -> None:
    caps(ratio="0.8")
    row = _session(db_session)

    assert usage_caps.record_cost(db_session, "ann", 4.5, session=row, now=NOV, warn=False) == []
    db_session.refresh(row)
    assert usage_caps.session_spent(row) == pytest.approx(4.5)  # still counted
    assert usage_caps.record_cost(db_session, "ann", 0.1, session=row, now=NOV) == ["session"]


@requires_postgres
def test_a_cap_that_is_off_is_never_warned_of(db_session, caps) -> None:
    caps(session="0", user="0")
    row = _session(db_session)

    assert usage_caps.record_cost(db_session, "ann", 50.0, session=row, now=NOV) == []


@requires_postgres
def test_a_reached_cap_refuses_and_the_month_is_named_first(db_session, caps) -> None:
    row = _session(db_session, cost=5.0)
    with pytest.raises(usage_caps.UsageCapError) as refused:
        usage_caps.chat_budget(db_session, row, now=NOV)
    assert refused.value.scope == "session"

    fresh = _session(db_session)
    usage_caps.record_cost(db_session, "ann", 10.0, session=None, now=NOV)
    with pytest.raises(usage_caps.UsageCapError) as refused:
        usage_caps.chat_budget(db_session, fresh, now=NOV)
    assert refused.value.scope == "user"

    usage_caps.record_cost(db_session, "bob", 90.0, session=None, now=NOV)
    with pytest.raises(usage_caps.UsageCapError) as refused:
        usage_caps.chat_budget(db_session, fresh, now=NOV)
    assert refused.value.scope == "deployment"
    # A new month starts from zero for the deployment, not for the user.
    with pytest.raises(usage_caps.UsageCapError) as refused:
        usage_caps.chat_budget(db_session, fresh, now=DEC)
    assert refused.value.scope == "user"


@requires_postgres
def test_the_budget_is_the_smallest_amount_left(db_session, caps) -> None:
    row = _session(db_session, cost=1.0)
    assert usage_caps.chat_budget(db_session, row, now=NOV) == pytest.approx(4.0)

    usage_caps.record_cost(db_session, "ann", 7.5, session=None, now=NOV)
    assert usage_caps.chat_budget(db_session, row, now=NOV) == pytest.approx(2.5)

    caps(session="0", user="0", deployment="0")
    assert usage_caps.chat_budget(db_session, row, now=NOV) is None


@requires_postgres
def test_a_running_replys_budget_is_held_against_the_users_cap(
    db_session, caps, monkeypatch
) -> None:
    monkeypatch.setattr(usage_caps, "_RESERVED", {})
    caps(session="5", user="10", deployment="100")
    first, second, third = (_session(db_session) for _ in range(3))
    usage_caps.record_cost(db_session, "ann", 3.0, session=None, now=NOV)

    one = usage_caps.reserve("ann", usage_caps.caps_left(db_session, first, now=NOV))
    assert one.budget == pytest.approx(5.0)  # the session's cap is the smaller
    two = usage_caps.reserve("ann", usage_caps.caps_left(db_session, second, now=NOV))
    assert two.budget == pytest.approx(2.0)  # 7 left, 5 held by the first
    with pytest.raises(usage_caps.UsageReservedError):
        usage_caps.reserve("ann", usage_caps.caps_left(db_session, third, now=NOV))
    # Another user is not affected.
    bob = _session(db_session, user="bob")
    assert usage_caps.reserve("bob", usage_caps.caps_left(db_session, bob, now=NOV)).budget == 5.0

    one.release()
    one.release()  # a second release gives nothing back twice
    assert usage_caps._RESERVED["ann"] == pytest.approx(2.0)  # noqa: SLF001
    two.release()
    assert "ann" not in usage_caps._RESERVED  # noqa: SLF001


@requires_postgres
def test_too_little_left_for_a_reply_is_refused_as_a_reached_cap(db_session, caps) -> None:
    row = _session(db_session, cost=5.0 - usage_caps.MIN_TURN_BUDGET_USD / 2)
    with pytest.raises(usage_caps.UsageCapError) as refused:
        usage_caps.chat_budget(db_session, row, now=NOV)
    assert refused.value.scope == "session"


def test_a_live_agent_with_more_budget_than_the_caps_leave_is_ended(monkeypatch) -> None:
    ended: list[str] = []

    async def end(session_id):
        ended.append(session_id)
        return True

    monkeypatch.setattr(agent_service, "end_session", end)
    monkeypatch.setattr(agent_service, "AGENT_SESSIONS", {})
    sid = "a"
    idle = time.time() - 600
    agent = {"lock": asyncio.Lock(), "budget_usd": 10.0, "cost_total_usd": 2.0, "last_active": idle}
    agent_service.AGENT_SESSIONS[sid] = agent

    assert asyncio.run(agent_service.fit_budget(sid, 8.0)) is False  # it has 8 left
    assert asyncio.run(agent_service.fit_budget(sid, None)) is False
    # Within the margin a small overrun is allowed, so switching sessions
    # does not restart the agent each time.
    assert asyncio.run(agent_service.fit_budget(sid, 7.5)) is False
    assert asyncio.run(agent_service.fit_budget(sid, 3.0)) is True
    assert ended == [sid]
    # One without a budget of its own is ended when a cap now sets one.
    agent_service.AGENT_SESSIONS[sid] = {
        "lock": asyncio.Lock(),
        "budget_usd": None,
        "last_active": idle,
    }
    assert asyncio.run(agent_service.fit_budget(sid, 3.0)) is True


def test_an_agent_just_handed_to_a_request_is_not_ended(monkeypatch) -> None:
    async def end(session_id):
        raise AssertionError("an agent being set up for a turn must not be ended")

    monkeypatch.setattr(agent_service, "end_session", end)
    monkeypatch.setattr(
        agent_service,
        "AGENT_SESSIONS",
        {"a": {"lock": asyncio.Lock(), "budget_usd": 10.0, "handed_at": time.time()}},
    )

    assert asyncio.run(agent_service.fit_budget("a", 1.0)) is False


def test_an_agent_whose_turn_just_ended_is_still_fitted(monkeypatch) -> None:
    ended: list[str] = []

    async def end(session_id):
        ended.append(session_id)
        return True

    monkeypatch.setattr(agent_service, "end_session", end)
    agent = {
        "lock": asyncio.Lock(),
        "budget_usd": 10.0,
        "last_active": time.time(),  # its last turn ended a moment ago
        "handed_at": time.time() - 120,
    }
    monkeypatch.setattr(agent_service, "AGENT_SESSIONS", {"a": agent})

    assert asyncio.run(agent_service.fit_budget("a", 1.0)) is True
    assert ended == ["a"]


@requires_postgres
def test_sessions_are_counted_and_the_limit_holds_under_concurrency(db_engine, caps) -> None:
    factory = sessionmaker(bind=db_engine)
    outcomes: list[str] = []

    def claim() -> None:
        db = factory()
        try:
            usage_caps.claim_session(db, "crowd")
            # The caller creates the session in the same transaction, as the route does.
            db.add(WizardSession(user_id="crowd", output_dir="/tmp/x"))
            db.commit()
            outcomes.append("ok")
        except usage_caps.SessionLimitError:
            outcomes.append("refused")
        finally:
            db.close()

    threads = [threading.Thread(target=claim) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ["ok"] * 3 + ["refused"] * 5
    db = factory()
    try:
        assert db.get(UsageTotal, ("user", "crowd")).sessions_held == 3
        assert usage_caps.open_sessions(db, "crowd") == 3
        db.query(UsageTotal).delete()
        db.query(WizardSession).filter(WizardSession.user_id == "crowd").delete()
        db.commit()
    finally:
        db.close()


@requires_postgres
def test_without_a_session_limit_every_session_is_still_counted(db_session, caps) -> None:
    caps(sessions="0")
    for _ in range(5):
        usage_caps.claim_session(db_session, "many")

    assert _total(db_session, "user", "many").sessions_held == 5


# --- through the API -----------------------------------------------------------------


@requires_postgres
def test_the_fourth_session_in_progress_is_refused_and_removing_one_makes_room_but_keeps_its_spend(
    client, db_engine, caps
) -> None:
    ids = [
        client.post("/sessions", json={"user_id": "ann", "title": f"S{n}"}).json()["id"]
        for n in range(3)
    ]
    refused = client.post("/sessions", json={"user_id": "ann", "title": "S4"})
    assert refused.status_code == 429
    assert refused.json()["detail"]["error"] == "session_limit"
    db = sessionmaker(bind=db_engine)()
    try:
        usage_caps.record_cost(db, "ann", 4.0, session=db.get(WizardSession, uuid.UUID(ids[0])))
    finally:
        db.close()

    assert client.delete(f"/sessions/{ids[0]}", headers={USER_HEADER: "ann"}).status_code == 204
    assert client.post("/sessions", json={"user_id": "ann", "title": "S5"}).status_code == 201
    assert client.post("/sessions", json={"user_id": "ann", "title": "S6"}).status_code == 429
    db = sessionmaker(bind=db_engine)()
    try:
        assert _total(db, "user", "ann").cost_usd == pytest.approx(4.0)  # spend stays
        assert _total(db, "user", "ann").sessions_held == 3
    finally:
        db.close()
    # Another user has places of their own.
    assert client.post("/sessions", json={"user_id": "bob", "title": "B1"}).status_code == 201


@requires_postgres
def test_a_session_that_could_not_be_created_gives_its_place_back(
    client, caps, monkeypatch
) -> None:
    from wizard_api.services import session_service

    def broken(db, payload):
        raise RuntimeError("database gone")

    monkeypatch.setattr(session_service, "create_session", broken)
    with pytest.raises(RuntimeError):
        client.post("/sessions", json={"user_id": "ann", "title": "S"})
    monkeypatch.undo()
    caps()

    for n in range(3):
        assert (
            client.post("/sessions", json={"user_id": "ann", "title": f"S{n}"}).status_code == 201
        )


@requires_postgres
def test_a_caller_cannot_set_the_sessions_spend(client, caps) -> None:
    sid = client.post("/sessions", json={"user_id": "ann", "title": "S"}).json()["id"]

    for key in (usage_caps.SESSION_COST_KEY, usage_caps.SESSION_WARNED_KEY):
        res = client.patch(f"/sessions/{sid}", json={"metadata": {key: 0}})
        assert res.status_code == 422, key
        res = client.post("/sessions", json={"user_id": "bob", "title": "S", "metadata": {key: 0}})
        assert res.status_code == 422, key


@pytest.fixture
def turn_client(client, db_engine):
    """A database session per request, as the chat's own turn opens one."""
    factory = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    def own_session():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = own_session
    return client


def _frames(text: str) -> list[dict]:
    return [
        json.loads(line[len("data: ") :])
        for line in text.split("\n\n")
        if line.startswith("data: ") and "heartbeat" not in line
    ]


@requires_postgres
def test_a_message_over_a_cap_is_refused_before_an_agent_is_woken(
    turn_client, db_engine, caps, monkeypatch
) -> None:
    woken: list[str] = []

    async def no_agent(*args, **kwargs):
        woken.append("agent")
        raise AssertionError("no agent may be started")

    monkeypatch.setattr(agent_service, "get_or_create_session", no_agent)
    sid = turn_client.post("/sessions", json={"user_id": "ann", "title": "S"}).json()["id"]
    db = sessionmaker(bind=db_engine)()
    try:
        row = db.get(WizardSession, uuid.UUID(sid))
        usage_caps.record_cost(db, "ann", 5.0, session=row)
    finally:
        db.close()

    res = turn_client.post(f"/sessions/{sid}/chat", json={"message": "Jatka"})

    assert res.status_code == 402
    assert res.json()["detail"]["error"] == "usage_cap"
    assert res.json()["detail"]["scope"] == "session"
    assert woken == []


def _result(cost: float):
    sdk = pytest.importorskip("claude_agent_sdk")
    return sdk.ResultMessage(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=False,
        num_turns=1,
        session_id="s",
        total_cost_usd=cost,
    )


def _wait_for(condition, seconds: float = 5.0) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.02)


@requires_postgres
def test_a_turn_is_counted_and_most_of_the_cap_is_said_once(turn_client, caps, monkeypatch) -> None:
    caps(session="5", user="100", deployment="1000", ratio="0.8")
    budgets: list = []
    agent = {"lock": asyncio.Lock()}

    async def fake_agent(session_id, output_dir, locale=None, **kwargs):
        budgets.append(kwargs.get("budget_usd"))
        return agent

    async def stream(_agent, message, parts):
        # What the SDK reports for the query: its running total for the client.
        spent = agent.get("cost_total_usd", 0.0) + 2.1
        agent["turn_results"] = [("turn", _result(spent))]
        parts.append("Valmis.")
        yield sse({"delta": "Valmis."})
        yield sse({"done": True})

    monkeypatch.setattr(agent_service, "get_or_create_session", fake_agent)
    monkeypatch.setattr(agent_service, "stream_turn_for", stream)
    sid = turn_client.post("/sessions", json={"user_id": "ann", "title": "S"}).json()["id"]

    def send() -> list[dict]:
        res = turn_client.post(f"/sessions/{sid}/chat", json={"message": "Hei", "locale": "fi"})
        assert res.status_code == 200
        _wait_for(lambda: not agent_service.is_busy(sid))
        return _frames(res.text)

    first = send()
    second = send()
    third = send()

    assert budgets == [pytest.approx(5.0), pytest.approx(2.9), pytest.approx(0.8)]
    notice = usage_caps.notice("session", "fi")
    assert not any(notice in f.get("delta", "") for f in first)
    assert any(notice in f.get("delta", "") for f in second)  # 4.2 of 5 used
    assert not any(notice in f.get("delta", "") for f in third)
    detail = turn_client.get(f"/sessions/{sid}").json()
    replies = [m["content"] for m in detail["metadata"]["messages"] if m["role"] == "assistant"]
    assert notice in replies[1]  # kept with the reply, for a reload
    assert detail["metadata"][usage_caps.SESSION_COST_KEY] == pytest.approx(6.3)
    assert "ann" not in usage_caps._RESERVED  # noqa: SLF001 - each reply gave its budget back
    # Now over the cap: the next message is refused.
    refused = turn_client.post(f"/sessions/{sid}/chat", json={"message": "Hei"})
    assert refused.status_code == 402
    assert refused.json()["detail"]["scope"] == "session"


@requires_postgres
def test_a_turn_that_ends_in_an_error_leaves_the_notice_for_the_next(
    turn_client, caps, monkeypatch
) -> None:
    caps(session="5", user="100", deployment="1000", ratio="0.8")
    agent = {"lock": asyncio.Lock()}
    fail = [True]

    async def fake_agent(session_id, output_dir, locale=None, **kwargs):
        return agent

    async def stream(_agent, message, parts):
        spent = agent.get("cost_total_usd", 0.0) + 2.1
        agent["turn_results"] = [("turn", _result(spent))]
        if fail[0]:
            yield sse({"error": True, "message": "broken"})
            return
        parts.append("Valmis.")
        yield sse({"delta": "Valmis."})
        yield sse({"done": True})

    monkeypatch.setattr(agent_service, "get_or_create_session", fake_agent)
    monkeypatch.setattr(agent_service, "stream_turn_for", stream)
    sid = turn_client.post("/sessions", json={"user_id": "ann", "title": "S"}).json()["id"]

    def send() -> list[dict]:
        res = turn_client.post(f"/sessions/{sid}/chat", json={"message": "Hei", "locale": "fi"})
        assert res.status_code == 200
        _wait_for(lambda: not agent_service.is_busy(sid))
        return _frames(res.text)

    notice = usage_caps.notice("session", "fi")
    send()
    failed = send()  # 4.2 of 5 used, but the reader stops at the error frame
    assert not any(notice in f.get("delta", "") for f in failed)
    fail[0] = False
    caps(session="10", user="100", deployment="1000", ratio="0.4")
    given = send()  # 6.3 of 10: the notice not yet given comes now
    assert any(notice.replace("80", "40") in f.get("delta", "") for f in given)


def test_a_query_that_ended_with_no_result_is_charged_an_estimate() -> None:
    from wizard_api import telemetry

    async def frames():
        yield sse({"error": True, "message": "the agent's stream ended without a result"})

    roomy = {"budget_usd": 5.0, "cost_total_usd": 1.0, "query_unfinished": True}
    tight = {"budget_usd": 1.3, "cost_total_usd": 1.0, "query_unfinished": True}
    done = {"budget_usd": 5.0, "query_unfinished": False}
    charged: list[float] = []

    async def run(agent) -> None:
        async for _ in telemetry.traced_turn(
            frames(),
            {},
            lambda: [(agent, False)],
            "m",
            lambda f: "error" in f,
            None,
            charged.append,
        ):
            pass

    for agent in (roomy, tight, done):
        asyncio.run(run(agent))

    assert charged == [
        pytest.approx(telemetry.UNREPORTED_QUERY_COST_USD),
        pytest.approx(0.3),  # no more than the agent's own budget left
    ]
    assert "query_unfinished" not in roomy


@requires_postgres
def test_the_ops_gauges_show_the_caps_the_months_spend_and_users_near_their_cap(
    db_session, caps, monkeypatch
) -> None:
    from wizard_api import ops_metrics

    caps(user="10", deployment="100", ratio="0.8")
    usage_caps.record_cost(db_session, "ann", 8.5, session=None)  # past 80 %
    usage_caps.record_cost(db_session, "bob", 10.0, session=None)  # at the cap
    usage_caps.record_cost(db_session, "cat", 1.0, session=None)

    stats = usage_caps.usage_stats(db_session)
    assert stats == {
        "deployment_spent": pytest.approx(19.5),
        "users_near": 1.0,  # bob is at the cap, not near it
        "users_reached": 1.0,
    }
    monkeypatch.setattr(ops_metrics._usage, "get", lambda: stats)  # noqa: SLF001
    assert dict((a["scope"], v) for v, a in ops_metrics._usage_caps() if v is not None) == {  # noqa: SLF001
        "session": 5.0,
        "user": 10.0,
        "deployment": 100.0,
    }
    assert list(ops_metrics._deployment_spent()) == [(pytest.approx(19.5), {})]  # noqa: SLF001
    assert list(ops_metrics._users_by_cap()) == [  # noqa: SLF001
        (1.0, {"state": "near"}),
        (1.0, {"state": "reached"}),
    ]


@requires_postgres
def test_moving_sessions_to_a_new_owner_id_moves_their_spend_and_places(db_session, caps) -> None:
    from wizard_api.services import session_service

    for _ in range(2):
        db_session.add(WizardSession(user_id="ann@example.test", output_dir="/tmp/x"))
    db_session.commit()
    usage_caps.claim_session(db_session, "ann@example.test")
    usage_caps.claim_session(db_session, "ann@example.test")
    usage_caps.record_cost(db_session, "ann@example.test", 4.0, session=None, now=NOV)
    usage_caps.claim_session(db_session, "owner-1")
    usage_caps.record_cost(db_session, "owner-1", 1.0, session=None, now=NOV)

    assert session_service.move_owner(db_session, "ann@example.test", "owner-1") == 2

    moved = _total(db_session, "user", "owner-1")
    assert moved.cost_usd == pytest.approx(5.0)
    assert moved.sessions_held == 3
    assert _total(db_session, "user", "ann@example.test") is None


@requires_postgres
def test_a_message_refused_before_its_turn_gives_its_budget_back(
    turn_client, caps, monkeypatch
) -> None:
    async def busy(*args, **kwargs):
        raise agent_service.AgentUserLimitError("busy")

    monkeypatch.setattr(agent_service, "get_or_create_session", busy)
    sid = turn_client.post("/sessions", json={"user_id": "ann", "title": "S"}).json()["id"]

    assert turn_client.post(f"/sessions/{sid}/chat", json={"message": "Hei"}).status_code == 429
    assert "ann" not in usage_caps._RESERVED  # noqa: SLF001


@requires_postgres
def test_a_session_with_all_gates_approved_holds_no_place_until_a_gate_is_reopened(
    client, db_engine, caps
) -> None:
    ids = [
        client.post("/sessions", json={"user_id": "ann", "title": f"S{n}"}).json()["id"]
        for n in range(3)
    ]
    assert client.post("/sessions", json={"user_id": "ann", "title": "S4"}).status_code == 429

    def set_gates(statuses: dict) -> None:
        db = sessionmaker(bind=db_engine)()
        try:
            row = db.get(WizardSession, uuid.UUID(ids[0]))
            row.gate_statuses = {**row.gate_statuses, **statuses}
            db.commit()
        finally:
            db.close()

    set_gates({"gate_4": "approved"})  # Gate 4 alone does not finish it
    assert client.post("/sessions", json={"user_id": "ann", "title": "S4"}).status_code == 429
    set_gates({f"gate_{n}": "approved" for n in range(1, 5)})  # all four: done
    fourth = client.post("/sessions", json={"user_id": "ann", "title": "S4"})
    assert fourth.status_code == 201
    assert client.post("/sessions", json={"user_id": "ann", "title": "S5"}).status_code == 429

    set_gates({"gate_2": "pending"})  # reopened: in progress again, so ann has four and no room
    refused = client.post("/sessions", json={"user_id": "ann", "title": "S6"})
    assert refused.status_code == 429
    assert "in progress" in refused.json()["detail"]["message"]
