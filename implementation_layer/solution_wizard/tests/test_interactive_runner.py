"""The interactive runner starts the agent with the tool guard on every call.

The agent runs with ``bypassPermissions``; the only thing between it and the
user's machine is the PreToolUse hook (``agent_tool_guard``). A hook runs
before the CLI's own approval, so unlike ``can_use_tool`` it also sees the
calls the CLI approves by itself (``ls``, ``git status``, reading a file).

* the options the runner builds register the guard for every tool call, load
  no user settings and no MCP servers;
* a fake CLI on the SDK's ``Transport`` interface receives the SDK's real
  ``initialize`` request and sends real ``hook_callback`` requests, built from
  the SDK's TypedDicts, so the SDK's own dispatch calls the guard;
* the agent's environment holds the system basics and the .env file's names;
* ``test_a_live_session_sends_every_tool_call_through_the_guard`` (marked
  ``llm``) starts the real CLI, so an SDK or CLI upgrade that changes which
  calls reach the hook fails a test.
"""

from __future__ import annotations

import asyncio
import inspect
import io
import json
import os
import sys
import typing
from pathlib import Path
from typing import Any, Literal, get_args, get_origin, get_type_hints

import pytest

claude_agent_sdk = pytest.importorskip("claude_agent_sdk")
pytest.importorskip("dotenv")
import anyio  # noqa: E402
from claude_agent_sdk import (  # noqa: E402
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    PreToolUseHookInput,
    Transport,
)
from claude_agent_sdk import types as sdk_types  # noqa: E402

WIZARD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WIZARD))

import agent_tool_guard  # noqa: E402
import run_wizard_interactive as runner  # noqa: E402

EXPECTED_EVENTS = {"PreToolUse"}


def _literals(annotation: Any) -> set[Any]:
    """The values of a Literal, or of a union of Literals (``HookEvent``)."""
    if get_origin(annotation) is Literal:
        return set(get_args(annotation))
    return {value for arg in get_args(annotation) for value in _literals(arg)}


def _fields(typed_dict: type) -> dict[str, Any]:
    return get_type_hints(typed_dict)


@pytest.fixture()
def output(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    return out


def _options(output: Path) -> ClaudeAgentOptions:
    return runner.build_session_options(output, {"PATH": os.environ.get("PATH", "")}, "m")


# --- the SDK's hook types ----------------------------------------------------


def test_the_sdk_still_declares_the_hook_shapes_the_guard_relies_on() -> None:
    assert EXPECTED_EVENTS <= _literals(sdk_types.HookEvent)
    hook_input = _fields(PreToolUseHookInput)
    assert hook_input["tool_name"] is str
    assert {"hook_event_name", "tool_name", "tool_input"} <= PreToolUseHookInput.__required_keys__
    output = _fields(sdk_types.PreToolUseHookSpecificOutput)
    assert "deny" in _literals(output["permissionDecision"])
    assert "permissionDecisionReason" in output
    params, _ = get_args(sdk_types.HookCallback)
    assert len(inspect.signature(agent_tool_guard.ToolGuard.hook).parameters) == 1 + len(params)
    assert inspect.iscoroutinefunction(agent_tool_guard.ToolGuard.hook)


# --- the options the runner builds -------------------------------------------


def test_the_options_register_the_guard_for_every_tool_call(output) -> None:
    options = _options(output)

    assert options.permission_mode == "bypassPermissions"
    assert options.can_use_tool is None
    assert set(options.hooks) == EXPECTED_EVENTS
    [matcher] = options.hooks["PreToolUse"]
    assert isinstance(matcher, HookMatcher)
    assert matcher.matcher is None  # every tool, not a subset
    [callback] = matcher.hooks
    assert isinstance(callback.__self__, agent_tool_guard.ToolGuard)
    assert callback.__self__.output == output.resolve()
    assert callback.__self__.cwd == WIZARD


def test_the_session_loads_no_user_settings_and_no_mcp_servers(output) -> None:
    options = _options(output)

    assert options.setting_sources == []
    assert options.mcp_servers in ({}, None)
    assert options.strict_mcp_config is True
    assert "strict-mcp-config" not in options.extra_args  # the documented field instead
    assert set(options.tools) == set(runner.TOOLS)
    assert options.max_budget_usd is None  # no limit unless --max-budget-usd is given


def _cli_command(options: ClaudeAgentOptions, monkeypatch) -> list[str]:
    """The command line the SDK starts the CLI with, captured without starting it."""
    seen: list[str] = []

    async def open_process(command, *_args, **_kwargs):
        seen.extend(command)
        raise _CLIStartError

    monkeypatch.setattr(anyio, "open_process", open_process)

    async def go() -> None:
        try:
            await ClaudeSDKClient(options=options).connect()
        except Exception:  # noqa: BLE001 - the SDK wraps the stop above in its own error
            pass

    asyncio.run(go())
    assert seen, "the SDK did not reach the point where it starts the CLI"
    return seen


def test_the_cli_is_started_with_strict_mcp_config_and_the_budget(output, tmp_path, monkeypatch):
    cli = tmp_path / "claude"
    cli.write_text("")
    env = {"PATH": os.environ.get("PATH", "")}
    options = runner.build_session_options(output, env, "m", cli_path=str(cli))
    command = _cli_command(options, monkeypatch)
    assert command.count("--strict-mcp-config") == 1
    assert "--max-budget-usd" not in command

    options = runner.build_session_options(output, env, "m", max_budget_usd=2.5, cli_path=str(cli))
    command = _cli_command(options, monkeypatch)
    assert command[command.index("--max-budget-usd") + 1] == "2.5"


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "five"])
def test_the_budget_must_be_a_positive_amount(monkeypatch, value) -> None:
    monkeypatch.setattr(sys, "argv", ["run_wizard_interactive.py", "--max-budget-usd", value])
    with pytest.raises(SystemExit):
        runner.parse_args()


@pytest.mark.parametrize(
    ("given", "on_the_command_line", "shown"),
    [("2.5", "2.5", "$2.50"), ("1000000", "1000000.0", "$1,000,000.00"), (None, None, None)],
)
def test_the_budget_option_reaches_the_cli_through_main(
    tmp_path, monkeypatch, capsys, shell_env, given, on_the_command_line, shown
) -> None:
    """main -> run_interactive -> build_session_options -> the CLI's --max-budget-usd."""
    _temp_is_an_ordinary_folder(monkeypatch, tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "CLAUDE_CODE_USE_FOUNDRY=1\nANTHROPIC_FOUNDRY_API_KEY=k\nANTHROPIC_FOUNDRY_RESOURCE=r\n"
    )
    # The .env file is the only source: load_dotenv keeps a variable already set, and
    # CI sets the Foundry ones to "" where it has no secret for them.
    for name in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", *_FOUNDRY_NAMES):
        os.environ.pop(name, None)
    cli = tmp_path / "claude"
    cli.write_text("")
    build = runner.build_session_options
    monkeypatch.setattr(
        runner, "build_session_options", lambda *a, **k: build(*a, cli_path=str(cli), **k)
    )
    command: list[str] = []

    async def open_process(cmd, *_args, **_kwargs):
        command.extend(cmd)
        raise _CLIStartError

    monkeypatch.setattr(anyio, "open_process", open_process)
    argv = ["run_wizard_interactive.py", "--output-dir", str(tmp_path / "out")]
    argv += ["--env-file", str(env_file)]
    if given is not None:
        argv += ["--max-budget-usd", given]
    monkeypatch.setattr(sys, "argv", argv)

    with pytest.raises(SystemExit):
        runner.main()

    assert command, "main did not reach the point where the SDK starts the CLI"
    printed = capsys.readouterr().out
    if given is None:
        assert "--max-budget-usd" not in command
        assert "Budget:" not in printed
    else:
        assert command[command.index("--max-budget-usd") + 1] == on_the_command_line
        assert f"Budget: {shown} for the whole session" in printed
        assert "a little over" in printed
        assert "e+" not in printed


@pytest.mark.parametrize(
    ("amount", "shown"),
    [(2.5, "$2.50"), (5, "$5.00"), (1e6, "$1,000,000.00"), (0.125, "$0.125"), (0.5, "$0.50")],
)
def test_a_budget_is_shown_as_money(amount, shown) -> None:
    assert runner._money(amount) == shown


class _OneResult:
    """A client whose turn ends with one result message."""

    def __init__(self, message) -> None:
        self.message = message

    async def receive_response(self):
        yield self.message


def test_a_session_stopped_by_its_budget_says_so(capsys) -> None:
    from claude_agent_sdk import ResultMessage

    stopped = ResultMessage(
        subtype="error_max_budget_usd",
        duration_ms=1,
        duration_api_ms=1,
        is_error=True,
        num_turns=7,
        session_id="s",
        total_cost_usd=2.5123,
    )

    assert asyncio.run(runner._drain_response(_OneResult(stopped))) is stopped

    printed = capsys.readouterr().out
    assert "Session stopped: the --max-budget-usd limit was reached ($2.5123)" in printed
    assert "Session ended with error" not in printed


def test_output_to_a_file_or_a_pipe_takes_any_character(tmp_path, monkeypatch, shell_env):
    """On Windows a redirected stream is cp1252, which has no ≥ or →: the runner's own
    error message (Copy .env.example → .env) stopped it with a UnicodeEncodeError."""
    import io

    out, err = io.BytesIO(), io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(out, encoding="cp1252"))
    monkeypatch.setattr(sys, "stderr", io.TextIOWrapper(err, encoding="cp1252"))
    for name in _FOUNDRY_NAMES:
        os.environ.pop(name, None)
    missing = tmp_path / "no.env"
    monkeypatch.setattr(sys, "argv", ["run_wizard_interactive.py", "--env-file", str(missing)])

    with pytest.raises(SystemExit) as stopped:
        runner.main()

    assert stopped.value.code == 1
    sys.stderr.flush()
    assert "Copy .env.example → .env" in err.getvalue().decode("utf-8")
    print("≥ 0.5")
    sys.stdout.flush()
    assert out.getvalue().decode("utf-8").strip() == "≥ 0.5"


class _Terminal(io.BytesIO):
    def isatty(self) -> bool:
        return True


def _terminal(monkeypatch, encoding: str):
    raw = _Terminal()
    stream = io.TextIOWrapper(raw, encoding=encoding)
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "stderr", io.TextIOWrapper(_Terminal(), encoding=encoding))
    return stream, raw


@pytest.mark.parametrize("encoding", ["utf-8", "UTF8", "cp65001"])
def test_a_utf8_terminal_is_left_as_it_is(monkeypatch, encoding) -> None:
    stream, raw = _terminal(monkeypatch, encoding)
    before = (stream.encoding, stream.errors)

    runner.use_utf8_output()

    assert (sys.stdout.encoding, sys.stdout.errors) == before == (encoding, "strict")
    print("≥ ä")
    sys.stdout.flush()
    assert raw.getvalue().decode("utf-8").strip() == "≥ ä"


def test_a_terminal_in_another_encoding_keeps_it_and_replaces_what_it_cannot_show(
    monkeypatch,
) -> None:
    """Writing UTF-8 to a cp850 console would turn every ä into two wrong signs."""
    stream, raw = _terminal(monkeypatch, "cp850")

    runner.use_utf8_output()

    assert (sys.stdout.encoding, sys.stdout.errors) == ("cp850", "replace")
    print("≥ ä")
    sys.stdout.flush()
    assert raw.getvalue().decode("cp850").strip() == "? ä"


@pytest.mark.parametrize("stream", [None, "string", "closed"])
def test_output_that_is_no_text_stream_is_left_as_it_is(monkeypatch, stream) -> None:
    """pythonw has no stdout at all, and a caller may give one without reconfigure."""
    if stream == "string":
        stream = io.StringIO()
    elif stream == "closed":
        stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        stream.close()
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "stderr", stream)

    runner.use_utf8_output()

    assert sys.stdout is stream


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


def test_the_sdk_runs_the_guard_on_each_tool_call(output, tmp_path) -> None:
    (output / "poc").mkdir()
    (output / "poc" / ".env").write_text("KEY=canary")
    options = _options(output)
    cli = _FakeCLI()
    bp = output.as_posix() + "/use_case.blueprint.json"

    async def go() -> dict[str, Any]:
        client = ClaudeSDKClient(options=options, transport=cli)
        await client.connect()
        try:
            [matcher] = cli.initialize["hooks"]["PreToolUse"]
            assert matcher["matcher"] is None
            [callback_id] = matcher["hookCallbackIds"]
            calls = {
                # What the CLI approves by itself in its default mode.
                "ls": ("Bash", {"command": "ls"}),
                "git status": ("Bash", {"command": "git status"}),
                "env file": ("Read", {"file_path": str(output / "poc" / ".env")}),
                "outside": ("Read", {"file_path": str(tmp_path / "elsewhere.txt")}),
                "printenv": ("Bash", {"command": "printenv"}),
                "mcp": ("mcp__claude_ai_Gmail__search", {"query": "x"}),
                "wizard file": ("Write", {"file_path": str(WIZARD / "SKILL.md"), "content": ""}),
                "allowed script": (
                    "Bash",
                    {"command": f"python scripts/validate_blueprint.py --blueprint {bp}"},
                ),
                "allowed write": ("Write", {"file_path": bp, "content": "{}"}),
                "allowed read": ("Read", {"file_path": str(WIZARD / "SKILL.md")}),
            }
            answers = {}
            for n, (label, (tool, tool_input)) in enumerate(calls.items()):
                answers[label] = await cli.run_hook(
                    callback_id, _pre_tool_use(tool, tool_input, WIZARD, n)
                )
            return answers
        finally:
            await client.disconnect()

    answers = asyncio.run(go())

    for label in ("ls", "git status", "env file", "outside", "printenv", "mcp", "wizard file"):
        assert _assert_denied(answers[label]), label
    assert ".env" in _assert_denied(answers["env file"])
    assert answers["allowed script"] == {}
    assert answers["allowed write"] == {}
    assert answers["allowed read"] == {}


# --- the environment, the output folder and the first prompt -----------------


def test_the_agent_gets_the_system_basics_and_the_env_files_names() -> None:
    source = {
        "PATH": "/bin",
        "HOME": "/home/me",
        "ANTHROPIC_FOUNDRY_API_KEY": "k",
        "AZURE_TTS_MODEL": "tts",
        "GITHUB_TOKEN": "secret",
        "AWS_SECRET_ACCESS_KEY": "secret",
        "MY_SHELL_VAR": "x",
    }
    env = runner.agent_environment(source, {"ANTHROPIC_FOUNDRY_API_KEY", "AZURE_TTS_MODEL"}, [])

    assert env["PATH"] == "/bin" and env["HOME"] == "/home/me"
    assert env["ANTHROPIC_FOUNDRY_API_KEY"] == "k" and env["AZURE_TTS_MODEL"] == "tts"
    assert "GITHUB_TOKEN" not in env and "AWS_SECRET_ACCESS_KEY" not in env
    assert "MY_SHELL_VAR" not in env
    assert env["CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR"] == "1"
    passed = runner.agent_environment(source, set(), ["MY_SHELL_VAR"])
    assert passed["MY_SHELL_VAR"] == "x"


_FOUNDRY_NAMES = ("CLAUDE_CODE_USE_FOUNDRY", "ANTHROPIC_FOUNDRY_API_KEY",
                  "ANTHROPIC_FOUNDRY_RESOURCE")  # fmt: skip


@pytest.fixture()
def shell_env():
    """Puts the process environment back after a test narrows it."""
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)


class _CLIStartError(Exception):
    pass


def _cli_process_env(options: ClaudeAgentOptions, monkeypatch) -> dict[str, str]:
    """The environment the SDK starts the CLI with, captured without starting it."""
    seen: dict[str, str] = {}

    async def open_process(*_args, env=None, **_kwargs):
        seen.update(env or {})
        raise _CLIStartError

    monkeypatch.setattr(anyio, "open_process", open_process)

    async def go() -> None:
        client = ClaudeSDKClient(options=options)
        try:
            await client.connect()
        except Exception:  # noqa: BLE001 - the SDK wraps the stop above in its own error
            pass

    asyncio.run(go())
    assert seen, "the SDK did not reach the point where it starts the CLI"
    return seen


def _temp_is_an_ordinary_folder(monkeypatch, tmp_path) -> None:
    """On Windows pytest's temporary folder is under %LOCALAPPDATA%, which the
    runner refuses as an output folder; point the settings folders elsewhere."""
    if sys.platform == "win32":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
        monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))


def test_the_cli_gets_only_the_env_files_names_and_the_system_basics(
    tmp_path, monkeypatch, shell_env
) -> None:
    """``main`` itself narrows the environment before the SDK starts the CLI."""
    _temp_is_an_ordinary_folder(monkeypatch, tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "CLAUDE_CODE_USE_FOUNDRY=1\nANTHROPIC_FOUNDRY_API_KEY=k\n"
        "ANTHROPIC_FOUNDRY_RESOURCE=r\nDOCLING_API_BASE=https://x\n"
    )
    os.environ["MY_SHELL_VAR"] = "x"
    for name in (*_FOUNDRY_NAMES, "DOCLING_API_BASE", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"):
        os.environ.pop(name, None)
    cli = tmp_path / "claude"
    cli.write_text("")
    build = runner.build_session_options
    monkeypatch.setattr(
        runner,
        "build_session_options",
        lambda *a, **k: build(*a, cli_path=str(cli), **k),
    )
    seen: dict[str, str] = {}

    async def open_process(*_args, env=None, **_kwargs):
        seen.update(env or {})
        raise _CLIStartError

    monkeypatch.setattr(anyio, "open_process", open_process)
    out = tmp_path / "out"
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_wizard_interactive.py", "--output-dir", str(out), "--env-file", str(env_file)],
    )
    with pytest.raises(SystemExit):
        runner.main()

    assert seen, "main did not reach the point where the SDK starts the CLI"
    assert seen["DOCLING_API_BASE"] == "https://x"
    assert seen["ANTHROPIC_FOUNDRY_API_KEY"] == "k"
    assert "MY_SHELL_VAR" not in seen
    # Compared with what the runner may hand on, not with os.environ, which main
    # has already narrowed to the same names.
    may_pass = runner.SYSTEM_ENV_VARS | set(runner.AGENT_ENV_DEFAULTS)
    may_pass |= {"CLAUDE_CODE_USE_FOUNDRY", "ANTHROPIC_FOUNDRY_API_KEY"}
    may_pass |= {"ANTHROPIC_FOUNDRY_RESOURCE", "DOCLING_API_BASE"}  # the .env file's names
    added = {name for name in seen if name.upper() not in {n.upper() for n in may_pass}}
    assert all(name == "PWD" or name.startswith("CLAUDE") for name in added), added


def test_without_an_env_file_the_provider_names_come_from_the_shell(tmp_path, shell_env) -> None:
    for name in _FOUNDRY_NAMES:
        os.environ[name] = "1"
    os.environ["AZURE_API_KEY"] = "k"
    os.environ["OPENAI_BASE_URL"] = "https://x"
    os.environ["MY_SHELL_VAR"] = "x"

    env = runner.load_environment(tmp_path / "missing.env")

    assert env["AZURE_API_KEY"] == "k" and env["OPENAI_BASE_URL"] == "https://x"
    assert all(env[name] == "1" for name in _FOUNDRY_NAMES)
    assert "MY_SHELL_VAR" not in env


def test_a_relative_output_folder_is_taken_from_where_the_runner_starts(
    tmp_path, monkeypatch
) -> None:
    _temp_is_an_ordinary_folder(monkeypatch, tmp_path)
    assert runner.resolve_output_dir("out/case", tmp_path) == (tmp_path / "out" / "case").resolve()


@pytest.mark.skipif(sys.platform != "win32", reason="Git Bash drive paths are Windows only")
def test_a_git_bash_output_folder_is_read_as_a_windows_path(tmp_path, monkeypatch) -> None:
    _temp_is_an_ordinary_folder(monkeypatch, tmp_path)
    target = tmp_path / "case"
    drive, rest = target.as_posix().split(":", 1)

    assert runner.resolve_output_dir(f"/{drive.lower()}{rest}", tmp_path) == target.resolve()


@pytest.mark.parametrize("inside", [".", "implementation_layer/solution_wizard/out"])
def test_an_output_folder_inside_the_repository_is_refused(inside) -> None:
    with pytest.raises(ValueError, match="inside the GAIK repository"):
        runner.resolve_output_dir(inside, runner.REPO_ROOT)


def test_an_output_folder_that_holds_the_repository_is_refused() -> None:
    with pytest.raises(ValueError, match="holds the GAIK repository"):
        runner.resolve_output_dir("..", runner.REPO_ROOT)


def test_the_first_prompt_gives_the_output_folder_with_forward_slashes() -> None:
    from pathlib import PureWindowsPath

    prompt = runner.build_initial_prompt(PureWindowsPath(r"C:\\work\\case"))  # type: ignore[arg-type]
    assert "C:/work/case" in prompt and "\\" not in prompt


# --- a live session ------------------------------------------------------------


def _live_credentials() -> bool:
    return bool(
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("CLAUDE_CODE_USE_FOUNDRY")
        or os.environ.get("WIZARD_LIVE_CLAUDE_LOGIN")
    )


#: The calls the live probe asks for: what the CLI approves by itself, reads
#: and writes inside and outside the output folder, and the wizard's scripts.
PROBE = [
    "Run the Bash command: ls",
    "Run the Bash command: git status",
    "Read the file {out}/poc/.env",
    "Use Grep to search for CANARY in the folder {out}",
    "Read the file {outside}/note.txt",
    "Run the Bash command: printenv",
    "Run the Bash command: python scripts/run_wizard.py --show-registry",
    "Write the text hello to {out}/probe.txt",
    "Write the text hello to {wizard}/probe.txt",
]


@pytest.mark.llm
def test_a_live_session_sends_every_tool_call_through_the_guard(tmp_path) -> None:
    """Starts the real CLI with the runner's options and a small model.

    Needs ANTHROPIC_API_KEY, Foundry settings, or WIZARD_LIVE_CLAUDE_LOGIN=1 for
    a claude.ai login; WIZARD_LIVE_MODEL picks the model.
    """
    if not _live_credentials():
        pytest.skip("no credentials for a live session")
    from claude_agent_sdk import AssistantMessage, ResultMessage, ToolUseBlock, UserMessage

    out, outside = tmp_path / "out", tmp_path / "outside"
    (out / "poc").mkdir(parents=True)
    outside.mkdir()
    (out / "poc" / ".env").write_text("KEY=CANARY-ENV-0451\n")
    (outside / "note.txt").write_text("CANARY-OUTSIDE-0451\n")
    names = {k for k in os.environ if k.startswith(("ANTHROPIC_", "CLAUDE_CODE_", "AZURE_"))}
    env = runner.agent_environment(dict(os.environ), names, [])
    for nested in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"):
        env.pop(nested, None)
    model = os.environ.get("WIZARD_LIVE_MODEL", "claude-haiku-5-5")
    options = runner.build_session_options(out, env, model, max_turns=30)
    [matcher] = options.hooks["PreToolUse"]
    guard_hook = matcher.hooks[0]
    seen: dict[str, tuple[str, dict]] = {}
    inputs: dict[str, str] = {}

    async def recording(input_data, tool_use_id, context):
        answer = await guard_hook(input_data, tool_use_id, context)
        seen[tool_use_id] = (input_data["tool_name"], answer)
        inputs[tool_use_id] = json.dumps(input_data.get("tool_input"))[:90]
        return answer

    matcher.hooks[0] = recording
    steps = "\n".join(
        f"{i + 1}. "
        + s.format(
            out=out.as_posix(), outside=outside.as_posix(), wizard=WIZARD.as_posix()
        )  # fmt: skip
        for i, s in enumerate(PROBE)
    )
    prompt = (
        "This is a test of the tool permissions. Do each step below with exactly one "
        "tool call, in order, even if an earlier one was refused, then reply DONE.\n" + steps
    )
    used: dict[str, str] = {}
    texts: list[str] = []

    async def go() -> None:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            used[block.id] = block.name
                        texts.append(str(getattr(block, "text", "")))
                elif isinstance(message, UserMessage):
                    texts.append(str(message.content))
                elif isinstance(message, ResultMessage):
                    break

    asyncio.run(go())

    # The call log, for the person who runs this against a new SDK or CLI.
    for tool_use_id, name in used.items():
        decision = seen.get(tool_use_id, (name, None))[1]
        verdict = "not seen" if decision is None else ("refused" if decision else "allowed")
        print(f"{name}: {verdict}  {inputs.get(tool_use_id, '')}")
    assert len(used) >= len(PROBE) - 1, used
    # Every call the model made reached the guard, the self-approved ones too.
    assert set(used) <= set(seen), set(used) - set(seen)
    everything = "\n".join(texts)
    assert "CANARY-ENV-0451" not in everything
    assert "CANARY-OUTSIDE-0451" not in everything
    assert (out / "probe.txt").exists()
    assert not (WIZARD / "probe.txt").exists()


def test_without_an_env_file_every_provider_setting_in_the_shell_reaches_the_agent(
    tmp_path, shell_env
) -> None:
    for name in _FOUNDRY_NAMES:
        os.environ[name] = "1"
    os.environ["ANTHROPIC_MAX_TOKENS"] = "100"
    os.environ["GOOGLE_VERTEXAI_PROJECT"] = "p"
    os.environ["OPENAI_TTS_MODEL"] = "t"
    os.environ["GITHUB_TOKEN"] = "x"

    env = runner.load_environment(tmp_path / "missing.env")

    assert env["ANTHROPIC_MAX_TOKENS"] == "100" and env["GOOGLE_VERTEXAI_PROJECT"] == "p"
    assert env["OPENAI_TTS_MODEL"] == "t" and "GITHUB_TOKEN" not in env


def test_git_bash_path_is_a_system_name() -> None:
    assert "CLAUDE_CODE_GIT_BASH_PATH" in runner.SYSTEM_ENV_VARS


def test_on_windows_an_env_files_name_matches_the_shell_name_in_any_case(monkeypatch) -> None:
    monkeypatch.setattr(runner.os, "name", "nt")
    env = runner.agent_environment({"AZURE_API_KEY": "k", "OTHER": "x"}, {"Azure_Api_Key"}, [])
    assert env["AZURE_API_KEY"] == "k" and "OTHER" not in env


@pytest.fixture()
def home(tmp_path, monkeypatch):
    home = tmp_path / "home" / "me"
    (home / ".config").mkdir(parents=True)
    (home / "work").mkdir()
    monkeypatch.setattr(runner.Path, "home", classmethod(lambda cls: home))
    for name in ("CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME", "APPDATA", "LOCALAPPDATA"):
        monkeypatch.delenv(name, raising=False)
    return home


def test_an_output_folder_under_home_is_accepted(home) -> None:
    assert runner.resolve_output_dir(str(home / "work" / "case"), home) == Path(
        os.path.realpath(home / "work" / "case")
    )


@pytest.mark.parametrize("where", ["home", "above"])
def test_the_home_folder_and_the_folders_above_it_are_refused(home, where) -> None:
    folder = home if where == "home" else home.parent
    with pytest.raises(ValueError, match="home folder"):
        runner.resolve_output_dir(str(folder), home)


def test_a_settings_folder_in_home_is_refused(home) -> None:
    with pytest.raises(ValueError, match="settings folder"):
        runner.resolve_output_dir(str(home / ".config" / "case"), home)


def test_a_folder_the_scripts_python_loads_code_from_is_refused(
    home, tmp_path, monkeypatch
) -> None:
    venv = tmp_path / "tools" / "venv"
    venv.mkdir(parents=True)
    monkeypatch.setattr(
        agent_tool_guard, "python_code_dirs", lambda: [Path(os.path.realpath(venv))]
    )
    with pytest.raises(ValueError, match="loads code from"):
        runner.resolve_output_dir(str(venv / "out"), home)
    with pytest.raises(ValueError, match="loads code from"):
        runner.resolve_output_dir(str(venv.parent), home)


def test_the_repository_is_refused_in_any_case_where_the_filesystem_ignores_it() -> None:
    if not agent_tool_guard._ignores_case(runner.REPO_ROOT):
        pytest.skip("this filesystem tells names apart by case")
    other_case = str(runner.REPO_ROOT / "out").swapcase()
    with pytest.raises(ValueError, match="inside the GAIK repository"):
        runner.resolve_output_dir(other_case, runner.REPO_ROOT)


def test_the_guard_never_writes_the_repository(output) -> None:
    options = runner.build_session_options(output, {}, "m")
    guard = options.hooks["PreToolUse"][0].hooks[0].__self__
    assert agent_tool_guard.under_any(Path(os.path.realpath(runner.REPO_ROOT)), guard.protected)
