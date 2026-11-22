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

The agent gets the system basics (PATH, home and temp folders, locale, proxy
and certificate settings) plus the names this .env file sets, nothing else
from your shell: the runner narrows its own environment to these before the
SDK starts the CLI, which inherits it. Without a .env file, the names come
from the PoC template's env.example (provider keys and settings) and the
runner settings above, taken from your shell. Name another variable with
--pass-env NAME to hand it on.

--- What the agent may do ---------------------------------------------------

The agent runs with bypassPermissions and a PreToolUse hook
(agent_tool_guard.py) that decides every tool call before it runs, including
the ones the CLI would approve by itself:

- it reads only the output folder and the wizard's own files, and writes only
  the output folder;
- it never reads or writes a .env file;
- Bash runs only the wizard's scripts (scripts/agent_scripts.json), one plain
  command at a time;
- web, subagent and MCP tools are refused, and your own MCP servers and
  Claude Code settings are not loaded.

A refused call is answered with the reason, and the agent carries on.

Run the preflight check to verify credentials before a full session:

    python run_wizard_interactive.py --preflight

--- Usage -------------------------------------------------------------------

    # The runner asks for the output folder before the session starts:
    python run_wizard_interactive.py

    # Or give it (outside this repository):
    python run_wizard_interactive.py --output-dir C:/projects/my-use-case

    # Use a different .env file:
    python run_wizard_interactive.py --env-file path/to/.env

    # Override the model:
    python run_wizard_interactive.py --model claude-sonnet-5-5

    # Stop once the session's estimated model cost reaches $5 (default: no limit;
    # the CLI counts the whole session, across your messages, and checks it
    # between turns, so a session can end a little over):
    python run_wizard_interactive.py --max-budget-usd 5

See also: run_wizard_sdk.py for a headless smoke-test (no user interaction).
"""

from __future__ import annotations

import argparse
import asyncio
import codecs
import math
import os
import re
import sys
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)

WIZARD_DIR = Path(__file__).resolve().parent
REPO_ROOT = WIZARD_DIR.parents[1]
sys.path.insert(0, str(WIZARD_DIR))

import agent_tool_guard  # noqa: E402 - next to this file

#: The tools the wizard uses; everything else is refused by the guard too.
TOOLS = ["Read", "Grep", "Glob", "Write", "Edit", "Bash", "TodoWrite"]
#: What a program needs from the system to run, on Linux, macOS and Windows.
SYSTEM_ENV_VARS = frozenset(
    {
        "PATH", "PATHEXT", "HOME", "USER", "USERNAME", "LOGNAME", "SHELL", "TERM",
        "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE", "TZ",
        "TMPDIR", "TEMP", "TMP",
        "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "OS",
        "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA",
        "PROGRAMFILES", "PROGRAMFILES(X86)", "COMMONPROGRAMFILES",
        "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
        "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_RUNTIME_DIR",
        "VIRTUAL_ENV", "CONDA_PREFIX",
        "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "NODE_EXTRA_CA_CERTS",
        "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy",
        "CLAUDE_CONFIG_DIR", "CLAUDE_CODE_GIT_BASH_PATH",
    }
)  # fmt: skip
AGENT_ENV_DEFAULTS = {
    "API_TIMEOUT_MS": "600000",
    "CLAUDE_CODE_MAX_RETRIES": "2",
    "DISABLE_TELEMETRY": "1",
    # Bash starts every command in the wizard folder, so `python scripts/...` works.
    "CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR": "1",
}

REQUIRED_ENV_VARS = [
    "CLAUDE_CODE_USE_FOUNDRY",
    "ANTHROPIC_FOUNDRY_API_KEY",
    "ANTHROPIC_FOUNDRY_RESOURCE",
]
DEFAULT_MODEL = "claude-sonnet-5-5"
#: Without a .env file the agent gets these names from the shell, besides the
#: provider names the PoC template lists: the runner's own settings, and the
#: alternative names gaik accepts that the template mentions only in comments.
RUNNER_ENV_VARS = frozenset(
    {"ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL", "LLM_PROVIDER", *AGENT_ENV_DEFAULTS}
    | {"AITTA_API_TOKEN", "AITTA_TOKEN", "GEMINI_API_KEY", "GOOGLE_SERVICE_ACCOUNT_JSON"}
)
PROVIDER_ENV_TEMPLATE = WIZARD_DIR / "templates" / "poc" / "_common" / "env.example.tmpl"
#: Without a .env file, every shell name with one of these prefixes goes to the
#: agent too: gaik reads more provider settings than the template lists.
PROVIDER_ENV_PREFIXES = (
    "ANTHROPIC_",
    "AZURE_",
    "OPENAI_",
    "AITTA_",
    "GOOGLE_",
    "GEMINI_",
    "LITELLM_",
)

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


def agent_environment(
    source: dict[str, str], env_file_names: set[str], pass_env: list[str]
) -> dict[str, str]:
    """The agent's environment: the system basics, the names the .env file
    sets and the names given with --pass-env, taken from ``source``."""
    names = SYSTEM_ENV_VARS | set(env_file_names) | set(pass_env)
    if os.name == "nt":
        # Windows reads names in any case and os.environ upper-cases them, so a
        # .env name written as Azure_Api_Key is AZURE_API_KEY in the shell.
        wanted = {name.upper() for name in names}
        env = {k: v for k, v in source.items() if k.upper() in wanted}
    else:
        env = {k: v for k, v in source.items() if k in names}
    for key, value in AGENT_ENV_DEFAULTS.items():
        env.setdefault(key, value)
    return env


def provider_env_names(template: Path = PROVIDER_ENV_TEMPLATE) -> set[str]:
    """The variable names the PoC template's env.example lists (``# NAME=``)."""
    text = template.read_text(encoding="utf-8")
    return set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]*)=", text, flags=re.MULTILINE))


def load_environment(env_file: Path, pass_env: list[str] | None = None) -> dict[str, str]:
    names: set[str] = set()
    if env_file.exists():
        load_dotenv(env_file)
        names = {k for k in dotenv_values(env_file) if k}
    else:
        print(f"{DIM}(no .env at {env_file} — using current shell env){RESET}", file=sys.stderr)
        names = set(REQUIRED_ENV_VARS) | RUNNER_ENV_VARS | provider_env_names()
        names |= {k for k in os.environ if k.upper().startswith(PROVIDER_ENV_PREFIXES)}

    missing = [k for k in REQUIRED_ENV_VARS if not (os.getenv(k) or "").strip()]
    if missing:
        raise RuntimeError(
            f"{RED}Missing Foundry env vars: {', '.join(missing)}{RESET}\n"
            f"Copy .env.example → .env and fill them in."
        )
    return agent_environment(dict(os.environ), names, pass_env or [])


def use_agent_environment(env: dict[str, str]) -> None:
    """Make ``env`` the runner's whole environment.

    The SDK starts the CLI with the runner's environment and ``options.env``
    over it, so this is what keeps everything else in the shell from the
    agent. The runner needs nothing more once ``load_environment`` has run.
    """
    os.environ.clear()
    os.environ.update(env)


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
    if message.subtype == "error_max_budget_usd":
        cost = f" (${message.total_cost_usd:.4f})" if message.total_cost_usd else ""
        print(
            f"\n{YELLOW}--- Session stopped: the --max-budget-usd limit was reached{cost} ---{RESET}"
        )
    elif message.is_error:
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


def build_initial_prompt(output_dir: Path) -> str:
    """The first message that invokes the wizard skill and sets up the session."""
    # Forward slashes on every system: the guard reads them the same way in
    # Bash and in the file tools, and a Windows backslash is shell syntax.
    output_hint = (
        f"\nThe user has pre-selected this output directory: {output_dir.as_posix()}\n"
        "Skip the directory question and use it directly. Write paths in it with "
        "forward slashes."
    )

    return f"""\
/solution-wizard

You are starting an interactive GAIK Solution Configuration Wizard session.
Load and follow the complete wizard instructions from ./SKILL.md (you are already
in the wizard directory). {output_hint}

Begin Phase 1: introduce yourself briefly, then ask the user for their use-case
description.
Wait for each answer before asking the next question -- this is an interactive
conversation, one or two questions at a time.
""".strip()


# ── Main interactive loop ─────────────────────────────────────────────────────


def build_session_options(
    output_dir: Path,
    env: dict[str, str],
    model: str,
    *,
    max_budget_usd: float | None = None,
    **extra: object,
) -> ClaudeAgentOptions:
    """The agent's options: every tool call goes through the guard's hook.

    ``max_budget_usd`` ends the session once its estimated model cost reaches it.
    With one streaming client the CLI counts the whole session, across messages,
    not each message (the SDK's docs say "for the query"). It checks the total
    between turns, so the session can end a little over the limit.
    """
    # The repository is never written either: with an editable install the
    # scripts import gaik from it.
    guard = agent_tool_guard.ToolGuard(WIZARD_DIR, output_dir, protected=[REPO_ROOT])
    return ClaudeAgentOptions(
        cwd=str(WIZARD_DIR),
        add_dirs=[str(output_dir)],
        env=env,
        model=model,
        tools=TOOLS,
        allowed_tools=TOOLS,
        # bypassPermissions lets every tool run; the hook is what limits them to
        # the output folder and the wizard's own scripts. A hook runs before the
        # CLI's own approval, so it also decides the calls the CLI would approve
        # by itself.
        permission_mode="bypassPermissions",
        hooks={"PreToolUse": [HookMatcher(hooks=[guard.hook])]},
        setting_sources=[],  # no user or project settings, CLAUDE.md or hooks
        # Only the MCP servers given here, which is none: not the user's own.
        strict_mcp_config=True,
        max_budget_usd=max_budget_usd,
        **extra,
    )


def _config_dirs(home: Path) -> list[Path]:
    """Folders whose files a program loads at start: the hidden folders in the
    home folder (shell, Python, Claude Code and git settings) and the ones the
    environment names."""
    dirs = (
        [home / name for name in os.listdir(home) if name.startswith(".")] if home.is_dir() else []
    )
    for name in ("CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME", "APPDATA", "LOCALAPPDATA"):
        if os.environ.get(name):
            dirs.append(Path(os.environ[name]))
    return [Path(os.path.realpath(d)) for d in dirs]


def resolve_output_dir(raw: str, cwd: Path) -> Path:
    """An absolute output folder of its own, relative paths taken from ``cwd``.

    The agent writes anything there, so the folder must not be, hold or sit in
    a place whose files something loads later: this repository
    (``scaffold_poc.py`` refuses one inside it, and an editable install imports
    gaik from it), the home folder, its hidden settings folders, or where the
    scripts' Python loads code from. Names are compared the way the filesystem
    reads them (in any case on macOS and Windows).
    """
    # A Git Bash /c/... path is C:/... on Windows, as the guard reads it.
    path = Path(agent_tool_guard._native(raw.strip().strip('"'))).expanduser()
    path = Path(os.path.realpath(path if path.is_absolute() else cwd / path))
    repo = Path(os.path.realpath(REPO_ROOT))
    home = Path(os.path.realpath(Path.home()))
    if agent_tool_guard.under_any(path, [repo]):
        raise ValueError(
            f"the output folder {path.as_posix()} is inside the GAIK repository; "
            "choose one outside it, for example under your home folder"
        )
    if agent_tool_guard.under_any(repo, [path]):
        raise ValueError(
            f"the output folder {path.as_posix()} holds the GAIK repository; "
            "choose a folder of its own outside it"
        )
    if agent_tool_guard.under_any(home, [path]):
        raise ValueError(
            f"the output folder {path.as_posix()} is your home folder or holds it; "
            "choose a folder of its own inside it"
        )
    config = _config_dirs(home)
    if agent_tool_guard.under_any(path, config):
        raise ValueError(
            f"the output folder {path.as_posix()} is in a settings folder that programs "
            "load files from; choose an ordinary folder"
        )
    code = agent_tool_guard.python_code_dirs()
    if agent_tool_guard.under_any(path, code) or any(
        agent_tool_guard.under_any(d, [path]) for d in code
    ):
        raise ValueError(
            f"the output folder {path.as_posix()} is or holds a folder the wizard's Python "
            "loads code from; choose a folder of its own"
        )
    return path


def _ask_output_dir() -> Path:
    while True:
        print(f"{BOLD}Output folder for this use case:{RESET} ", end="", flush=True)
        line = sys.stdin.readline()
        if not line:
            raise KeyboardInterrupt
        if not line.strip():
            continue
        try:
            return resolve_output_dir(line, Path.cwd())
        except ValueError as exc:
            print(f"{RED}{exc}{RESET}")


async def run_interactive(
    env: dict[str, str],
    model: str,
    output_dir: Path,
    max_budget_usd: float | None = None,
) -> int:
    options = build_session_options(output_dir, env, model, max_budget_usd=max_budget_usd)

    print(f"{BOLD}GAIK Solution Configuration Wizard{RESET}")
    print(f"{DIM}Model: {model}  |  Wizard dir: {WIZARD_DIR}")
    print(f"Output dir: {output_dir}")
    if max_budget_usd is not None:
        print(
            f"Budget: {_money(max_budget_usd)} for the whole session (checked between "
            "turns, so it can end a little over)"
        )
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


# ── CLI ───────────────────────────────────────────────────────────────────────


def _money(amount: float) -> str:
    """US dollars as a price is written: $1,000,000.00, $2.50, or $0.125 for a fraction."""
    whole, _, fraction = f"{amount:,.4f}".rstrip("0").partition(".")
    return f"${whole}.{fraction.ljust(2, '0')}"


def _dollars(value: str) -> float:
    """A positive, finite number of US dollars."""
    try:
        amount = float(value)
    except ValueError:
        amount = math.nan
    if not (math.isfinite(amount) and amount > 0):
        raise argparse.ArgumentTypeError(f"expected an amount above 0, got {value!r}")
    return amount


def _is_utf8(encoding: str | None) -> bool:
    try:
        return bool(encoding) and codecs.lookup(encoding).name == "utf-8"
    except LookupError:
        return False


def use_utf8_output() -> None:
    """Print every character the agent sends, also to a file or a pipe.

    On Windows, output that is not a console is written in the ANSI code page
    (cp1252), which has no ≥ or →, so the first such character the agent quoted
    ended the run with a UnicodeEncodeError. Output to a file or a pipe is now
    written in UTF-8. A terminal keeps the encoding it shows: a UTF-8 one is left
    as it is, and one in another encoding prints a character it has no sign for
    as a replacement instead of stopping. A stream that is not a text stream
    (none at all under pythonw) is left as it is.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            if not stream.isatty():
                reconfigure(encoding="utf-8", errors="replace")
            elif not _is_utf8(getattr(stream, "encoding", None)):
                reconfigure(errors="replace")
        except (OSError, ValueError):  # a closed stream: nothing is printed to it
            continue


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Interactive CLI session for the GAIK Solution Configuration Wizard."
    )
    p.add_argument(
        "--output-dir",
        help="The output folder, outside this repository (asked for when left out).",
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
        "--max-budget-usd",
        type=_dollars,
        default=None,
        metavar="USD",
        help="Stop the session once its estimated model cost reaches this many US dollars, "
        "counted over the whole session, across your messages. The CLI checks the cost "
        "between turns, so a session can end a little over it (default: no limit).",
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
        help="Hand this variable from your shell on to the agent (repeatable); "
        "the agent otherwise gets the system basics and the names the .env file sets.",
    )
    p.add_argument(
        "--allow-nested",
        action="store_true",
        help="Permit running inside a Claude Code session by dropping CLAUDECODE "
        "for the child process (may disrupt the parent session).",
    )
    return p.parse_args()


def main() -> None:
    use_utf8_output()
    args = parse_args()
    try:
        env = load_environment(Path(args.env_file).expanduser().resolve(), args.pass_env)
        guard_nested_session(args.allow_nested, env)
        use_agent_environment(env)
        model = resolve_model(env, args.model)

        if args.preflight:
            from claude_agent_sdk import query, ClaudeAgentOptions

            print(f"Preflight: checking Foundry routing (model={model}) …\n")

            async def _check():
                opts = ClaudeAgentOptions(
                    cwd=str(WIZARD_DIR),
                    env=env,
                    model=model,
                    tools=[],
                    allowed_tools=[],
                    permission_mode="bypassPermissions",
                    setting_sources=[],
                    strict_mcp_config=True,
                    max_turns=1,
                )
                async for msg in query(prompt="Reply with the single word: READY", options=opts):
                    if isinstance(msg, __import__("claude_agent_sdk").AssistantMessage):
                        for b in msg.content:
                            if hasattr(b, "text"):
                                print(f"{GREEN}{b.text}{RESET}", end="", flush=True)
                    elif isinstance(msg, __import__("claude_agent_sdk").ResultMessage):
                        print()
                        if msg.is_error:
                            print(f"{RED}Preflight failed (stop: {msg.stop_reason}){RESET}")
                            return 1
                        cost = f"  cost ${msg.total_cost_usd:.4f}" if msg.total_cost_usd else ""
                        print(f"{GREEN}Preflight passed{RESET}{DIM}{cost}{RESET}")
                        return 0
                return 0

            sys.exit(asyncio.run(_check()))

        output_dir = (
            resolve_output_dir(args.output_dir, Path.cwd())
            if args.output_dir
            else _ask_output_dir()
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        sys.exit(asyncio.run(run_interactive(env, model, output_dir, args.max_budget_usd)))

    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted.{RESET}", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f"\n{RED}ERROR: {exc}{RESET}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
