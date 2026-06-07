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
    ANTHROPIC_FOUNDRY_RESOURCE=<your Foundry resource name, e.g. haagahelia-poc-gaik>

Recommended (model selection):

    ANTHROPIC_DEFAULT_SONNET_MODEL=claude-sonnet-4-6

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
    python run_wizard_interactive.py --model claude-sonnet-4-6

See also: run_wizard_sdk.py for a headless smoke-test (no user interaction).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)

WIZARD_DIR = Path(__file__).resolve().parent

REQUIRED_ENV_VARS = [
    "CLAUDE_CODE_USE_FOUNDRY",
    "ANTHROPIC_FOUNDRY_API_KEY",
    "ANTHROPIC_FOUNDRY_RESOURCE",
]
DEFAULT_MODEL = "claude-sonnet-4-6"

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


def load_environment(env_file: Path) -> dict[str, str]:
    if env_file.exists():
        load_dotenv(env_file)
    else:
        print(f"{DIM}(no .env at {env_file} — using current shell env){RESET}", file=sys.stderr)

    missing = [k for k in REQUIRED_ENV_VARS if not (os.getenv(k) or "").strip()]
    if missing:
        raise RuntimeError(
            f"{RED}Missing Foundry env vars: {', '.join(missing)}{RESET}\n"
            f"Copy .env.example → .env and fill them in."
        )

    env = dict(os.environ)
    env.setdefault("API_TIMEOUT_MS", "600000")
    env.setdefault("CLAUDE_CODE_MAX_RETRIES", "2")
    env.setdefault("DISABLE_TELEMETRY", "1")
    return env


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
    options = ClaudeAgentOptions(
        cwd=str(WIZARD_DIR),
        add_dirs=[str(output_dir)] if output_dir else [],
        env=env,
        model=model,
        allowed_tools=["Read", "Grep", "Glob", "Write", "Edit", "Bash"],
        permission_mode="bypassPermissions",
        setting_sources=[],  # isolate from repo CLAUDE.md / graphify noise
    )

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
        "--allow-nested",
        action="store_true",
        help="Permit running inside a Claude Code session by dropping CLAUDECODE "
        "for the child process (may disrupt the parent session).",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    try:
        env = load_environment(Path(args.env_file).expanduser().resolve())
        guard_nested_session(args.allow_nested, env)
        model = resolve_model(env, args.model)

        if args.preflight:
            from claude_agent_sdk import query, ClaudeAgentOptions

            print(f"Preflight: checking Foundry routing (model={model}) …\n")

            async def _check():
                opts = ClaudeAgentOptions(
                    cwd=str(WIZARD_DIR),
                    env=env,
                    model=model,
                    allowed_tools=[],
                    permission_mode="bypassPermissions",
                    setting_sources=[],
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
