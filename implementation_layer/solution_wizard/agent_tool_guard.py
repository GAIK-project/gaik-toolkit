"""What the wizard agent's tools may touch.

The agent runs with ``bypassPermissions``, which on its own lets every tool
reach anything the user running it can. The agent only needs its session's
output folder and the wizard's own files, so a PreToolUse hook decides every
tool call before it runs. A hook runs before the CLI's own approval, so it
also sees the calls the CLI would approve by itself (``ls``, reading a file):

* files are written only in the output folder, and read only there and in the
  wizard's own files (SKILL.md, references, templates, scripts);
* ``.env`` files are not read or written, wherever they are: they hold keys
  (``.env.example`` is a template and may be);
* Bash runs only the wizard's scripts, one plain command at a time, with the
  options ``scripts/agent_scripts.json`` lists (or ``--help`` alone): no shell
  operators, redirection or variables, so nothing else can be chained on; a
  script does not run while a folder it writes into holds a link it would follow,
  nor when the table does not say which folders it writes into;
* every other tool (web fetch and search, subagents, notebooks, MCP tools) is
  refused.

A refusal tells the agent what is allowed, so it can carry on within the rules.

The interactive runner (``run_wizard_interactive.py``) and Solution Wizard v2
use this guard. A caller may add its own check of a blueprint before it is
scaffolded (``blueprint_check``).
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import site
import sys
from collections.abc import Callable
from pathlib import Path, PurePath
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

SCRIPTS_TABLE = Path(__file__).resolve().parent / "scripts" / "agent_scripts.json"

_READ_TOOLS = {"Read": "file_path", "Grep": "path", "Glob": "path", "LS": "path"}
_WRITE_TOOLS = {"Write": "file_path", "Edit": "file_path", "MultiEdit": "file_path"}
#: ToolSearch is how the agent loads the description of a tool the CLI lists by
#: name only. It runs nothing; what it finds is still decided here, call by call.
_HARMLESS_TOOLS = frozenset({"TodoWrite", "ToolSearch"})

_PATH, _VALUE, _URL, _FLAG = "path", "value", "url", "flag"
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
#: A Git Bash path on Windows: /c/Users/... is C:/Users/...
_GIT_BASH_DRIVE = re.compile(r"^/([A-Za-z])(/|$)")
#: The hosts of the providers gaik calls; --base-url must be one of them.
PROVIDER_HOSTS = (
    ".openai.azure.com",
    ".services.ai.azure.com",
    ".cognitiveservices.azure.com",
    "api.openai.com",
    "api.anthropic.com",
    "aitta-api.csc.fi",
    "generativelanguage.googleapis.com",
)

BlueprintCheck = Callable[[dict[str, Any]], "str | None"]


def load_scripts(table: Path = SCRIPTS_TABLE) -> dict[str, dict[str, str]]:
    """The scripts the agent may run and the kind of each option they take."""
    return json.loads(table.read_text(encoding="utf-8"))["scripts"]


def load_left_out(table: Path = SCRIPTS_TABLE) -> dict[str, str]:
    """Scripts the agent may not run at all, with the reason the refusal gives."""
    left_out = json.loads(table.read_text(encoding="utf-8"))["left_out"]
    return {name: reason for name, reason in left_out.items() if " " not in name}


def load_writes(table: Path = SCRIPTS_TABLE) -> dict[str, list[str]]:
    """The folders each script writes into, relative to the folder it writes in.

    A table without ``writes`` is refused rather than read as "writes nothing",
    which would let every script run without the link check; a script the table
    lists without an entry there is not run (see ``ToolGuard._check_bash``).
    """
    data = json.loads(table.read_text(encoding="utf-8"))
    writes = data.get("writes")
    if not isinstance(writes, dict):
        raise ValueError(
            f"{table.name} has no 'writes' table: list the folders each script writes "
            "into ([] for one that writes nothing)"
        )
    for script, folders in writes.items():
        if not isinstance(folders, list) or not all(isinstance(f, str) for f in folders):
            raise ValueError(f"{table.name}: 'writes' for {script} must be a list of folders")
    return writes


def endpoint_ok(value: str) -> bool:
    """A known provider's own https endpoint."""
    try:
        url = urlsplit(value.strip())
    except ValueError:
        return False
    host = (url.hostname or "").lower()
    return (
        url.scheme == "https"
        and not url.username
        and any(
            host == h.lstrip(".") or (h.startswith(".") and host.endswith(h))
            for h in PROVIDER_HOSTS
        )
    )


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


def _native(path: str) -> str:
    """``path`` as the operating system reads it (a Git Bash /c/... on Windows)."""
    if os.name == "nt" and (m := _GIT_BASH_DRIVE.match(path)):
        return f"{m.group(1)}:/{path[m.end() :]}"
    return path


def _is_env_name(name: str) -> bool:
    if name in {".env.example", ".env.template", ".env.sample"}:
        return False
    return name == ".env" or name.startswith(".env.") or name.endswith(".env")


def is_env_file(path: str) -> bool:
    """A ``.env`` file, which holds keys: ``.env``, ``.env.local``, ``x.env``.

    The last part of the path is judged in each of the forms Windows also opens
    a file under: any part between colons (a drive prefix such as ``C:.env`` or
    a stream suffix such as ``.env::$DATA``), with trailing dots and spaces
    dropped, as Windows drops them. Elsewhere these forms are only stricter.
    """
    name = re.split(r"[\\/]", path.rstrip("\\/"))[-1].lower()
    return any(_is_env_name(part.rstrip(". ")) for part in [name, *name.split(":")])


#: Entries a folder search may look through for .env files before it is refused.
_MAX_SEARCHED_ENTRIES = 50_000


def _has_env_file(folder: Path) -> bool:
    """Whether a search of ``folder`` could read a .env file (True when the
    folder is too large to tell). Grep reads hidden files too."""
    seen = 0
    for root, dirs, files in os.walk(folder):
        seen += len(dirs) + len(files)
        if seen > _MAX_SEARCHED_ENTRIES:
            return True
        if any(is_env_file(name) for name in files):
            return True
        # A link may lead to a folder that has one; the walk does not follow it.
        if any(_is_link(os.path.join(root, name)) for name in [*dirs, *files]):
            return True
    return False


def _real(path: str, cwd: Path) -> Path:
    """The file ``path`` opens, links and Windows short names resolved."""
    path = _native(path)
    target = Path(path) if os.path.isabs(path) else cwd / path
    return Path(os.path.realpath(target))


def _folded_under(path: PurePath, root: PurePath, fold: Callable[[str], str]) -> bool:
    """Whether ``path`` is ``root`` or inside it, each name folded with ``fold``."""
    parts, root_parts = path.parts, root.parts
    return len(parts) >= len(root_parts) and all(
        fold(part) == fold(root_part) for part, root_part in zip(parts, root_parts)
    )


def _inside(path: str, roots: list[Path], cwd: Path) -> bool:
    """Whether ``path`` opens inside one of ``roots``.

    An allow check. Names are compared as written, except under a root whose
    filesystem opens a name in either case (macOS and Windows by default): there
    ``realpath`` keeps the case a path was typed in, so the output folder typed in
    one case and a path Glob returns in the disk's case name the same folder, and
    they are compared in lower case. On a case-sensitive filesystem a path written
    in another case is judged outside, so it cannot reach a folder next to the root.
    """
    if _expands(path):
        return False
    real = _real(path, cwd)
    if any(real == root or root in real.parents for root in roots):
        return True
    return any(_ignores_case(root) and _folded_under(real, root, str.lower) for root in roots)


def _ignores_case(folder: Path) -> bool:
    """Whether the filesystem holding ``folder`` opens a name in either case.

    The default filesystems on macOS and Windows do; ``Path`` comparison and
    ``realpath`` there still compare case, so a check that refuses a folder has
    to fold it. Judged on the nearest folder that exists.
    """
    probe = folder
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    flipped = Path(str(probe).swapcase())
    if str(flipped) == str(probe):
        return os.name == "nt" or sys.platform == "darwin"
    try:
        return flipped.exists() and os.path.samefile(flipped, probe)
    except OSError:
        return False


def under_any(path: Path, roots: list[Path]) -> bool:
    """Whether ``path`` is one of ``roots`` or inside one, the way the filesystem
    reads names: a refuse check, so names are folded where the filesystem ignores
    case."""
    for root in roots:
        if path == root or root in path.parents:
            return True
        if _ignores_case(root) and _folded_under(path, root, str.casefold):
            return True
    return False


def python_code_dirs() -> list[Path]:
    """Where the scripts' Python loads code from: its install, its site-packages
    and every folder on ``sys.path`` (an editable install puts the repository's
    source there). A file written in one of them runs with the next import."""
    found = {sys.prefix, sys.exec_prefix, sys.base_prefix, sys.base_exec_prefix}
    try:
        found.update(site.getsitepackages())
    except AttributeError:  # some virtualenv builds have no getsitepackages
        pass
    user_site = site.getusersitepackages()
    if isinstance(user_site, str):
        found.add(user_site)
    found.update(entry for entry in sys.path if entry and os.path.isabs(entry))
    dirs = []
    for entry in found:
        real = Path(os.path.realpath(entry))
        if real.is_dir() and real.parent != real:  # never a whole drive
            dirs.append(real)
    return sorted(set(dirs))


#: Path forms Windows opens as a different file from the one the name shows: a
#: drive-relative path (``C:out``), a stream (``x:stream``), a device or UNC
#: path (``//?/``, ``\\server``), and a name ending in a dot or a space, which
#: Windows drops. Refused on every system, where they are only stricter.
_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")


def odd_path_form(path: str) -> bool:
    """A path whose meaning differs between the guard and the program it reaches."""
    if path.startswith(("//", "\\\\")):
        return True
    rest = path[2:] if _DRIVE.match(path) else path
    if ":" in rest:
        return True
    parts = [p for p in re.split(r"[\\/]", rest) if p not in ("", ".", "..")]
    return any(p[-1] in ". " for p in parts)


def _is_link(path: str) -> bool:
    isjunction = getattr(os.path, "isjunction", None)
    return os.path.islink(path) or bool(isjunction and isjunction(path))


def find_link(folders: list[Path]) -> Path | None:
    """The first link or junction a script writing in ``folders`` would follow.

    That is one of the folders, or an entry directly in one: a file the script
    writes, or a folder it writes under (which is then in ``folders`` itself).
    Nothing else is looked at, so a virtual environment the user made in the
    output folder (its ``bin/python`` is a link) does not stop the scripts.
    """
    for folder in folders:
        if _is_link(str(folder)):
            return folder
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    if _is_link(entry.path):
                        return Path(entry.path)
        except (FileNotFoundError, NotADirectoryError):
            continue  # not made yet, or a file the script will refuse
    return None


class ToolGuard:
    """Per-session rules; ``hook`` is registered as the agent's PreToolUse hook."""

    def __init__(
        self,
        wizard_dir: Path,
        output_dir: Path,
        *,
        blueprint_check: BlueprintCheck | None = None,
        scripts: dict[str, dict[str, str]] | None = None,
        left_out: dict[str, str] | None = None,
        extra_tools: frozenset[str] = frozenset(),
        protected: list[Path] | None = None,
        writes: dict[str, list[str]] | None = None,
    ) -> None:
        self.cwd = Path(os.path.realpath(wizard_dir))
        self.output = Path(os.path.realpath(output_dir))
        self.readable = [self.output, self.cwd]
        self.writable = [self.output]
        #: Never written, even when the output folder holds them: the wizard's
        #: own files, where the scripts' Python loads code from, and the
        #: caller's own (the runner adds the repository).
        self.protected = sorted(
            {self.cwd, *python_code_dirs(), *(Path(os.path.realpath(p)) for p in protected or [])}
        )
        self.blueprint_check = blueprint_check
        self.scripts = scripts if scripts is not None else load_scripts()
        self.left_out = left_out if left_out is not None else load_left_out()
        #: The folders each script writes into, checked for links before it runs.
        self.writes = writes if writes is not None else load_writes()
        #: The caller's own tools (v2's in-process gate tools), which check
        #: their own input.
        self.extra_tools = extra_tools

    async def hook(self, input_data: Any, tool_use_id: str | None, context: Any) -> dict[str, Any]:
        try:
            tool = input_data.get("tool_name", "")
            tool_input = input_data.get("tool_input") or {}
            reason = self.check(tool, tool_input if isinstance(tool_input, dict) else {})
        except Exception:  # noqa: BLE001 - a call the rules cannot decide does not run
            logger.exception("tool guard could not decide a call; refusing it")
            reason = "The wizard could not check this tool call, so it was not run."
        return _deny(reason) if reason else {}

    def _env_file(self, path: str) -> bool:
        """A .env file by the name as written or by the name of the file it opens."""
        if is_env_file(path):
            return True
        return not _expands(path) and is_env_file(str(_real(path, self.cwd)))

    def _writable(self, path: str) -> bool:
        """In the output folder, and not in a protected folder even when the
        output folder holds one."""
        if odd_path_form(path) or not _inside(path, self.writable, self.cwd):
            return False
        return not under_any(_real(path, self.cwd), self.protected)

    def check(self, tool: str, tool_input: dict[str, Any]) -> str | None:
        """Why the call is refused, or None when it may run."""
        if tool in _HARMLESS_TOOLS or tool in self.extra_tools:
            return None
        if tool in _WRITE_TOOLS:
            path = tool_input.get(_WRITE_TOOLS[tool]) or ""
            if path and self._env_file(path):
                return "The wizard does not write .env files; write .env.example instead."
            if not path or not self._writable(path):
                return f"Files can be written only in the output folder {self.output.as_posix()}."
            return None
        if tool in _READ_TOOLS:
            paths = [tool_input.get(_READ_TOOLS[tool]) or str(self.cwd)]
            pattern = tool_input.get("pattern")
            if tool == "Glob" and isinstance(pattern, str):
                if ".." in Path(pattern).parts:
                    return "Glob patterns may not climb out of their directory with '..'."
                if is_env_file(pattern):
                    return "The wizard does not read .env files; they hold keys."
                if _expands(pattern) or pattern.startswith("{"):
                    return "Glob patterns must be plain paths under an allowed directory."
                if os.path.isabs(pattern):
                    paths.append(pattern.split("*", 1)[0] or "/")
            if tool in {"Grep", "Glob"} and isinstance(tool_input.get("glob"), str):
                if is_env_file(tool_input["glob"]):
                    return "The wizard does not read .env files; they hold keys."
            if any(self._env_file(p) for p in paths):
                return "The wizard does not read .env files; they hold keys."
            if not all(_inside(p, self.readable, self.cwd) for p in paths):
                return (
                    f"Files can be read only in the output folder {self.output.as_posix()} "
                    "and in the wizard's own files."
                )
            if tool == "Grep":
                folder = _native(paths[0])
                folder_path = Path(folder) if os.path.isabs(folder) else self.cwd / folder
                if folder_path.is_dir() and _has_env_file(folder_path):
                    return (
                        "This folder has a .env file, which holds keys, and Grep would read "
                        "it: search a file, or a folder without one (for example poc/schemas)."
                    )
            return None
        if tool == "Bash":
            return self._check_bash(str(tool_input.get("command") or ""))
        return f"The {tool} tool is not available in the wizard."

    def _check_bash(self, command: str) -> str | None:
        allowed = (
            "Bash runs only the wizard's scripts, one plain command at a time, e.g. "
            "`python scripts/validate_blueprint.py --blueprint "
            f"{self.output.as_posix()}/use_case.blueprint.json` (forward slashes, no quotes "
            "needed). Use the Read, Write, Edit, Glob and Grep tools for files."
        )
        command = _CONTINUATION.sub(" ", command).strip()
        whole = _ONE_LINER_COMMAND.match(command)
        if whole:
            return self._check_one_liner(whole.group(1), allowed)
        if _SHELL_SYNTAX.search(command):
            return "No shell operators, redirection, variables, backslashes or globs. " + allowed
        try:
            argv = shlex.split(command)
        except ValueError:
            return allowed
        if len(argv) < 2 or argv[0] not in _PYTHON:
            return allowed
        script = argv[1]
        name = Path(script).name
        if name in self.left_out and name not in self.scripts:
            return f"{name} is not run by the agent here: {self.left_out[name]}."
        options = self.scripts.get(Path(script).name)
        if options is None or not _inside(script, [self.cwd / "scripts"], self.cwd):
            return allowed
        if argv[2:] == ["--help"]:
            return None  # argparse lists the options and exits before the script runs
        given = self._options(argv[2:], options)
        if isinstance(given, str):
            return f"{given} {Path(script).name} takes {', '.join(options)}. " + allowed
        for option, value in given.items():
            kind = options[option]
            if kind == _PATH and (self._env_file(value) or not self._writable(value)):
                return f"{option} must be in the output folder {self.output.as_posix()}. " + allowed
            if kind == _URL and not endpoint_ok(value):
                return (
                    f"{option} must be a provider's own https endpoint; leave it out to use "
                    "the endpoint configured in the environment. " + allowed
                )
        if name not in self.writes:
            # Without an entry the guard cannot tell where the script writes, so it
            # cannot check those folders for links: not run rather than unchecked.
            return (
                f"{name} has no entry under 'writes' in scripts/agent_scripts.json, so the "
                "wizard cannot check the folders it writes into; it is not run."
            )
        link = find_link(self._written_folders(name, given))
        if link is not None:
            return (
                f"{link.as_posix()} is a link or junction where {name} writes, and the "
                "script would follow it. Remove that link first. " + allowed
            )
        if name in _SCAFFOLDING_SCRIPTS:
            return self._check_blueprint(given)
        return None

    def _written_folders(self, script: str, given: dict[str, str]) -> list[Path]:
        """The folders ``script`` writes into with these options (``writes`` in
        agent_scripts.json): under its --output-dir, or without one where it
        writes instead, the --blueprint's folder or, for the scaffolder, the
        blueprint's package.output_dir."""
        subfolders = self.writes[script]
        if "--output-dir" in given:
            base = _real(given["--output-dir"], self.cwd)
        elif "--blueprint" in given:
            base = _real(given["--blueprint"], self.cwd).parent
            if script in _SCAFFOLDING_SCRIPTS:
                package = (self._read_blueprint(given["--blueprint"]) or {}).get("package")
                output_dir = package.get("output_dir") if isinstance(package, dict) else None
                # One outside the output folder is refused by _check_blueprint.
                if isinstance(output_dir, str) and output_dir and self._writable(output_dir):
                    base = _real(output_dir, self.cwd)
        else:
            return []  # the script stops without them
        return [base if sub == "." else base / sub for sub in subfolders]

    def _read_blueprint(self, path: str) -> dict[str, Any] | None:
        """The blueprint at ``path`` as JSON, or None when it cannot be read."""
        path = _native(path)
        target = Path(path) if os.path.isabs(path) else self.cwd / path
        try:
            blueprint = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return blueprint if isinstance(blueprint, dict) else None

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
                if one_liner is _ONE_LINERS[0] and (
                    self._env_file(match.group(1))
                    or not _inside(match.group(1), self.readable, self.cwd)
                ):
                    return allowed
                return None
        return allowed

    def _check_blueprint(self, given: dict[str, str]) -> str | None:
        """Where the scaffolder writes, and the caller's own blueprint check."""
        path = given.get("--blueprint")
        if path is None:
            return None  # the script refuses to run without one
        blueprint = self._read_blueprint(path)
        if blueprint is None:
            return None  # the script reports an unreadable blueprint itself
        if "--output-dir" not in given:
            # Without --output-dir the scaffolder writes where the blueprint says.
            package = blueprint.get("package")
            output_dir = package.get("output_dir") if isinstance(package, dict) else None
            if output_dir and not self._writable(str(output_dir)):
                return (
                    "The blueprint's package.output_dir is outside the output folder; pass "
                    f"--output-dir {self.output.as_posix()} or fix package.output_dir."
                )
        if self.blueprint_check is not None:
            return self.blueprint_check(blueprint)
        return None
