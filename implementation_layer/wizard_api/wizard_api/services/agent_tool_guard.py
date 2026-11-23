"""What the wizard agent's tools may touch.

The agent runs with ``bypassPermissions``, which on its own lets every tool
reach anything the API container can. The agent only needs its own session and
the wizard's assets, so a PreToolUse hook decides every tool call before it runs:

* files are written only in the session's own directory, and read only there
  and in the wizard's own assets (SKILL.md, references, templates, scripts);
* Bash runs only the wizard's scripts, one plain command at a time: no shell
  operators, redirection or variables, so nothing else can be chained on;
* every other tool (web fetch and search, subagents, notebooks) is refused.

A refusal tells the agent what is allowed, so it can carry on within the rules.
The PoC itself runs in the sandbox Job, not here.

``WIZARD_AGENT_MAX_TURNS`` counts the agent's own model calls only. A call that
reaches a model or the web another way is *metered*: a run of a wizard script
that calls a model itself, web search and fetch, and the tools of an MCP server
other than the wizard's own. Each one the rules let run is counted for the chat
message (``WIZARD_MAX_METERED_CALLS_PER_TURN``) and for the user in a sliding
hour (``WIZARD_MAX_METERED_CALLS_PER_USER_PER_HOUR``); over either it is refused
too. The web tools and outside MCP servers are refused by the rules today and
are metered by name, so they fall under the limits the moment they are allowed.

Every decision is one log line and one count of ``wizard.agent.tool_calls``:
the tool's name, its kind and the reason, never its input.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import shlex
import time
from collections import deque
from pathlib import Path
from typing import Any, NamedTuple

from wizard_api import config
from wizard_api.services import scaffold_guard

logger = logging.getLogger(__name__)

_READ_TOOLS = {"Read": "file_path", "Grep": "path", "Glob": "path", "LS": "path"}
_WRITE_TOOLS = {"Write": "file_path", "Edit": "file_path", "MultiEdit": "file_path"}
#: ToolSearch is how the agent loads the description of a tool the CLI lists by
#: name only, which is how it lists the wizard's own tools below: refused, the
#: agent took those tools as unavailable and never called them. It runs
#: nothing; what it finds is still decided here, call by call.
_HARMLESS_TOOLS = {"TodoWrite", "ToolSearch"}
#: The wizard's own in-process tools (agent_service). Each checks its own input
#: and acts only on the session the agent belongs to.
_WIZARD_TOOLS = {"mcp__wizard__reopen_gate", "mcp__wizard__offer_language"}

_PATH, _VALUE, _URL, _FLAG = "path", "value", "url", "flag"
_RENDER = {"--blueprint": _PATH, "--output-dir": _PATH, "--skip-validation": _FLAG}
#: The scripts SKILL.md tells the agent to run and every option each one takes.
#: Paths must be in the session; options are spelled out in full, because
#: argparse would accept an abbreviation the guard does not recognise.
#: ``promote_template.py`` is left out on purpose: a promoted template is reused
#: by every later session.
_SCRIPTS: dict[str, dict[str, str]] = {
    "check_requirements.py": {"--blueprint": _PATH},
    "generate_bpmn.py": _RENDER,
    "generate_docs.py": _RENDER,
    "generate_mermaid.py": _RENDER,
    "generate_schema.py": {
        "--requirements": _PATH,
        "--schema-name": _VALUE,
        "--output-dir": _PATH,
        "--provider": _VALUE,
        "--use-azure": _FLAG,
        "--no-azure": _FLAG,
        "--model": _VALUE,
        "--base-url": _URL,
    },
    # --export-schema is left out: it rewrites the wizard's own schema file.
    "run_wizard.py": {"--blueprint": _PATH, "--output-dir": _PATH, "--show-registry": _FLAG},
    "scaffold_poc.py": {
        "--blueprint": _PATH,
        "--output-dir": _PATH,
        "--synthetic": _FLAG,
        "--skip-validation": _FLAG,
    },
    "validate_blueprint.py": {"--blueprint": _PATH},
    # The AI Act screening (SKILL.md Phase 12, ai_act_screening/scripts/). The
    # checker only reads; the brief renderer writes ai_act_screening.json and
    # docs/ai_act_screening.md under --pack. Both use the standard library only: no
    # model call, no network, no subprocess.
    "check_screening.py": {
        "--pack": _PATH,
        "--screening": _PATH,
        "--transcript": _PATH,
        "--hash": _FLAG,
        "--status": _FLAG,
    },
    "render_brief.py": {"--pack": _PATH, "--outdated": _FLAG},
    # refresh_schema_model.py (SKILL.md Step 4.5) is left out: it imports the
    # session's output_schema.py, and every script here runs the wizard's own code
    # only. The PoC loads output_schema_model.json and writes it again itself when
    # output_schema.py is newer (GAIK-project/gaik-toolkit#247), in a sandbox run
    # (the package fetch keeps the files' times) and in a downloaded package.
}
#: Scripts that turn the blueprint into code, so they get its text checked first.
_SCAFFOLDING_SCRIPTS = frozenset({"scaffold_poc.py"})
#: Where a script is, under the wizard directory, when that is not ``scripts/``: the
#: AI Act screening is a skill of its own next to SKILL.md. A name is run only from
#: its own folder, so a file of the same name anywhere else is not that script.
_SCRIPT_FOLDERS = {
    "check_screening.py": "ai_act_screening/scripts",
    "render_brief.py": "ai_act_screening/scripts",
}
_PYTHON = frozenset({"python", "python3"})
#: The two one-liners SKILL.md uses: a syntax check and an import check.
_ONE_LINERS = (
    re.compile(r"^import ast; ast\.parse\(open\('([^']+)'\)\.read\(\)\)$"),
    re.compile(r"^import (gaik(?:\.[A-Za-z0-9_]+)*)$"),
)
#: A one-liner is accepted only as the whole command in one pair of double
#: quotes, with nothing the shell would expand inside (no $, backtick or
#: backslash) and nothing chained on after the closing quote.
_ONE_LINER_COMMAND = re.compile(r'^python3? -c "([^"\\$`]*)"$')
#: A line continuation, as in SKILL.md's multi-line generate_schema.py command.
_CONTINUATION = re.compile(r"\\\r?\n")
_SHELL_SYNTAX = re.compile(r"[;&|`$<>(){}\\\n\r*?\[\]~!#]")

#: Scripts in ``_SCRIPTS`` that call a model themselves: generate_schema.py runs
#: gaik's SchemaGenerator. No other listed script does.
_MODEL_SCRIPTS = frozenset({"generate_schema.py"})
_WEB_TOOLS = frozenset({"WebSearch", "WebFetch"})
_MCP_PREFIX = "mcp__"
_WIZARD_MCP_PREFIX = "mcp__wizard__"
#: The kinds of call counted against the metered-call limits.
METERED_KINDS = frozenset({"model_script", "web", "mcp"})
#: The reason code a refusal by the rules gets, by kind of call.
_REFUSED = {
    "read": "path_not_allowed",
    "write": "path_not_allowed",
    "command": "command_not_allowed",
    "model_script": "command_not_allowed",
}
_LIMIT_CODES = frozenset({"turn_limit", "user_limit"})
#: A tool name fit for a log line and a metric; anything else is logged as "other".
_TOOL_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,99}$")

_METERED_WHAT = (
    "calls that use a model or the web (generate_schema.py, web search or fetch, outside MCP tools)"
)
_TURN_LIMIT = (
    "This call was not run: this message has already made {limit} " + _METERED_WHAT + ", "
    "the most one message may make. Carry on without it. If the work cannot go on without "
    "it, tell the user in plain words that the wizard stopped at its limit for one message "
    "and that their next message lets you continue."
)
_USER_LIMIT = (
    "This call was not run: the user has made {limit} " + _METERED_WHAT + " in the last "
    "hour, the most the wizard allows. Carry on without it. If the work cannot go on "
    "without it, tell the user in plain words that the wizard's hourly limit is reached and "
    "that they can try again in about {minutes} minutes."
)

#: user id -> times (time.monotonic) of the metered calls let run in the last hour,
#: across every agent of that user. In this API process, as the chat turn rate is.
_USER_CALLS: dict[str, deque[float]] = {}
_USER_WINDOW_SECONDS = 3600


def _forget_old_calls(now: float) -> None:
    """Drop the calls older than the window, and every user left with none.

    Run on each metered call, over every user: a user who stops working does not
    stay in memory, and the table holds no more than the last hour's callers.
    """
    cutoff = now - _USER_WINDOW_SECONDS
    for user_id, calls in list(_USER_CALLS.items()):
        while calls and calls[0] <= cutoff:
            calls.popleft()
        if not calls:
            del _USER_CALLS[user_id]


class Decision(NamedTuple):
    """What the guard decided for one call, and what of it may be logged."""

    kind: str
    #: The wizard script a Bash call runs, by its name in ``_SCRIPTS``, or None.
    script: str | None
    #: ``ok`` when the call may run, else why not (a fixed code).
    code: str
    #: What the agent is told when the call is refused, None when it may run.
    reason: str | None


def _normalise(command: str) -> str:
    return _CONTINUATION.sub(" ", command).strip()


def _script_name(command: str) -> str | None:
    """The wizard script a Bash command runs, or None (a one-liner, anything else).

    Parsed as ``_check_bash`` parses it, so a command the guard lets run is
    named by the script that runs, however it is quoted or spelled out.
    """
    command = _normalise(command)
    if _ONE_LINER_COMMAND.match(command) or _SHELL_SYNTAX.search(command):
        return None
    try:
        argv = shlex.split(command)
    except ValueError:
        return None
    if len(argv) < 2 or argv[0] not in _PYTHON:
        return None
    name = Path(argv[1]).name
    return name if name in _SCRIPTS else None


def call_kind(tool: str, tool_input: dict[str, Any]) -> tuple[str, str | None]:
    """The kind of a call and, for Bash, the wizard script it runs."""
    if tool in _HARMLESS_TOOLS:
        return "internal", None
    if tool in _WIZARD_TOOLS or tool.startswith(_WIZARD_MCP_PREFIX):
        return "wizard", None
    if tool in _WRITE_TOOLS:
        return "write", None
    if tool in _READ_TOOLS:
        return "read", None
    if tool == "Bash":
        script = _script_name(str(tool_input.get("command") or ""))
        return ("model_script" if script in _MODEL_SCRIPTS else "command"), script
    if tool in _WEB_TOOLS:
        return "web", None
    if tool.startswith(_MCP_PREFIX):
        return "mcp", None
    return "other", None


def _record(tool: str, decision: Decision, *, failed: bool = False) -> None:
    """One log line and one count for a decision: no command, path, input, URL or id.

    Allowed calls and refusals by the rules are INFO; a refusal at a limit is a
    WARNING, which also reaches the WP5 collector; a call the guard could not
    decide is an ERROR with its traceback (which stays in the pod).
    """
    name = tool if _TOOL_NAME.match(tool or "") else "other"
    outcome = "allowed" if decision.reason is None else "denied"
    if failed:
        level = logging.ERROR
    elif decision.code in _LIMIT_CODES:
        level = logging.WARNING
    else:
        level = logging.INFO
    logger.log(
        level,
        "tool call tool=%s kind=%s script=%s decision=%s reason=%s",
        name,
        decision.kind,
        decision.script or "-",
        outcome,
        decision.code,
        exc_info=failed,
    )
    try:
        from wizard_api import ops_metrics

        ops_metrics.tool_calls.add(
            1, {"kind": decision.kind, "decision": outcome, "reason": decision.code}
        )
    except Exception:  # noqa: BLE001 - a count never changes a decision
        logger.debug("tool call could not be counted", exc_info=True)


def _deny(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _expands(path: str) -> bool:
    """A path the tool or the shell rewrites before opening it.

    Checked as written, ``~/x`` looks like a folder named ``~`` inside the
    working directory, but the file tools and the shell open it under the home
    directory. Whatever is judged here must be what gets opened, so such a path
    is refused rather than guessed at.
    """
    return path.startswith("~") or "$" in path


def _inside(path: str, roots: list[Path], cwd: Path) -> bool:
    if _expands(path):
        return False
    target = Path(path) if os.path.isabs(path) else cwd / path
    real = Path(os.path.realpath(target))
    return any(real == root or root in real.parents for root in roots)


class ToolGuard:
    """Per-session rules; ``hook`` is registered as the agent's PreToolUse hook.

    ``user_id`` is the session owner, whose metered calls are counted together
    across their sessions; ``start_turn`` begins the count of a new chat message.
    """

    def __init__(self, wizard_dir: Path, output_dir: Path, *, user_id: str | None = None) -> None:
        self.cwd = Path(os.path.realpath(wizard_dir))
        self.output = Path(os.path.realpath(output_dir))
        self.readable = [self.output, self.cwd]
        self.writable = [self.output]
        self.user_id = user_id
        #: Metered calls let run since the chat message began.
        self.turn_calls = 0

    def start_turn(self) -> None:
        """A new chat message: its metered calls are counted from zero."""
        self.turn_calls = 0

    async def hook(self, input_data: Any, tool_use_id: str | None, context: Any) -> dict[str, Any]:
        tool = ""
        try:
            tool = str(input_data.get("tool_name", "") or "")
            tool_input = input_data.get("tool_input") or {}
            decision = self.decide(tool, tool_input if isinstance(tool_input, dict) else {})
        except Exception:  # noqa: BLE001 - a call the rules cannot decide does not run
            decision = Decision(
                "other",
                None,
                "guard_error",
                "The wizard could not check this tool call, so it was not run.",
            )
            _record(tool, decision, failed=True)
            return _deny(decision.reason)
        _record(tool, decision)
        return _deny(decision.reason) if decision.reason else {}

    def decide(
        self, tool: str, tool_input: dict[str, Any], *, now: float | None = None
    ) -> Decision:
        """The rules first, then the metered-call limits for a call the rules let run.

        A metered call that may run is counted here, so a refused one uses up nothing.
        """
        kind, script = call_kind(tool, tool_input)
        reason = self.check(tool, tool_input)
        if reason is not None:
            return Decision(kind, script, _REFUSED.get(kind, "tool_not_available"), reason)
        if kind in METERED_KINDS:
            over = self._meter(time.monotonic() if now is None else now)
            if over is not None:
                return Decision(kind, script, *over)
        return Decision(kind, script, "ok", None)

    def _meter(self, now: float) -> tuple[str, str] | None:
        """The limit a metered call is over, as (code, refusal), or None once it is counted."""
        turn_limit = config.max_metered_calls_per_turn()
        if self.turn_calls >= turn_limit:
            return "turn_limit", _TURN_LIMIT.format(limit=turn_limit)
        user_limit = config.max_metered_calls_per_user_per_hour()
        if self.user_id and user_limit > 0:
            _forget_old_calls(now)
            calls = _USER_CALLS.get(self.user_id)
            if calls is not None and len(calls) >= user_limit:
                minutes = max(1, math.ceil((calls[0] + _USER_WINDOW_SECONDS - now) / 60))
                return "user_limit", _USER_LIMIT.format(limit=user_limit, minutes=minutes)
            _USER_CALLS.setdefault(self.user_id, deque()).append(now)
        self.turn_calls += 1
        return None

    def check(self, tool: str, tool_input: dict[str, Any]) -> str | None:
        """Why the call is refused, or None when it may run."""
        if tool in _HARMLESS_TOOLS or tool in _WIZARD_TOOLS:
            return None
        if tool in _WRITE_TOOLS:
            path = tool_input.get(_WRITE_TOOLS[tool]) or ""
            if not path or not _inside(path, self.writable, self.cwd):
                return f"Files can be written only in the session directory {self.output}."
            return None
        if tool in _READ_TOOLS:
            paths = [tool_input.get(_READ_TOOLS[tool]) or str(self.cwd)]
            pattern = tool_input.get("pattern")
            if tool == "Glob" and isinstance(pattern, str):
                if ".." in Path(pattern).parts:
                    return "Glob patterns may not climb out of their directory with '..'."
                if _expands(pattern) or pattern.startswith("{"):
                    return "Glob patterns must be plain paths under an allowed directory."
                if os.path.isabs(pattern):
                    paths.append(pattern.split("*", 1)[0] or "/")
            if not all(_inside(p, self.readable, self.cwd) for p in paths):
                return (
                    f"Files can be read only in the session directory {self.output} "
                    "and in the wizard's own files."
                )
            return None
        if tool == "Bash":
            return self._check_bash(str(tool_input.get("command") or ""))
        return f"The {tool} tool is not available in the wizard."

    def _check_bash(self, command: str) -> str | None:
        allowed = (
            "Bash runs only the wizard's scripts, one plain command at a time, e.g. "
            "`python scripts/validate_blueprint.py --blueprint "
            "<session dir>/use_case.blueprint.json`. "
            "Use the Read, Write, Edit, Glob and Grep tools for files. The PoC runs in the sandbox "
            "from the wizard's Run button, not here."
        )
        command = _normalise(command)  # as _script_name reads it
        whole = _ONE_LINER_COMMAND.match(command)
        if whole:
            return self._check_one_liner(whole.group(1), allowed)
        if _SHELL_SYNTAX.search(command):
            return "No shell operators, redirection, variables or globs. " + allowed
        try:
            argv = shlex.split(command)
        except ValueError:
            return allowed
        if len(argv) < 2 or argv[0] not in _PYTHON:
            return allowed
        script = argv[1]
        name = Path(script).name
        options = _SCRIPTS.get(name)
        folder = self.cwd / _SCRIPT_FOLDERS.get(name, "scripts")
        if options is None or not _inside(script, [folder], self.cwd):
            return allowed
        given = self._options(argv[2:], options)
        if isinstance(given, str):
            return f"{given} {Path(script).name} takes {', '.join(options)}. " + allowed
        for option, value in given.items():
            kind = options[option]
            if kind == _PATH and not _inside(value, self.writable, self.cwd):
                return f"{option} must be in the session directory {self.output}. " + allowed
            if kind == _URL and (
                value.lower().startswith("env:") or not scaffold_guard.endpoint_ok(value)
            ):
                return (
                    f"{option} must be a provider's own https endpoint; leave it out to use "
                    "the endpoint configured in the environment. " + allowed
                )
        if Path(script).name in _SCAFFOLDING_SCRIPTS:
            return self._check_blueprint(given)
        return None

    @staticmethod
    def _options(args: list[str], options: dict[str, str]) -> dict[str, str] | str:
        """The options as {name: value}, or why they are not accepted."""
        given: dict[str, str] = {}
        i = 0
        while i < len(args):
            name, eq, value = args[i].partition("=")
            kind = options.get(name)
            if kind is None:
                return f"Unknown option or argument {args[i]!r}:"
            if name in given:
                return f"{name} is given twice:"
            if kind == _FLAG:
                if eq:
                    return f"{name} takes no value:"
                value = ""
            elif not eq:
                i += 1
                if i == len(args) or args[i].startswith("-"):
                    return f"{name} needs a value:"
                value = args[i]
            if kind != _FLAG and not value:
                return f"{name} needs a value:"
            given[name] = value
            i += 1
        return given

    def _check_one_liner(self, code: str, allowed: str) -> str | None:
        for one_liner in _ONE_LINERS:
            match = one_liner.match(code)
            if match:
                if one_liner is _ONE_LINERS[0] and not _inside(
                    match.group(1), self.readable, self.cwd
                ):
                    return allowed
                return None
        return allowed

    def _check_blueprint(self, given: dict[str, str]) -> str | None:
        """The scaffolder pastes blueprint text into code it runs (scaffold_guard)."""
        path = given.get("--blueprint")
        if path is None:
            return None  # the script refuses to run without one
        target = Path(path) if os.path.isabs(path) else self.cwd / path
        try:
            blueprint = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None  # the script reports an unreadable blueprint itself
        if not isinstance(blueprint, dict):
            return None
        if "--output-dir" not in given:
            # Without --output-dir the scaffolder writes where the blueprint says.
            package = blueprint.get("package")
            output_dir = package.get("output_dir") if isinstance(package, dict) else None
            if output_dir and not _inside(str(output_dir), self.writable, self.cwd):
                return (
                    f"The blueprint's package.output_dir is outside the session; pass "
                    f"--output-dir {self.output} or fix package.output_dir."
                )
        found = scaffold_guard.problems(blueprint)
        if not found and scaffold_guard.safe_for_scaffolding(blueprint) == blueprint:
            return None
        transcription = scaffold_guard.transcription_model_problems(blueprint)
        if transcription:
            return "Fix the blueprint before scaffolding: " + transcription[0] + "."
        return (
            "Fix the blueprint before scaffolding: names that become code must be plain "
            "identifiers (letters, digits, _), and text values may not contain double quotes, "
            "backslashes or line breaks (use ” instead of a double quote). "
            + ("Problems: " + "; ".join(found[:5]) if found else "")
        ).strip()
