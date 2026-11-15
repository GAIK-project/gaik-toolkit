#!/usr/bin/env python3
"""Interactive CLI session for the GAIK Solution Configuration Wizard.

Starts a persistent conversation with the wizard. The wizard asks questions
at each phase and gate; you type answers and press Enter. The session continues
until the wizard completes (or you press Ctrl+C / Ctrl+D).

--- Prerequisites -----------------------------------------------------------

1. Install the wizard runner extras (once):

       pip install "gaik[wizard]"        # installs claude-agent-sdk + python-dotenv

   Or install them directly:

       pip install claude-agent-sdk python-dotenv

2. The `claude` Code CLI must be on PATH (the SDK spawns it as a subprocess):

       # Verify:
       claude --version

   Install if missing: https://docs.anthropic.com/en/claude-code/setup

--- Credentials (.env) ------------------------------------------------------

The script reads credentials from ../.env (one directory above this file, i.e.
implementation_layer/.env) by default.  Copy the template and fill in your values:

    cp .env.example ../.env      # then edit ../.env

Required variables:

    CLAUDE_CODE_USE_FOUNDRY=1
    ANTHROPIC_FOUNDRY_API_KEY=<your Azure Foundry API key>
    ANTHROPIC_FOUNDRY_RESOURCE=<your Foundry resource name, e.g. my-foundry-resource>

Recommended (model selection):

    ANTHROPIC_DEFAULT_SONNET_MODEL=claude-sonnet-5-5

Optional (timeouts / telemetry):

    API_TIMEOUT_MS=600000
    CLAUDE_CODE_MAX_RETRIES=2
    DISABLE_TELEMETRY=1

Run the preflight check to verify credentials before a full session:

    python run_wizard_interactive.py --preflight

--- Usage -------------------------------------------------------------------

    # Wizard asks for the output directory interactively:
    python run_wizard_interactive.py

    # Pre-supply the output directory (skips that question):
    python run_wizard_interactive.py --output-dir C:\\projects\\my-use-case

    # Use a different .env file:
    python run_wizard_interactive.py --env-file path/to/.env

    # Override the model:
    python run_wizard_interactive.py --model claude-sonnet-5-5

    # Pass one more environment variable to the agent (repeatable):
    python run_wizard_interactive.py --pass-env AZURE_CLIENT_ID

--- What the agent may do ----------------------------------------------------

The agent gets the Read, Grep, Glob, Write, Edit and Bash tools and nothing else.

- Write and Edit run without asking inside the output directory you gave with
  --output-dir, or a folder you approved when the wizard first wrote there (that
  folder and its subfolders; never your home folder or a drive root as a whole).
  Writes anywhere else, and every change to the wizard's own files, ask you first.
- Read, Grep and Glob run without asking in the wizard folder and in the folders
  the wizard may write; a new folder asks once, and .env files are never read.
- Bash runs without asking only for the wizard's own scripts
  (`python scripts/<name>.py ...`, see WIZARD_SCRIPTS) with the options in
  _SCRIPT_OPTIONS written in full, --blueprint and --output-dir in a folder the
  wizard may write and no URL. Any other command is shown to you first and
  runs only if you answer y.
- Every other tool is refused.

The agent's process gets only the environment variables listed in
AGENT_ENV_VARS (system basics, the Claude Code provider settings and the gaik
provider settings the wizard's scripts read), plus any --pass-env names.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shlex
import sys
import threading
from collections.abc import Awaitable, Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    query,
)
from dotenv import dotenv_values

WIZARD_DIR = Path(__file__).resolve().parent

REQUIRED_ENV_VARS = [
    "CLAUDE_CODE_USE_FOUNDRY",
    "ANTHROPIC_FOUNDRY_API_KEY",
    "ANTHROPIC_FOUNDRY_RESOURCE",
]
DEFAULT_MODEL = "claude-sonnet-5-5"

# ── ANSI colours (suppressed on non-TTY / Windows without ANSI support) ──────


def _supports_colour() -> bool:
    return sys.stdout.isatty() and os.name != "nt" or os.environ.get("FORCE_COLOR")


RESET = "\033[0m" if _supports_colour() else ""
BOLD = "\033[1m" if _supports_colour() else ""
DIM = "\033[2m" if _supports_colour() else ""
CYAN = "\033[36m" if _supports_colour() else ""
YELLOW = "\033[33m" if _supports_colour() else ""
GREEN = "\033[32m" if _supports_colour() else ""
RED = "\033[31m" if _supports_colour() else ""


# ── Environment ───────────────────────────────────────────────────────────────


# The only environment variables the agent's process receives. The Claude Agent
# SDK starts the CLI with this process's environment, so run_interactive() and the
# preflight also narrow os.environ to this set before they start it.
AGENT_ENV_VARS = frozenset(
    {
        # System basics (POSIX and Windows) the CLI, its shell and Python need.
        "PATH",
        "PATHEXT",
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "TERM",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TZ",
        "TMPDIR",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "WINDIR",
        "COMSPEC",
        # Network settings for a proxy or a company certificate.
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "NODE_EXTRA_CA_CERTS",
        # The Python environment the wizard's scripts run in.
        "VIRTUAL_ENV",
        "CONDA_PREFIX",
        "CONDA_DEFAULT_ENV",
        "PYTHONPATH",
        "PYTHONUTF8",
        "PYTHONIOENCODING",
        "PYENV_VERSION",
        # Claude Code: the Foundry provider, model choice and run settings.
        "CLAUDE_CODE_USE_FOUNDRY",
        "ANTHROPIC_FOUNDRY_API_KEY",
        "ANTHROPIC_FOUNDRY_RESOURCE",
        "ANTHROPIC_FOUNDRY_BASE_URL",
        "ANTHROPIC_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "ANTHROPIC_SMALL_FAST_MODEL",
        "API_TIMEOUT_MS",
        "CLAUDE_CODE_MAX_RETRIES",
        "CLAUDE_CODE_GIT_BASH_PATH",
        "CLAUDE_CONFIG_DIR",
        "DISABLE_TELEMETRY",
        "CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR",
        # gaik providers, for the scripts that call a model (generate_schema.py).
        "LLM_PROVIDER",
        "AZURE_API_KEY",
        "AZURE_ENDPOINT",
        "AZURE_API_VERSION",
        "AZURE_DEPLOYMENT",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_MODEL",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "AITTA_API_KEY",
        "AITTA_API_TOKEN",
        "AITTA_TOKEN",
        "AITTA_BASE_URL",
        "AITTA_MODEL",
        "LITELLM_API_KEY",
        "LITELLM_API_VERSION",
        "LITELLM_BASE_URL",
        "LITELLM_MODEL",
        "EMBEDDING_MODEL",
        "ANTHROPIC_MAX_TOKENS",
        "GOOGLE_GEMINI_API_KEY",
        "GOOGLE_VERTEXAI_PROJECT",
        "GOOGLE_VERTEXAI_LOCATION",
        "GOOGLE_GENERATE_CONTENT_URL",
        "GOOGLE_PROJECT_ID",
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        "GOOGLE_SCOPES",
        "AITTA_EMBEDDING_MODEL",
        "LITELLM_EMBEDDING_MODEL",
        "AZURE_TRANSCRIPTION_MODEL",
        "OPENAI_TRANSCRIPTION_MODEL",
    }
)


def build_agent_env(source: Mapping[str, str], extra_names: Iterable[str] = ()) -> dict[str, str]:
    """Return the variables of ``source`` the agent may see, with run defaults."""
    names = AGENT_ENV_VARS | set(extra_names)
    env = {k: v for k, v in source.items() if k in names and v is not None}
    env.setdefault("API_TIMEOUT_MS", "600000")
    env.setdefault("CLAUDE_CODE_MAX_RETRIES", "2")
    env.setdefault("DISABLE_TELEMETRY", "1")
    # Each Bash call starts in the wizard folder, so `python scripts/...` always
    # names the wizard's own scripts.
    env["CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR"] = "1"
    return env


def load_environment(env_file: Path, extra_names: Iterable[str] = ()) -> dict[str, str]:
    source = dict(os.environ)
    if env_file.exists():
        # Like load_dotenv: a variable already set in the shell wins over the file.
        for key, value in dotenv_values(env_file).items():
            if value is not None:
                source.setdefault(key, value)
    else:
        print(f"{DIM}(no .env at {env_file} — using current shell env){RESET}", file=sys.stderr)

    missing = [k for k in REQUIRED_ENV_VARS if not (source.get(k) or "").strip()]
    if missing:
        raise RuntimeError(
            f"{RED}Missing Foundry env vars: {', '.join(missing)}{RESET}\n"
            f"Copy .env.example → .env and fill them in."
        )

    return build_agent_env(source, extra_names)


def narrow_process_environment(env: Mapping[str, str]) -> None:
    """Leave only ``env`` in os.environ, which the SDK passes on to the agent."""
    os.environ.clear()
    os.environ.update(env)


# ── What the agent may do ─────────────────────────────────────────────────────

# The tools the agent has at all. WizardPermissions decides each call.
AGENT_TOOLS = ["Read", "Grep", "Glob", "Write", "Edit", "Bash"]
READ_TOOLS = ("Read", "Grep", "Glob")
ENV_FILE_RULES = ("Read(**/.env)", "Read(**/.env.*)")
WRITE_TOOLS = ("Write", "Edit")

# The scripts SKILL.md runs, as `python scripts/<name>`, that write only into the
# use case's folder. They run without asking while their --blueprint and
# --output-dir are in a folder the wizard may write. promote_template.py is left
# out on purpose: it writes into the wizard's own template library, so it asks.
WIZARD_SCRIPTS = frozenset(
    {
        "check_requirements.py",
        "generate_bpmn.py",
        "generate_docs.py",
        "generate_mermaid.py",
        "generate_schema.py",
        "run_wizard.py",
        "scaffold_poc.py",
        "validate_blueprint.py",
    }
)
PYTHON_COMMANDS = frozenset({"python", "python3"})
# The options a listed script may get without asking, spelled out in full: argparse
# would also take an abbreviation, which then escapes the checks below. Left out
# on purpose: --base-url (sends the provider key to another host) and
# --export-schema (writes into the wizard's own schemas/ folder).
_SCRIPT_OPTIONS = frozenset(
    {
        "--blueprint",
        "--output-dir",
        "--requirements",
        "--schema-name",
        "--provider",
        "--use-azure",
        "--no-azure",
        "--model",
        "--synthetic",
        "--skip-validation",
        "--show-registry",
    }
)
# Options that name where a script writes, and files a script reads.
_WRITE_PATH_OPTIONS = ("--blueprint", "--output-dir")
_READ_PATH_OPTIONS = ("--requirements",)
# Characters that would let a command do more than run one script with the
# arguments as written: control operators, expansions, globs and braces.
_SHELL_CONTROL = set(";&|<>`$\n\r{}*?[]~")

# The wizard's own files and folders. The agent reads SKILL.md as its instructions
# and the scripts above run without asking, so a change here always asks.
WIZARD_OWN_ENTRIES = frozenset(
    {
        "CLAUDE.md",
        "README.md",
        "SKILL.md",
        "docs",
        "examples",
        "gaik_validated_version.txt",
        "images",
        "registries",
        "run_wizard_interactive.py",
        "schemas",
        "scripts",
        "src",
        "templates",
        "tests",
    }
)


def _is_within(path: Path, folder: Path) -> bool:
    return path == folder or folder in path.parents


def _is_env_file(name: str) -> bool:
    return name == ".env" or name.startswith(".env.")


def _names_env_file(tool_name: str, tool_input: Mapping[str, Any]) -> bool:
    """Whether a Read, Grep or Glob call names a .env file or a pattern for one."""
    for key in ("file_path", "path"):
        value = tool_input.get(key)
        if value and _is_env_file(Path(str(value)).name):
            return True
    pattern_key = "pattern" if tool_name == "Glob" else "glob"
    return ".env" in str(tool_input.get(pattern_key) or "")


def _resolve(path_text: str, base: Path) -> Path:
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def script_command_argv(command: str, wizard_dir: Path = WIZARD_DIR) -> list[str] | None:
    """The argv of ``command`` when it only runs one listed wizard script, else None."""
    # SKILL.md writes long commands over several lines with a trailing backslash.
    command = command.replace("\\\r\n", " ").replace("\\\n", " ")
    if not command or any(ch in _SHELL_CONTROL for ch in command):
        return None
    try:
        argv = shlex.split(command)
    except ValueError:
        return None
    if len(argv) < 2 or argv[0] not in PYTHON_COMMANDS:
        return None
    try:
        script = _resolve(argv[1], wizard_dir)
        scripts_dir = (wizard_dir / "scripts").resolve()
    except OSError:
        return None
    if script.parent != scripts_dir or script.name not in WIZARD_SCRIPTS:
        return None
    for arg in argv[2:]:
        if "://" in arg:
            return None
        if arg.startswith("-") and arg.split("=", 1)[0] not in _SCRIPT_OPTIONS:
            return None
    return argv


def script_path_arguments(argv: list[str], options: Iterable[str]) -> list[str]:
    """The values in ``argv`` of the given path ``options``."""
    values = []
    for i, arg in enumerate(argv):
        for option in options:
            if arg == option:
                values.append(argv[i + 1] if i + 1 < len(argv) else "")
            elif arg.startswith(option + "="):
                values.append(arg[len(option) + 1 :])
    return values


def is_wizard_script_command(command: str, wizard_dir: Path = WIZARD_DIR) -> bool:
    """True when ``command`` only runs one listed wizard script with arguments."""
    return script_command_argv(command, wizard_dir) is not None


AskUser = Callable[[str], Awaitable[bool]]


async def ask_user_in_terminal(question: str) -> bool:
    """Ask a yes/no question on the terminal; no answer (EOF) means no."""
    loop = asyncio.get_running_loop()
    answer: asyncio.Future[bool] = loop.create_future()

    def _ask() -> None:
        print(f"\n{YELLOW}{question} [y/N]{RESET} ", end="", flush=True)
        try:
            line = sys.stdin.readline()
            result = line.strip().lower() in {"y", "yes"}
        except Exception:
            result = False
        loop.call_soon_threadsafe(lambda: answer.done() or answer.set_result(result))

    # A daemon thread, not the default executor: on Ctrl+C asyncio.run would wait
    # for a blocked readline in the executor before the runner could exit.
    threading.Thread(target=_ask, daemon=True).start()
    return await answer


class WizardPermissions:
    """Decides every tool call of the session (``can_use_tool``)."""

    def __init__(
        self,
        output_dir: Path | None,
        ask: AskUser = ask_user_in_terminal,
        wizard_dir: Path = WIZARD_DIR,
    ) -> None:
        self.wizard_dir = wizard_dir.resolve()
        self.ask = ask
        self.write_dirs: list[Path] = [output_dir.resolve()] if output_dir else []
        self.read_dirs: list[Path] = []
        # The SDK may ask about several tool calls at once. Deciding one at a time
        # keeps the questions apart and lets a yes for a folder cover the next call.
        self._lock = asyncio.Lock()

    def is_wizard_own(self, path: Path) -> bool:
        if not _is_within(path, self.wizard_dir) or path == self.wizard_dir:
            return path == self.wizard_dir
        parts = path.relative_to(self.wizard_dir).parts
        if parts[0] in WIZARD_OWN_ENTRIES:
            return True
        # Any other file directly in the wizard folder, but not an output folder there.
        return len(parts) == 1 and path not in self.write_dirs

    def _holds_wizard_files(self, folder: Path) -> bool:
        if not _is_within(folder, self.wizard_dir) or folder == self.wizard_dir:
            return folder == self.wizard_dir
        return folder.relative_to(self.wizard_dir).parts[0] in WIZARD_OWN_ENTRIES

    def may_write(self, path: Path) -> bool:
        return not self.is_wizard_own(path) and any(_is_within(path, d) for d in self.write_dirs)

    def may_read(self, path: Path) -> bool:
        if _is_env_file(path.name):
            return False
        if _is_within(path, self.wizard_dir):
            return True
        return any(_is_within(path, d) for d in (*self.write_dirs, *self.read_dirs))

    @staticmethod
    def _rememberable(folder: Path) -> bool:
        """Whether a yes for ``folder`` may cover later calls in it and below it."""
        home = Path.home().resolve()
        return folder != Path(folder.anchor) and not _is_within(home, folder)

    async def _decide_write(self, tool_name: str, tool_input: dict[str, Any]):
        file_path = str(tool_input.get("file_path") or "")
        if not file_path:
            return PermissionResultDeny(message=f"{tool_name} needs a file_path.")
        target = _resolve(file_path, self.wizard_dir)
        if self.is_wizard_own(target):
            # Always asked and never remembered.
            if await self.ask(f"Allow {tool_name} on the wizard's own file {target}?"):
                return PermissionResultAllow()
            return PermissionResultDeny(message="The user declined this change.")
        if self.may_write(target):
            return PermissionResultAllow()
        folder = target.parent
        if not self._rememberable(folder) or self._holds_wizard_files(folder):
            if await self.ask(f"Allow {tool_name} on {target}?"):
                return PermissionResultAllow()
            return PermissionResultDeny(message=f"The user declined writing {target}.")
        if await self.ask(f"Allow the wizard to write files in {folder} and its subfolders?"):
            self.write_dirs.append(folder)
            return PermissionResultAllow()
        return PermissionResultDeny(message=f"The user declined writing in {folder}.")

    def _read_target(self, tool_name: str, tool_input: dict[str, Any]) -> Path | None:
        if tool_name == "Read":
            text = str(tool_input.get("file_path") or "")
            return _resolve(text, self.wizard_dir) if text else None
        pattern = str(tool_input.get("pattern" if tool_name == "Glob" else "glob") or "")
        if pattern.startswith(("/", "~", "\\")) or ".." in pattern or ":" in pattern:
            return None  # a pattern that leaves its folder: ask about it as is
        return _resolve(str(tool_input.get("path") or "."), self.wizard_dir)

    async def _decide_read(self, tool_name: str, tool_input: dict[str, Any]):
        if _names_env_file(tool_name, tool_input):
            return PermissionResultDeny(message="The wizard does not read .env files.")
        target = self._read_target(tool_name, tool_input)
        if target is not None and self.may_read(target):
            return PermissionResultAllow()
        if target is None:
            if await self.ask(f"Allow {tool_name} with {tool_input}?"):
                return PermissionResultAllow()
            return PermissionResultDeny(message="The user declined this read.")
        folder = target if tool_name != "Read" else target.parent
        if not self._rememberable(folder):
            if await self.ask(f"Allow {tool_name} on {target}?"):
                return PermissionResultAllow()
            return PermissionResultDeny(message=f"The user declined reading {target}.")
        if await self.ask(f"Allow the wizard to read files in {folder} and its subfolders?"):
            self.read_dirs.append(folder)
            return PermissionResultAllow()
        return PermissionResultDeny(message=f"The user declined reading in {folder}.")

    def _runs_without_asking(self, command: str) -> bool:
        argv = script_command_argv(command, self.wizard_dir)
        if argv is None:
            return False
        for value in script_path_arguments(argv, _WRITE_PATH_OPTIONS):
            if not value or not self.may_write(_resolve(value, self.wizard_dir)):
                return False
        for value in script_path_arguments(argv, _READ_PATH_OPTIONS):
            if not value or not self.may_read(_resolve(value, self.wizard_dir)):
                return False
        return True

    async def _decide_bash(self, tool_input: dict[str, Any]):
        command = str(tool_input.get("command") or "")
        if self._runs_without_asking(command):
            return PermissionResultAllow()
        if await self.ask(f"Allow this command?\n  {command}\n"):
            return PermissionResultAllow()
        return PermissionResultDeny(message="The user declined this command.")

    async def __call__(self, tool_name: str, tool_input: dict[str, Any], context: Any):
        async with self._lock:
            return await self._decide(tool_name, tool_input)

    async def _decide(self, tool_name: str, tool_input: dict[str, Any]):
        if tool_name in READ_TOOLS:
            return await self._decide_read(tool_name, tool_input)
        if tool_name in WRITE_TOOLS:
            return await self._decide_write(tool_name, tool_input)
        if tool_name == "Bash":
            return await self._decide_bash(tool_input)
        return PermissionResultDeny(message=f"The wizard does not use {tool_name}.")


def build_session_options(
    env: dict[str, str],
    model: str,
    output_dir: Path | None,
    ask: AskUser = ask_user_in_terminal,
) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        cwd=str(WIZARD_DIR),
        add_dirs=[str(output_dir)] if output_dir else [],
        env=env,
        model=model,
        tools=list(AGENT_TOOLS),
        # No allow rules, so every call the CLI would ask about reaches
        # WizardPermissions (the CLI itself lets reads in cwd and add_dirs through).
        allowed_tools=[],
        # The CLI also applies these to the files a Grep or Glob over a folder opens.
        disallowed_tools=list(ENV_FILE_RULES),
        permission_mode="default",
        can_use_tool=WizardPermissions(output_dir, ask=ask),
        setting_sources=[],  # isolate from repo CLAUDE.md / graphify noise
    )


def build_preflight_options(env: dict[str, str], model: str) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        cwd=str(WIZARD_DIR),
        env=env,
        model=model,
        tools=[],
        allowed_tools=[],
        permission_mode="default",
        setting_sources=[],
        max_turns=1,
    )


def resolve_model(env: dict[str, str], cli_model: str | None) -> str:
    return (
        cli_model
        or env.get("ANTHROPIC_MODEL")
        or env.get("ANTHROPIC_DEFAULT_SONNET_MODEL")
        or DEFAULT_MODEL
    ).strip()


def guard_nested_session(allow_nested: bool, env: dict[str, str]) -> None:
    if not (os.environ.get("CLAUDECODE") or env.get("CLAUDECODE")):
        return
    if not allow_nested:
        raise RuntimeError(
            f"{RED}Detected CLAUDECODE — cannot spawn a nested Claude Code session.{RESET}\n"
            "Run from a normal terminal where CLAUDECODE is not set.\n"
            "Pass --allow-nested to override (may disrupt the parent session)."
        )
    for k in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"):
        env.pop(k, None)


# ── Output printing ───────────────────────────────────────────────────────────


def _print_text(text: str) -> None:
    """Print wizard text in cyan so it's visually distinct from the user prompt."""
    print(f"{CYAN}{text}{RESET}", end="", flush=True)


def _print_tool_use(name: str, inp: str) -> None:
    truncated = inp if len(inp) <= 200 else inp[:200] + " …"
    print(f"\n{DIM}[running: {name}  {truncated}]{RESET}", flush=True)


def _print_tool_result(content: str) -> None:
    if len(content) > 600:
        content = content[:600] + "\n… [truncated]"
    print(f"{DIM}{content}{RESET}", flush=True)


def _print_result(message: ResultMessage) -> None:
    print()  # blank line after the last streamed text
    if message.is_error:
        print(f"\n{RED}--- Session ended with error (stop: {message.stop_reason}) ---{RESET}")
        if message.result:
            print(message.result)
    else:
        print(f"\n{GREEN}--- Wizard session complete ---{RESET}")
        print(
            f"{DIM}Turns: {message.num_turns}  |  "
            f"Session: {message.session_id}"
            + (f"  |  Cost: ${message.total_cost_usd:.4f}" if message.total_cost_usd else "")
            + RESET
        )


# ── Input ─────────────────────────────────────────────────────────────────────


def _read_user_input() -> str | None:
    """Prompt the user and return their input, or None on EOF/Ctrl+D."""
    try:
        print(f"\n{BOLD}You:{RESET} ", end="", flush=True)
        line = sys.stdin.readline()
        if not line:  # EOF / Ctrl+D
            return None
        return line.rstrip("\n")
    except KeyboardInterrupt:
        return None


async def _drain_response(client: ClaudeSDKClient) -> ResultMessage | None:
    """Stream one wizard turn to stdout.

    Returns None when the turn ended normally (wizard is waiting for the next
    user message). Returns the ResultMessage when the turn ended with an error
    (so the caller knows to stop the loop).

    A normal-success ResultMessage means "I finished responding — your turn."
    It does NOT mean the session is over, so we never stop the loop on success.
    """
    async for message in client.receive_response():
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    _print_text(block.text)
                elif isinstance(block, ToolUseBlock):
                    inp = str(block.input)
                    _print_tool_use(block.name, inp)
                elif isinstance(block, ToolResultBlock):
                    _print_tool_result(str(block.content))
        elif isinstance(message, ResultMessage):
            if message.is_error:
                _print_result(message)
                return message  # error — caller should stop
            # Normal turn end: wizard is waiting for user input.
            # Return None so the conversation loop continues.
            return None
    return None


# ── Initial prompt ────────────────────────────────────────────────────────────


def build_initial_prompt(output_dir: Path | None) -> str:
    """The first message that invokes the wizard skill and sets up the session."""
    output_hint = (
        (
            f"\nThe user has pre-selected this output directory: {output_dir}\n"
            "Skip the directory question and use it directly."
        )
        if output_dir
        else ""
    )

    return f"""\
/solution-wizard

You are starting an interactive GAIK Solution Configuration Wizard session.
Load and follow the complete wizard instructions from ./SKILL.md (you are already
in the wizard directory). {output_hint}

Begin Phase 1: introduce yourself briefly, then ask the user for the output
directory (unless already provided above) and their use-case description.
Wait for each answer before asking the next question -- this is an interactive
conversation, one or two questions at a time.
""".strip()


# ── Main interactive loop ─────────────────────────────────────────────────────


async def run_interactive(
    env: dict[str, str],
    model: str,
    output_dir: Path | None,
) -> int:
    options = build_session_options(env, model, output_dir)
    narrow_process_environment(env)

    print(f"{BOLD}GAIK Solution Configuration Wizard{RESET}")
    print(f"{DIM}Model: {model}  |  Wizard dir: {WIZARD_DIR}")
    if output_dir:
        print(f"Output dir: {output_dir}")
    print(f"Ctrl+C or Ctrl+D to exit{RESET}\n")

    async with ClaudeSDKClient(options=options) as client:
        # ── First turn: invoke the skill, get the wizard's opening message ──
        initial_prompt = build_initial_prompt(output_dir)
        await client.query(initial_prompt)
        error_result = await _drain_response(client)

        # ── Conversation loop ────────────────────────────────────────────────
        # _drain_response returns None on a normal turn end (wizard is waiting)
        # and a ResultMessage on error. Loop until error or user exits.
        while error_result is None:
            user_input = _read_user_input()
            if user_input is None:  # EOF or Ctrl+D
                print(f"\n{YELLOW}(session ended by user){RESET}")
                break
            if not user_input.strip():
                continue  # ignore blank lines

            await client.query(user_input)
            error_result = await _drain_response(client)

        if error_result is None:
            # Clean user exit — print a minimal summary.
            print(f"\n{DIM}Session ended.{RESET}")
        # Error case: _print_result was already called inside _drain_response.

    return 0


async def run_preflight(env: dict[str, str], model: str) -> int:
    """Send one tiny request with the session's settings and no tools."""
    opts = build_preflight_options(env, model)
    narrow_process_environment(env)
    async for msg in query(prompt="Reply with the single word: READY", options=opts):
        if isinstance(msg, AssistantMessage):
            for b in msg.content:
                if hasattr(b, "text"):
                    print(f"{GREEN}{b.text}{RESET}", end="", flush=True)
        elif isinstance(msg, ResultMessage):
            print()
            if msg.is_error:
                print(f"{RED}Preflight failed (stop: {msg.stop_reason}){RESET}")
                return 1
            cost = f"  cost ${msg.total_cost_usd:.4f}" if msg.total_cost_usd else ""
            print(f"{GREEN}Preflight passed{RESET}{DIM}{cost}{RESET}")
            return 0
    return 0


# ── CLI ───────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Interactive CLI session for the GAIK Solution Configuration Wizard."
    )
    p.add_argument(
        "--output-dir",
        help="Pre-select the output directory (skips the wizard's directory question).",
    )
    p.add_argument(
        "--env-file",
        default=str(WIZARD_DIR.parent / ".env"),
        help="Path to .env with Foundry credentials (default: wizard dir/.env).",
    )
    p.add_argument(
        "--model",
        default=None,
        help=f"Override the model (default: ANTHROPIC_MODEL or {DEFAULT_MODEL}).",
    )
    p.add_argument(
        "--preflight",
        action="store_true",
        help="Check Foundry credentials with a tiny test query (no wizard session started).",
    )
    p.add_argument(
        "--pass-env",
        action="append",
        default=[],
        metavar="NAME",
        help="Also pass this environment variable to the agent (repeatable). "
        "By default it gets only the variables in AGENT_ENV_VARS.",
    )
    p.add_argument(
        "--allow-nested",
        action="store_true",
        help="Permit running inside a Claude Code session by dropping CLAUDECODE "
        "for the child process (may disrupt the parent session).",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    try:
        env = load_environment(Path(args.env_file).expanduser().resolve(), args.pass_env)
        guard_nested_session(args.allow_nested, env)
        model = resolve_model(env, args.model)

        if args.preflight:
            print(f"Preflight: checking Foundry routing (model={model}) …\n")
            sys.exit(asyncio.run(run_preflight(env, model)))

        output_dir: Path | None = None
        if args.output_dir:
            output_dir = Path(args.output_dir).expanduser()
            output_dir.mkdir(parents=True, exist_ok=True)
            output_dir = output_dir.resolve()

        sys.exit(asyncio.run(run_interactive(env, model, output_dir)))

    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted.{RESET}", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f"\n{RED}ERROR: {exc}{RESET}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
