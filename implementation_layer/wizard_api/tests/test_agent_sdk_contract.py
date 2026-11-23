"""The tool guard still applies with the pinned claude-agent-sdk.

The agent runs with ``bypassPermissions``; the only thing between it and the
container is the PreToolUse hook in ``agent_tool_guard``. If an SDK (or bundled
CLI) update changed how hooks are registered, what a hook call carries or what
a hook must answer, the guard could stop applying without any test of the guard
itself noticing. These tests pin that contract down against the SDK's own code
and types:

* the installed SDK is the version ``pyproject.toml`` pins;
* the options ``agent_service`` builds register the guard for every tool call;
* a fake CLI on the SDK's ``Transport`` interface receives the SDK's real
  ``initialize`` request and sends real ``hook_callback`` requests, built from
  the SDK's TypedDicts, so the SDK's own dispatch calls the guard and the
  answer that goes back to the CLI is checked against the SDK's output types.

No model is called and no API key is needed. The SDK is imported plainly, not
with ``importorskip``: it is a hard dependency, and a missing SDK must fail here
rather than skip the one test that guards an upgrade.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import tomllib
import typing
from pathlib import Path
from typing import Any, Literal, get_args, get_origin, get_type_hints

import anyio
import claude_agent_sdk
import pytest
from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    PreToolUseHookInput,
    Transport,
)
from claude_agent_sdk import types as sdk_types
from wizard_api.services import agent_service, agent_tool_guard

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"

#: The hook events the wizard registers, and the only ones.
EXPECTED_EVENTS = {"PreToolUse"}


def _literals(annotation: Any) -> set[Any]:
    """The values of a Literal, or of a union of Literals (``HookEvent``)."""
    if get_origin(annotation) is Literal:
        return set(get_args(annotation))
    return {value for arg in get_args(annotation) for value in _literals(arg)}


def _fields(typed_dict: type) -> dict[str, Any]:
    return get_type_hints(typed_dict)


# --- the pin -----------------------------------------------------------------


def test_the_installed_sdk_is_the_pinned_one() -> None:
    deps = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["dependencies"]
    [spec] = [d for d in deps if d.replace(" ", "").startswith("claude-agent-sdk")]
    name, sep, pinned = spec.replace(" ", "").partition("==")
    assert sep == "==", f"claude-agent-sdk must be pinned exactly, not {spec!r}"
    assert claude_agent_sdk.__version__ == pinned, (
        f"installed claude-agent-sdk {claude_agent_sdk.__version__} is not the pinned {pinned}"
    )


# --- the SDK's hook types ----------------------------------------------------


def test_the_sdk_still_declares_the_hook_shapes_the_guard_relies_on() -> None:
    assert EXPECTED_EVENTS <= _literals(sdk_types.HookEvent)

    # What the guard reads from a call.
    hook_input = _fields(PreToolUseHookInput)
    assert hook_input["hook_event_name"] == Literal["PreToolUse"]
    assert hook_input["tool_name"] is str
    assert get_origin(hook_input["tool_input"]) is dict
    assert {"hook_event_name", "tool_name", "tool_input"} <= PreToolUseHookInput.__required_keys__

    # What the guard answers.
    assert "hookSpecificOutput" in _fields(sdk_types.SyncHookJSONOutput)
    output = _fields(sdk_types.PreToolUseHookSpecificOutput)
    assert output["hookEventName"] == Literal["PreToolUse"]
    assert "deny" in _literals(output["permissionDecision"])
    assert "permissionDecisionReason" in output

    # How the SDK calls the guard: (input, tool_use_id, context) -> awaitable.
    params, _ = get_args(sdk_types.HookCallback)
    assert len(params) == 3
    assert len(inspect.signature(agent_tool_guard.ToolGuard.hook).parameters) == 1 + len(params)
    assert inspect.iscoroutinefunction(agent_tool_guard.ToolGuard.hook)

    # The wire request the CLI sends to run a hook.
    assert set(_fields(sdk_types.SDKHookCallbackRequest)) == {
        "subtype",
        "callback_id",
        "input",
        "tool_use_id",
    }


# --- the options agent_service builds ----------------------------------------


@pytest.fixture()
def dirs(tmp_path):
    wizard = tmp_path / "solution_wizard"
    (wizard / "scripts").mkdir(parents=True)
    (wizard / "scripts" / "validate_blueprint.py").write_text("")
    (wizard / "SKILL.md").write_text("")
    session = tmp_path / "sessions" / "alice" / "s1"
    session.mkdir(parents=True)
    other = tmp_path / "sessions" / "bob" / "s2"
    other.mkdir(parents=True)
    return wizard, session, other


def test_the_options_register_the_guard_for_every_tool_call(dirs) -> None:
    wizard, session, _ = dirs
    options = agent_service._build_options(
        wizard, session, guard=agent_tool_guard.ToolGuard(wizard, session)
    )

    assert isinstance(options, ClaudeAgentOptions)
    # bypassPermissions is why the hook has to apply: nothing else asks.
    assert options.permission_mode == "bypassPermissions"
    assert options.can_use_tool is None
    assert set(options.hooks) == EXPECTED_EVENTS
    [matcher] = options.hooks["PreToolUse"]
    assert isinstance(matcher, HookMatcher)
    assert matcher.matcher is None  # every tool, not a subset
    [callback] = matcher.hooks
    assert isinstance(callback.__self__, agent_tool_guard.ToolGuard)
    assert callback.__self__.output == Path(session).resolve()


# --- the guard through the SDK's own control protocol ------------------------


class _FakeCLI(Transport):
    """Plays the CLI's side of the SDK's control protocol, without a CLI."""

    def __init__(self) -> None:
        self._send, self._receive = anyio.create_memory_object_stream[dict[str, Any]](100)
        self.initialize: dict[str, Any] | None = None
        self._answers: dict[str, dict[str, Any]] = {}
        self._answered: dict[str, anyio.Event] = {}
        self._next = 0

    async def connect(self) -> None:
        pass

    def is_ready(self) -> bool:
        return True

    async def end_input(self) -> None:
        pass

    async def close(self) -> None:
        self._send.close()

    async def read_messages(self):
        async for message in self._receive:
            yield message

    async def write(self, data: str) -> None:
        for line in data.splitlines():
            message = json.loads(line)
            if message.get("type") == "control_request":
                request = message["request"]
                assert request["subtype"] == "initialize", request
                self.initialize = request
                await self._send.send(
                    sdk_types.SDKControlResponse(
                        type="control_response",
                        response=sdk_types.ControlResponse(
                            subtype="success", request_id=message["request_id"], response={}
                        ),
                    )
                )
            elif message.get("type") == "control_response":
                answer = message["response"]
                self._answers[answer["request_id"]] = answer
                self._answered[answer["request_id"]].set()

    async def run_hook(self, callback_id: str, hook_input: dict[str, Any]) -> dict[str, Any]:
        """Ask the SDK to run a hook, as the CLI does before a tool call."""
        self._next += 1
        request_id = f"cli_req_{self._next}"
        self._answered[request_id] = anyio.Event()
        await self._send.send(
            sdk_types.SDKControlRequest(
                type="control_request",
                request_id=request_id,
                request=sdk_types.SDKHookCallbackRequest(
                    subtype="hook_callback",
                    callback_id=callback_id,
                    input=hook_input,
                    tool_use_id=hook_input["tool_use_id"],
                ),
            )
        )
        with anyio.fail_after(10):
            await self._answered[request_id].wait()
        answer = self._answers[request_id]
        assert answer["subtype"] == "success", answer
        return answer["response"]


def _pre_tool_use(tool_name: str, tool_input: dict[str, Any], cwd: Path, n: int) -> dict:
    """A PreToolUse hook input with every key the pinned SDK declares as required.

    The keys come from ``PreToolUseHookInput`` itself, so a field the SDK adds
    as required is filled in here, and a field the guard relies on that the SDK
    renames or drops fails the check below instead of passing unnoticed.
    """
    known = {
        "session_id": "sdk-session",
        "transcript_path": str(cwd / "transcript.jsonl"),
        "cwd": str(cwd),
        "permission_mode": "bypassPermissions",
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_use_id": f"toolu_{n}",
    }
    declared = _fields(PreToolUseHookInput)
    assert set(known) <= set(declared), set(known) - set(declared)
    values = dict(known)
    for key in PreToolUseHookInput.__required_keys__ - set(known):
        annotation = declared[key]
        origin = get_origin(annotation) or annotation
        if origin is Literal:
            values[key] = get_args(annotation)[0]
        elif origin in (dict, typing.Dict):  # noqa: UP006
            values[key] = {}
        elif origin in (list, typing.List):  # noqa: UP006
            values[key] = []
        else:
            values[key] = origin() if isinstance(origin, type) else None
    assert PreToolUseHookInput.__required_keys__ <= set(values)
    return PreToolUseHookInput(**values)


def _assert_denied(answer: dict[str, Any]) -> str:
    assert set(answer) <= set(_fields(sdk_types.SyncHookJSONOutput)), answer
    specific = answer["hookSpecificOutput"]
    output = _fields(sdk_types.PreToolUseHookSpecificOutput)
    assert set(specific) <= set(output), specific
    assert specific["hookEventName"] in _literals(output["hookEventName"])
    assert specific["permissionDecision"] == "deny"
    assert specific["permissionDecisionReason"]
    return specific["permissionDecisionReason"]


def test_the_sdk_runs_the_guard_on_each_tool_call(dirs) -> None:
    wizard, session, other = dirs
    options = agent_service._build_options(
        wizard, session, guard=agent_tool_guard.ToolGuard(wizard, session)
    )
    cli = _FakeCLI()

    async def go() -> dict[str, Any]:
        client = ClaudeSDKClient(options=options, transport=cli)
        await client.connect()
        try:
            hooks = cli.initialize["hooks"]
            assert set(hooks) == EXPECTED_EVENTS
            [matcher] = hooks["PreToolUse"]
            assert matcher["matcher"] is None
            [callback_id] = matcher["hookCallbackIds"]

            calls = {
                "disallowed tool": ("WebFetch", {"url": "https://example.com", "prompt": "x"}),
                "write outside the session": (
                    "Write",
                    {"file_path": str(other / "notes.json"), "content": "{}"},
                ),
                "read outside the session": ("Read", {"file_path": "/etc/passwd"}),
                "shell operator": (
                    "Bash",
                    {
                        "command": "python scripts/validate_blueprint.py --blueprint "
                        f"{session / 'use_case.blueprint.json'}; env"
                    },
                ),
                "allowed read": ("Read", {"file_path": str(wizard / "SKILL.md")}),
                "allowed write": (
                    "Write",
                    {"file_path": str(session / "use_case.blueprint.json"), "content": "{}"},
                ),
                "allowed script": (
                    "Bash",
                    {
                        "command": "python scripts/validate_blueprint.py --blueprint "
                        f"{session / 'use_case.blueprint.json'}"
                    },
                ),
            }
            answers = {}
            for n, (label, (tool, tool_input)) in enumerate(calls.items()):
                hook_input = _pre_tool_use(tool, tool_input, wizard, n)
                answers[label] = await cli.run_hook(callback_id, hook_input)
            return answers
        finally:
            await client.disconnect()

    answers = asyncio.run(go())

    assert "WebFetch" in _assert_denied(answers["disallowed tool"])
    assert "session directory" in _assert_denied(answers["write outside the session"])
    assert "session directory" in _assert_denied(answers["read outside the session"])
    assert "shell operators" in _assert_denied(answers["shell operator"])
    # An allowed call gets no decision at all, so bypassPermissions lets it run.
    assert answers["allowed read"] == {}
    assert answers["allowed write"] == {}
    assert answers["allowed script"] == {}
