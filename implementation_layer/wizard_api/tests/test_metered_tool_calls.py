"""Tool calls that reach a model or the web fall under the turn and per-user limits.

``WIZARD_AGENT_MAX_TURNS`` counts the agent's own model calls only. A wizard
script that calls a model (generate_schema.py), web search and fetch, and the
tools of an MCP server other than the wizard's own are *metered*: the tool
guard counts each one it lets run, per chat message and per user in a sliding
hour, and refuses one over either limit with words the agent can pass on.
Every decision is one log line and one count, without the call's input or the
user's id.
"""

import asyncio
import contextlib
import dataclasses
import io
import logging

import pytest
from wizard_api import config, ops_metrics, telemetry
from wizard_api.services import agent_service, agent_tool_guard

GUARD_LOGGER = "wizard_api.services.agent_tool_guard"


@pytest.fixture(autouse=True)
def _fresh_counts(monkeypatch):
    monkeypatch.setattr(agent_tool_guard, "_USER_CALLS", {})
    monkeypatch.setenv("WIZARD_MAX_METERED_CALLS_PER_TURN", "3")
    monkeypatch.setenv("WIZARD_MAX_METERED_CALLS_PER_USER_PER_HOUR", "100")


@pytest.fixture()
def dirs(tmp_path):
    wizard = tmp_path / "solution_wizard"
    (wizard / "scripts").mkdir(parents=True)
    for name in ("validate_blueprint.py", "generate_schema.py", "scaffold_poc.py"):
        (wizard / "scripts" / name).write_text("")
    (wizard / "SKILL.md").write_text("")
    session = tmp_path / "sessions" / "alice" / "s1"
    (session / "poc" / "prompts").mkdir(parents=True)
    return wizard, session


def _guard(dirs, user_id="alice", session=None):
    wizard, own = dirs
    return agent_tool_guard.ToolGuard(wizard, session or own, user_id=user_id)


def _schema_command(session, extra=""):
    return (
        f"python scripts/generate_schema.py --requirements "
        f"{session}/poc/prompts/extraction_requirements.md --output-dir {session}/poc{extra}"
    )


def _schema(guard, now=0.0):
    command = _schema_command(guard.output)
    return guard.decide("Bash", {"command": command}, now=now)


def _allow_everything(guard, monkeypatch):
    """What the next item does for web search, fetch and MCP: the rules let them run."""
    monkeypatch.setattr(guard, "check", lambda tool, tool_input: None)


# --- config --------------------------------------------------------------------------


@pytest.mark.parametrize("raw, expected", [("", 10), ("4", 4), ("0", 10), ("-2", 10), ("many", 10)])
def test_the_per_turn_cap_is_a_positive_number_like_the_agents_turn_cap(
    monkeypatch, raw, expected
) -> None:
    monkeypatch.setenv("WIZARD_MAX_METERED_CALLS_PER_TURN", raw)

    assert config.max_metered_calls_per_turn() == expected


@pytest.mark.parametrize("raw, expected", [("", 60), ("30", 30), ("0", 0), ("-1", 60), ("x", 60)])
def test_the_hourly_user_limit_is_off_only_at_zero_like_the_chat_rate(
    monkeypatch, raw, expected
) -> None:
    monkeypatch.setenv("WIZARD_MAX_METERED_CALLS_PER_USER_PER_HOUR", raw)

    assert config.max_metered_calls_per_user_per_hour() == expected


def test_the_defaults_hold_when_nothing_is_set(monkeypatch) -> None:
    monkeypatch.delenv("WIZARD_MAX_METERED_CALLS_PER_TURN", raising=False)
    monkeypatch.delenv("WIZARD_MAX_METERED_CALLS_PER_USER_PER_HOUR", raising=False)

    assert config.max_metered_calls_per_turn() == 10
    assert config.max_metered_calls_per_user_per_hour() == 60


# --- what is metered -----------------------------------------------------------------


def test_a_script_that_calls_a_model_is_metered_however_it_is_written(dirs) -> None:
    guard = _guard(dirs)
    s = guard.output
    continued = (
        f"python scripts/generate_schema.py \\\n"
        f"    --requirements {s}/poc/prompts/extraction_requirements.md \\\n"
        f"    --output-dir {s}/poc"
    )
    quoted = (
        f'python3 scripts/generate_"schema".py --requirements '
        f"{s}/poc/prompts/extraction_requirements.md --output-dir {s}/poc"
    )
    for command in (_schema_command(s), continued, quoted):
        decision = guard.decide("Bash", {"command": command})
        assert decision.reason is None, command
        assert (decision.kind, decision.script) == ("model_script", "generate_schema.py")
    assert guard.turn_calls == 3


@pytest.mark.parametrize(
    "tool, kind",
    [
        ("WebSearch", "web"),
        ("WebFetch", "web"),
        ("mcp__context7__get-library-docs", "mcp"),
        ("mcp__markitdown__convert_to_markdown", "mcp"),
        ("mcp__wizard__reopen_gate", "wizard"),
        ("mcp__wizard__offer_language", "wizard"),
        ("Read", "read"),
        ("Write", "write"),
        ("TodoWrite", "internal"),
        ("Task", "other"),
    ],
)
def test_tools_are_metered_by_name(tool, kind) -> None:
    assert agent_tool_guard.call_kind(tool, {})[0] == kind
    assert (kind in agent_tool_guard.METERED_KINDS) == (kind in ("web", "mcp"))


def test_the_other_wizard_scripts_are_not_metered(dirs) -> None:
    guard = _guard(dirs)
    command = f"python scripts/validate_blueprint.py --blueprint {guard.output}/bp.json"

    decision = guard.decide("Bash", {"command": command})

    assert (decision.kind, decision.script, decision.code) == (
        "command",
        "validate_blueprint.py",
        "ok",
    )
    assert guard.turn_calls == 0


# --- per turn ------------------------------------------------------------------------


def test_a_turn_makes_at_most_the_per_turn_number_and_a_new_turn_starts_from_zero(dirs) -> None:
    guard = _guard(dirs)

    assert [_schema(guard).code for _ in range(4)] == ["ok", "ok", "ok", "turn_limit"]
    guard.start_turn()
    assert _schema(guard).code == "ok"
    assert guard.turn_calls == 1


def test_calls_that_are_not_metered_go_on_at_the_limit_and_use_nothing(dirs) -> None:
    guard = _guard(dirs)
    for _ in range(3):
        _schema(guard)
    s = guard.output

    for tool, tool_input in (
        ("Read", {"file_path": "SKILL.md"}),
        ("Write", {"file_path": str(s / "use_case.blueprint.json")}),
        ("Bash", {"command": f"python scripts/validate_blueprint.py --blueprint {s}/bp.json"}),
        ("mcp__wizard__reopen_gate", {"gate": 2, "reason": "x"}),
        ("TodoWrite", {"todos": []}),
    ):
        assert guard.decide(tool, tool_input).code == "ok", tool
    assert guard.turn_calls == 3
    assert _schema(guard).code == "turn_limit"


def test_a_metered_call_the_rules_refuse_uses_up_nothing(dirs) -> None:
    guard = _guard(dirs)
    outside = _schema_command(guard.output, " --base-url https://example.com/v1")

    decision = guard.decide("Bash", {"command": outside})

    assert (decision.kind, decision.code) == ("model_script", "command_not_allowed")
    assert guard.turn_calls == 0
    assert agent_tool_guard._USER_CALLS == {}


def test_web_and_outside_mcp_tools_are_refused_today_and_not_counted(dirs) -> None:
    guard = _guard(dirs)

    for tool in ("WebSearch", "WebFetch", "mcp__context7__get-library-docs"):
        decision = guard.decide(tool, {"query": "x"})
        assert (decision.code, decision.reason is not None) == ("tool_not_available", True)
    assert guard.turn_calls == 0


def test_a_future_mcp_or_web_tool_is_counted_the_moment_it_is_allowed(dirs, monkeypatch) -> None:
    guard = _guard(dirs)
    _allow_everything(guard, monkeypatch)

    codes = [
        guard.decide("mcp__context7__get-library-docs", {"libraryID": "/x/y"}).code,
        guard.decide("WebFetch", {"url": "https://example.com"}).code,
        guard.decide("mcp__docling__convert_document", {"source": "a.pdf"}).code,
        guard.decide("WebSearch", {"query": "x"}).code,
    ]

    assert codes == ["ok", "ok", "ok", "turn_limit"]
    # The wizard's own tools are never metered, at the limit or not.
    assert guard.decide("mcp__wizard__offer_language", {"language": "fi"}).code == "ok"


# --- per user ------------------------------------------------------------------------


def test_one_users_calls_count_together_across_turns_and_sessions(dirs, monkeypatch) -> None:
    monkeypatch.setenv("WIZARD_MAX_METERED_CALLS_PER_USER_PER_HOUR", "3")
    wizard, session = dirs
    second = session.parent / "s2"
    (second / "poc").mkdir(parents=True)
    first = _guard(dirs)
    other_session = _guard(dirs, session=second)
    bob = _guard(dirs, user_id="bob")

    assert _schema(first, now=0).code == "ok"
    first.start_turn()
    assert _schema(first, now=10).code == "ok"
    assert _schema(other_session, now=20).code == "ok"
    refused = _schema(other_session, now=30)
    assert refused.code == "user_limit"
    assert _schema(first, now=30).code == "user_limit"
    # Another user has their own hour.
    assert _schema(bob, now=30).code == "ok"
    # The first call leaves the window an hour after it was made.
    assert _schema(first, now=3600).code == "ok"
    assert _schema(first, now=3601).code == "user_limit"


def test_the_hourly_limit_can_be_turned_off(dirs, monkeypatch) -> None:
    monkeypatch.setenv("WIZARD_MAX_METERED_CALLS_PER_USER_PER_HOUR", "0")
    monkeypatch.setenv("WIZARD_MAX_METERED_CALLS_PER_TURN", "50")
    guard = _guard(dirs)

    assert all(_schema(guard, now=i).code == "ok" for i in range(20))
    assert agent_tool_guard._USER_CALLS == {}


def test_a_user_whose_hour_is_over_is_forgotten(dirs) -> None:
    alice, bob = _guard(dirs), _guard(dirs, user_id="bob")
    _schema(alice, now=0)
    _schema(alice, now=10)
    assert list(agent_tool_guard._USER_CALLS) == ["alice"]

    _schema(bob, now=3605)  # any metered call sweeps the table
    assert list(agent_tool_guard._USER_CALLS["alice"]) == [10]  # the one at 0 left

    _schema(bob, now=3611)

    assert list(agent_tool_guard._USER_CALLS) == ["bob"]
    assert list(agent_tool_guard._USER_CALLS["bob"]) == [3605, 3611]


def test_an_agent_without_an_owner_has_the_per_turn_cap_only(dirs, monkeypatch) -> None:
    monkeypatch.setenv("WIZARD_MAX_METERED_CALLS_PER_USER_PER_HOUR", "1")
    guard = _guard(dirs, user_id=None)

    assert [_schema(guard).code for _ in range(4)] == ["ok", "ok", "ok", "turn_limit"]


# --- what the agent is told ----------------------------------------------------------


def test_the_refusal_says_which_limit_and_what_to_do_in_the_sdk_format(dirs) -> None:
    guard = _guard(dirs)
    guard.turn_calls = 3
    command = _schema_command(guard.output)

    denied = asyncio.run(
        guard.hook({"tool_name": "Bash", "tool_input": {"command": command}}, None, None)
    )

    out = denied["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    reason = out["permissionDecisionReason"]
    assert "3 calls that use a model or the web" in reason
    assert "one message" in reason
    assert "Carry on without it" in reason
    assert "tell the user in plain words" in reason


def test_the_hourly_refusal_says_when_to_try_again(dirs, monkeypatch) -> None:
    monkeypatch.setenv("WIZARD_MAX_METERED_CALLS_PER_USER_PER_HOUR", "1")
    guard = _guard(dirs)
    _schema(guard, now=0)

    refused = _schema(guard, now=30)

    assert "1 calls that use a model or the web" in refused.reason
    assert "in the last hour" in refused.reason
    assert "try again in about 60 minutes" in refused.reason
    assert "alice" not in refused.reason


# --- the log line and the count ------------------------------------------------------


def test_each_decision_is_one_log_line_without_the_command_paths_or_user(
    dirs, caplog, monkeypatch
) -> None:
    caplog.set_level(logging.INFO, logger=GUARD_LOGGER)
    guard = _guard(dirs)
    command = _schema_command(guard.output, " --model azure/gpt-6-luna")

    asyncio.run(guard.hook({"tool_name": "Bash", "tool_input": {"command": command}}, None, None))

    [record] = [r for r in caplog.records if r.name == GUARD_LOGGER]
    message = record.getMessage()
    assert record.levelno == logging.INFO
    assert message == (
        "tool call tool=Bash kind=model_script script=generate_schema.py decision=allowed reason=ok"
    )
    for leaked in (str(guard.output), "--requirements", "azure/gpt-6-luna", "alice", "sessions"):
        assert leaked not in message


def test_a_refusal_at_a_limit_is_a_warning_without_ids(dirs, caplog) -> None:
    caplog.set_level(logging.INFO, logger=GUARD_LOGGER)
    guard = _guard(dirs)
    guard.turn_calls = 3

    asyncio.run(
        guard.hook(
            {"tool_name": "Bash", "tool_input": {"command": _schema_command(guard.output)}},
            None,
            None,
        )
    )

    [record] = [r for r in caplog.records if r.name == GUARD_LOGGER]
    assert record.levelno == logging.WARNING
    assert record.getMessage().endswith("decision=denied reason=turn_limit")
    assert "alice" not in record.getMessage()
    assert str(guard.output) not in record.getMessage()


def test_a_refusal_by_the_rules_and_a_url_stay_out_of_the_line(dirs, caplog) -> None:
    caplog.set_level(logging.INFO, logger=GUARD_LOGGER)
    guard = _guard(dirs)

    asyncio.run(
        guard.hook(
            {"tool_name": "WebFetch", "tool_input": {"url": "https://example.com/?q=secret"}},
            None,
            None,
        )
    )
    asyncio.run(
        guard.hook({"tool_name": "Read", "tool_input": {"file_path": "/etc/passwd"}}, None, None)
    )

    messages = [r.getMessage() for r in caplog.records if r.name == GUARD_LOGGER]
    assert messages == [
        "tool call tool=WebFetch kind=web script=- decision=denied reason=tool_not_available",
        "tool call tool=Read kind=read script=- decision=denied reason=path_not_allowed",
    ]


def test_a_tool_name_that_is_not_a_plain_name_is_logged_as_other(dirs, caplog) -> None:
    caplog.set_level(logging.INFO, logger=GUARD_LOGGER)
    guard = _guard(dirs)

    asyncio.run(guard.hook({"tool_name": "x /etc/passwd alice@example.test"}, None, None))

    [message] = [r.getMessage() for r in caplog.records if r.name == GUARD_LOGGER]
    assert message.startswith("tool call tool=other kind=other ")
    assert "passwd" not in message and "example.test" not in message


def test_a_call_the_guard_cannot_decide_is_logged_once(dirs, caplog, monkeypatch) -> None:
    caplog.set_level(logging.INFO, logger=GUARD_LOGGER)
    guard = _guard(dirs)

    def broken(*_args):
        raise TypeError("unexpected input")

    monkeypatch.setattr(guard, "check", broken)
    denied = asyncio.run(guard.hook({"tool_name": "Read", "tool_input": {}}, None, None))

    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    [record] = [r for r in caplog.records if r.name == GUARD_LOGGER]
    assert record.levelno == logging.ERROR
    assert record.getMessage().endswith("decision=denied reason=guard_error")


def test_each_decision_is_counted_by_kind_decision_and_reason(dirs, monkeypatch) -> None:
    added: list[tuple[int, dict]] = []

    class _Counter:
        def add(self, amount, attributes):
            added.append((amount, attributes))

    monkeypatch.setattr(ops_metrics, "tool_calls", _Counter())
    guard = _guard(dirs)
    guard.turn_calls = 3
    hook_input = {"tool_name": "Bash", "tool_input": {"command": _schema_command(guard.output)}}

    asyncio.run(guard.hook(hook_input, None, None))
    asyncio.run(
        guard.hook({"tool_name": "Read", "tool_input": {"file_path": "SKILL.md"}}, None, None)
    )

    assert added == [
        (1, {"kind": "model_script", "decision": "denied", "reason": "turn_limit"}),
        (1, {"kind": "read", "decision": "allowed", "reason": "ok"}),
    ]


class _Kept(logging.Handler):
    """Stands for the collector's handler on the root, at its default WARNING."""

    def __init__(self, level=logging.WARNING) -> None:
        super().__init__(level)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@contextlib.contextmanager
def _logging_as_in_the_pod():
    """Logging as uvicorn leaves it: nothing on the API's loggers or the root.

    Set back in the test's own body, so pytest's handlers on the root are as it
    left them when it takes them away.
    """
    tree, root = logging.getLogger(telemetry.API_LOGGER), logging.getLogger()
    kept = (tree.level, tree.handlers[:], root.level, root.handlers[:])
    tree.handlers, root.handlers = [], []
    tree.setLevel(logging.NOTSET)
    root.setLevel(logging.WARNING)
    try:
        yield tree, root
    finally:
        tree.handlers, root.handlers = kept[1], kept[3]
        tree.setLevel(kept[0])
        root.setLevel(kept[2])


def _hook(guard, tool, tool_input):
    return asyncio.run(guard.hook({"tool_name": tool, "tool_input": tool_input}, None, None))


def test_with_the_default_configuration_each_decision_is_printed_at_info(dirs, monkeypatch) -> None:
    monkeypatch.delenv("WIZARD_LOG_LEVEL", raising=False)
    printed = io.StringIO()
    guard = _guard(dirs)
    with _logging_as_in_the_pod() as (_tree, root):
        collector = _Kept()
        root.addHandler(collector)
        telemetry.configure_logging(stream=printed)

        _hook(guard, "Read", {"file_path": "SKILL.md"})
        guard.turn_calls = 3
        _hook(guard, "Bash", {"command": _schema_command(guard.output)})

    lines = printed.getvalue().splitlines()
    assert len(lines) == 2
    assert lines[0].endswith(
        "INFO wizard_api.services.agent_tool_guard: tool call tool=Read kind=read "
        "script=- decision=allowed reason=ok"
    )
    assert lines[1].endswith("decision=denied reason=turn_limit")
    assert " WARNING " in lines[1]
    # The collector's handler keeps its own level: the warning reaches it once,
    # the INFO line not at all.
    [warning] = collector.records
    assert warning.levelno == logging.WARNING
    assert warning.getMessage().endswith("decision=denied reason=turn_limit")


def test_wizard_log_level_sets_what_is_printed(dirs, monkeypatch) -> None:
    printed = io.StringIO()
    guard = _guard(dirs)
    monkeypatch.setenv("WIZARD_LOG_LEVEL", "warning")
    with _logging_as_in_the_pod():
        telemetry.configure_logging(stream=printed)
        _hook(guard, "Read", {"file_path": "SKILL.md"})

    assert printed.getvalue() == ""


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("", logging.INFO),
        ("debug", logging.DEBUG),
        ("ERROR", logging.ERROR),
        ("loud", logging.INFO),
    ],
)
def test_wizard_log_level_reads_a_level_name(monkeypatch, raw, expected) -> None:
    monkeypatch.setenv("WIZARD_LOG_LEVEL", raw)

    assert telemetry.log_level() == expected


def test_logging_is_configured_once_and_never_beside_a_printing_handler(monkeypatch) -> None:
    monkeypatch.delenv("WIZARD_LOG_LEVEL", raising=False)
    with _logging_as_in_the_pod() as (tree, root):
        telemetry.configure_logging(stream=io.StringIO())
        telemetry.configure_logging(stream=io.StringIO())
        assert len(tree.handlers) == 1

        tree.handlers = []
        root.addHandler(logging.StreamHandler(io.StringIO()))  # e.g. a basicConfig
        telemetry.configure_logging(stream=io.StringIO())
        assert tree.handlers == []
        assert tree.level == logging.INFO


def test_an_otel_log_level_below_the_pods_lets_those_lines_through(monkeypatch) -> None:
    monkeypatch.setenv("WIZARD_LOG_LEVEL", "WARNING")
    with _logging_as_in_the_pod() as (tree, _root):
        printed = io.StringIO()
        telemetry.configure_logging(stream=printed)
        telemetry._let_through(logging.INFO)  # what WIZARD_OTEL_LOG_LEVEL=INFO does

        assert tree.isEnabledFor(logging.INFO)
        logging.getLogger(GUARD_LOGGER).info("tool call tool=Read")
        assert printed.getvalue() == ""  # the pod still prints warnings only


def test_the_limit_refusals_are_primed_for_alerting() -> None:
    primed = ops_metrics._PRIMED["tool_calls"]

    for kind in agent_tool_guard.METERED_KINDS:
        for reason in ("turn_limit", "user_limit"):
            assert {"kind": kind, "decision": "denied", "reason": reason} in primed


# --- wiring: the owner and the turn reach the guard -----------------------------------

needs_sdk = pytest.mark.skipif(
    not agent_service._SDK_AVAILABLE, reason="claude-agent-sdk not installed"
)


def _result():
    from claude_agent_sdk import ResultMessage

    return ResultMessage(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=False,
        num_turns=1,
        session_id="11111111-1111-4111-8111-111111111111",
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
    """Replies "Done." to every query; ``on_query`` runs as the query is sent."""

    def __init__(self, on_query=None) -> None:
        self.on_query = on_query
        self.queries: list[str] = []

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def query(self, prompt, session_id="default") -> None:
        self.queries.append(prompt)
        if self.on_query is not None:
            self.on_query()

    async def receive_response(self):
        yield _text("Done.")
        yield _result()


@needs_sdk
def test_the_options_use_the_guard_they_are_given_and_none_are_built_without_one(dirs) -> None:
    wizard, session = dirs
    guard = agent_tool_guard.ToolGuard(wizard, session, user_id="alice")

    given = agent_service._build_options(wizard, session, guard=guard)

    assert given.hooks["PreToolUse"][0].hooks[0].__self__ is guard
    with pytest.raises(TypeError):
        agent_service._build_options(wizard, session)  # no guard that skips the owner


@pytest.fixture()
def starting(dirs, monkeypatch):
    """Agent starts without the SDK's client; the options each start is built with."""
    wizard, _ = dirs
    built: list[dict] = []
    monkeypatch.setenv("WIZARD_DIR", str(wizard))
    monkeypatch.setattr(agent_service, "AGENT_SESSIONS", {})
    monkeypatch.setattr(agent_service, "_START_LOCKS", {})
    monkeypatch.setattr(agent_service, "_STARTING", {})
    monkeypatch.setattr(
        agent_service, "_build_options", lambda *args, **kwargs: built.append(kwargs)
    )
    monkeypatch.setattr(agent_service, "ClaudeSDKClient", lambda options=None: _Client())
    return built


@needs_sdk
def test_a_started_agent_has_a_guard_that_knows_its_owner(dirs, starting, caplog) -> None:
    _, session = dirs

    agent = asyncio.run(
        agent_service.get_or_create_session("sid", str(session), "en", user_id="o_alice")
    )

    guard = agent["tool_guard"]
    assert isinstance(guard, agent_tool_guard.ToolGuard)
    assert guard.user_id == "o_alice"
    assert guard.output == session.resolve()
    assert [kwargs["guard"] for kwargs in starting] == [guard]
    assert "without an owner" not in caplog.text


@needs_sdk
def test_an_agent_started_without_an_owner_is_a_warning(dirs, starting, caplog) -> None:
    _, session = dirs

    agent = asyncio.run(agent_service.get_or_create_session("sid", str(session), "en"))

    assert agent["tool_guard"].user_id is None
    [record] = [r for r in caplog.records if "without an owner" in r.getMessage()]
    assert record.levelno == logging.WARNING


@needs_sdk
def test_a_chat_message_starts_the_count_before_the_agent_works(dirs) -> None:
    guard = _guard(dirs)
    guard.turn_calls = 3  # the previous message used up its calls
    during: list[str] = []
    client = _Client(on_query=lambda: during.append(_schema(guard).code))
    agent = {"client": client, "lock": asyncio.Lock(), "last_active": 0.0, "tool_guard": guard}

    async def turn() -> list[str]:
        return [f async for f in agent_service.stream_turn_for(agent, "next", [])]

    frames = asyncio.run(turn())

    assert during == ["ok"]
    assert guard.turn_calls == 1
    assert frames[-1] == agent_service.sse({"done": True})
