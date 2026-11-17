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
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
from pathlib import Path
from typing import Any

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
    # refresh_schema_model.py (SKILL.md Step 4.5) is left out: it imports the
    # session's output_schema.py, and every script here runs the wizard's own code
    # only. With gaik 0.10.0 the step changes nothing; how the model file is
    # refreshed from the next gaik pin is open.
}
#: Scripts that turn the blueprint into code, so they get its text checked first.
_SCAFFOLDING_SCRIPTS = frozenset({"scaffold_poc.py"})
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
    """Per-session rules; ``hook`` is registered as the agent's PreToolUse hook."""

    def __init__(self, wizard_dir: Path, output_dir: Path) -> None:
        self.cwd = Path(os.path.realpath(wizard_dir))
        self.output = Path(os.path.realpath(output_dir))
        self.readable = [self.output, self.cwd]
        self.writable = [self.output]

    async def hook(self, input_data: Any, tool_use_id: str | None, context: Any) -> dict[str, Any]:
        try:
            tool = input_data.get("tool_name", "")
            tool_input = input_data.get("tool_input") or {}
            reason = self.check(tool, tool_input if isinstance(tool_input, dict) else {})
        except Exception:  # noqa: BLE001 - a call the rules cannot decide does not run
            logger.exception("tool guard could not decide a call; refusing it")
            reason = "The wizard could not check this tool call, so it was not run."
        return _deny(reason) if reason else {}

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
        command = _CONTINUATION.sub(" ", command).strip()
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
        options = _SCRIPTS.get(Path(script).name)
        if options is None or not _inside(script, [self.cwd / "scripts"], self.cwd):
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
