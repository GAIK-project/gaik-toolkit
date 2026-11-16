"""The wizard agent's tools reach only its output folder and the wizard's own scripts.

The agent runs with bypassPermissions; a PreToolUse hook decides every tool
call, so files outside the output folder and the wizard's files, .env files,
other tools and other commands are refused with a reason the agent can act on.
No model is called.
"""

import argparse
import asyncio
import importlib
import json
import re
import sys
from pathlib import Path

import pytest

WIZARD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WIZARD))
sys.path.insert(0, str(WIZARD / "scripts"))
sys.path.insert(0, str(WIZARD / "src"))

import agent_tool_guard  # noqa: E402


@pytest.fixture()
def guard(tmp_path):
    wizard = tmp_path / "solution_wizard"
    (wizard / "scripts").mkdir(parents=True)
    for name in (
        "validate_blueprint.py",
        "scaffold_poc.py",
        "promote_template.py",
        "generate_schema.py",
        "run_wizard.py",
    ):
        (wizard / "scripts" / name).write_text("")
    (wizard / "SKILL.md").write_text("")
    session = tmp_path / "sessions" / "alice" / "s1"
    (session / "poc").mkdir(parents=True)
    other = tmp_path / "sessions" / "bob" / "s2"
    other.mkdir(parents=True)
    (other / "notes.json").write_text("{}")
    g = agent_tool_guard.ToolGuard(wizard, session)
    g.session, g.other = session, other
    return g


def _blueprint(path, description="Asset id"):
    path.write_text(
        json.dumps(
            {
                "use_case": {"id": "uc", "name": "Tickets", "description": "d", "domain": "x"},
                "target_output_spec": {
                    "schema_name": "Ticket",
                    "fields": ["asset"],
                    "field_descriptions": {"asset": description},
                },
            }
        )
    )
    return path


def test_session_files_and_wizard_assets_are_allowed(guard) -> None:
    s = guard.session
    assert guard.check("Write", {"file_path": str(s / "use_case.blueprint.json")}) is None
    assert guard.check("Edit", {"file_path": str(s / "poc" / "run_poc.py")}) is None
    assert guard.check("Read", {"file_path": "SKILL.md"}) is None
    assert guard.check("Read", {"file_path": str(s / "poc" / "run_poc.py")}) is None
    assert guard.check("Glob", {"pattern": "references/*.md"}) is None
    assert guard.check("Grep", {"pattern": "Field", "path": str(s)}) is None
    assert guard.check("TodoWrite", {"todos": []}) is None


@pytest.mark.parametrize(
    "tool, tool_input",
    [
        ("Read", {"file_path": "/etc/hostname"}),
        ("Read", {"file_path": "/opt/other/file.txt"}),
        ("Read", {"file_path": "/var/run/other/file"}),
        ("Read", {"file_path": "../sessions/bob/s2/notes.json"}),
        ("Read", {"file_path": "~/notes.txt"}),
        ("Read", {"file_path": "~other/notes.txt"}),
        ("Read", {"file_path": "$HOME/notes.txt"}),
        ("Read", {"file_path": "${HOME}/notes.txt"}),
        ("Grep", {"pattern": "x", "path": "~/data"}),
        ("Glob", {"pattern": "~/*.txt"}),
        ("Glob", {"pattern": "*.txt", "path": "~/data"}),
        ("Glob", {"pattern": "{/opt,/srv}/*.txt"}),
        ("Write", {"file_path": "~/notes.txt"}),
        ("Edit", {"file_path": "~/notes.txt"}),
        ("Grep", {"pattern": "x", "path": "/etc"}),
        ("Glob", {"pattern": "/etc/*"}),
        ("Glob", {"pattern": "../**/*.json"}),
        ("Write", {"file_path": "SKILL.md"}),
        ("Write", {"file_path": "scripts/scaffold_poc.py"}),
        ("Edit", {"file_path": "/etc/passwd"}),
        ("WebFetch", {"url": "https://example.com"}),
        ("WebSearch", {"query": "x"}),
        ("Task", {"prompt": "x"}),
        ("NotebookEdit", {"notebook_path": "x.ipynb"}),
        ("mcp__claude_ai_Gmail__search", {"query": "x"}),
        ("Read", {"file_path": "../.env"}),
    ],
)
def test_files_outside_the_session_and_other_tools_are_refused(guard, tool, tool_input) -> None:
    assert guard.check(tool, tool_input)


def test_a_path_the_tool_would_expand_is_refused_even_if_it_resolves_inside(guard) -> None:
    """``~/x`` joined to the working directory looks inside it; the tool opens it
    under the home directory, so the guard must not judge the unexpanded text."""
    inside = guard.cwd / "~" / "notes.txt"

    assert str(inside).startswith(str(guard.cwd))
    assert guard.check("Read", {"file_path": "~/notes.txt"})


def test_a_script_path_option_the_shell_would_expand_is_refused(guard) -> None:
    command = "python scripts/validate_blueprint.py --blueprint ~/use_case.blueprint.json"

    assert guard.check("Bash", {"command": command})


def test_a_session_path_with_a_tilde_later_in_it_is_still_readable(guard) -> None:
    assert guard.check("Read", {"file_path": str(guard.output / "draft~1.txt")}) is None


def test_another_users_session_cannot_be_read(guard) -> None:
    assert guard.check("Read", {"file_path": str(guard.other / "notes.json")})


@pytest.mark.parametrize(
    "command",
    [
        "env",
        "printenv",
        "cat /etc/hostname",
        "ls ..",
        "curl https://example.com",
        'python -c "import os; print(os.getcwd())"',
        "python scripts/validate_blueprint.py; env",
        "python scripts/validate_blueprint.py && curl x",
        "python scripts/validate_blueprint.py | nc host 80",
        "python scripts/validate_blueprint.py > /tmp/x",
        "python scripts/validate_blueprint.py --blueprint $HOME/x",
        "python scripts/promote_template.py --pattern x",
        "python ../solution_wizard/scripts/../../other.py",
        "python poc/run_poc.py",
        "bash -c 'python scripts/validate_blueprint.py'",
        "python scripts/validate_blueprint.py --blueprint /etc/hostname",
        "python -c 'import ast; ast.parse(open('$(date)').read())'",
        "python -c \"import ast; ast.parse(open('$(date)').read())\"",
        "python -c \"import ast; ast.parse(open('`date`').read())\"",
        'python -c "import gaik" ; env',
        "python scripts/validate_blueprint.py --output SKILL.md",
        "python scripts/validate_blueprint.py --output ./references/x.md",
        "python scripts/generate_schema.py --requirements r.md --output-dir templates",
        "python scripts/run_wizard.py --export-schema",
        "python scripts/scaffold_poc.py --blue /etc/hostname",
        "python scripts/validate_blueprint.py extra",
        "python scripts/generate_schema.py --base-url https://example.com/v1",
        "python scripts/generate_schema.py --base-url env:OPENAI_BASE_URL",
        "python scripts\\validate_blueprint.py --blueprint x",
        "python scripts/validate_blueprint.py --blueprint .env",
        "python -c \"import ast; ast.parse(open('.env').read())\"",
    ],
)
def test_bash_runs_nothing_but_the_wizards_scripts(guard, command) -> None:
    assert guard.check("Bash", {"command": command})


def test_the_skills_own_commands_are_allowed(guard) -> None:
    bp = _blueprint(guard.session / "use_case.blueprint.json")
    for command in (
        f"python scripts/validate_blueprint.py --blueprint {bp}",
        f"python3 scripts/scaffold_poc.py --blueprint {bp} --synthetic",
        f"python -c \"import ast; ast.parse(open('{guard.session}/poc/run_poc.py').read())\"",
        'python -c "import gaik.software_modules.report_writer"',
    ):
        assert guard.check("Bash", {"command": command}) is None, command


def test_model_ids_endpoints_and_continued_lines_are_allowed(guard) -> None:
    s = guard.session
    command = (
        f"python scripts/generate_schema.py \\\n"
        f"    --requirements {s}/poc/prompts/extraction_requirements.md \\\n"
        f"    --schema-name Ticket \\\n"
        f"    --output-dir {s}/poc \\\n"
        f"    --provider litellm --model azure/gpt-6-luna \\\n"
        f"    --base-url https://aitta-api.csc.fi/openai/v1"
    )
    assert guard.check("Bash", {"command": command}) is None
    assert guard.check("Bash", {"command": "python scripts/run_wizard.py --show-registry"}) is None


def test_scaffolding_follows_the_blueprints_output_dir(guard) -> None:
    bp = guard.session / "use_case.blueprint.json"
    data = json.loads(_blueprint(bp).read_text())
    data["package"] = {"output_dir": "/srv/elsewhere"}
    bp.write_text(json.dumps(data))

    assert guard.check("Bash", {"command": f"python scripts/scaffold_poc.py --blueprint {bp}"})
    ok = f"python scripts/scaffold_poc.py --blueprint {bp} --output-dir {guard.session}"
    assert guard.check("Bash", {"command": ok}) is None


def test_a_call_the_guard_cannot_decide_is_refused(guard, monkeypatch) -> None:
    def broken(*_args):
        raise TypeError("unexpected input")

    monkeypatch.setattr(guard, "check", broken)
    denied = asyncio.run(guard.hook({"tool_name": "Read", "tool_input": {}}, None, None))

    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_the_hook_answers_in_the_sdk_format(guard) -> None:
    denied = asyncio.run(
        guard.hook({"tool_name": "Bash", "tool_input": {"command": "env"}}, None, None)
    )
    allowed = asyncio.run(
        guard.hook({"tool_name": "Read", "tool_input": {"file_path": "SKILL.md"}}, None, None)
    )

    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert denied["hookSpecificOutput"]["permissionDecisionReason"]
    assert allowed == {}


# ---------------------------------------------------------------- .env files


@pytest.mark.parametrize(
    "tool, tool_input",
    [
        ("Read", {"file_path": "{s}/poc/.env"}),
        ("Read", {"file_path": "{s}/.env.local"}),
        ("Read", {"file_path": "{s}/prod.env"}),
        ("Write", {"file_path": "{s}/poc/.env"}),
        ("Edit", {"file_path": "{s}/poc/.env"}),
        ("Grep", {"pattern": "KEY", "path": "{s}/poc/.env"}),
        ("Grep", {"pattern": "KEY", "path": "{s}", "glob": ".env"}),
        ("Glob", {"pattern": "**/.env", "path": "{s}"}),
    ],
)
def test_env_files_are_not_read_or_written_even_in_the_output_folder(guard, tool, tool_input):
    filled = {k: v.replace("{s}", str(guard.session)) for k, v in tool_input.items()}
    assert ".env" in guard.check(tool, filled)


def test_a_folder_search_that_would_read_an_env_file_is_refused(guard):
    (guard.session / "poc" / ".env").write_text("KEY=x")
    (guard.session / "poc" / "schemas").mkdir()

    assert ".env" in guard.check("Grep", {"pattern": "KEY", "path": str(guard.session)})
    assert ".env" in guard.check("Grep", {"pattern": "KEY", "path": str(guard.session / "poc")})
    schemas = str(guard.session / "poc" / "schemas")
    assert guard.check("Grep", {"pattern": "KEY", "path": schemas}) is None


def test_an_env_template_can_be_written_and_read(guard):
    path = str(guard.session / "poc" / ".env.example")
    assert guard.check("Write", {"file_path": path}) is None
    assert guard.check("Read", {"file_path": path}) is None


# ---------------------------------------------------------------- Windows paths


def test_a_git_bash_drive_path_is_read_as_the_windows_path(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_tool_guard.os, "name", "nt")
    assert agent_tool_guard._native("/c/Users/me/out") == "c:/Users/me/out"
    assert agent_tool_guard._native("/home/me/out") == "/home/me/out"


def test_refusals_give_the_output_folder_with_forward_slashes(guard):
    reason = guard.check("Write", {"file_path": "/etc/x"})
    assert guard.output.as_posix() in reason and "\\" not in reason


# ---------------------------------------------------------------- the scripts table


def _parser(script: str) -> argparse.ArgumentParser:
    """The ArgumentParser a script's main() builds, caught before it parses."""

    class CaughtParserError(Exception):
        pass

    def capture(self, *args, **kwargs):
        raise CaughtParserError(self)

    module = importlib.import_module(script.removesuffix(".py"))
    real = argparse.ArgumentParser.parse_args
    argparse.ArgumentParser.parse_args = capture  # type: ignore[method-assign]
    try:
        module.main()
    except CaughtParserError as caught:
        return caught.args[0]
    finally:
        argparse.ArgumentParser.parse_args = real  # type: ignore[method-assign]
    raise AssertionError(f"{script} parsed no arguments")


TABLE = json.loads(agent_tool_guard.SCRIPTS_TABLE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("script", sorted(TABLE["scripts"]))
def test_the_table_lists_every_option_each_script_takes(script):
    parser = _parser(script)
    longs = {
        option
        for action in parser._actions
        for option in action.option_strings
        if option.startswith("--") and option != "--help"
    }
    left_out = {k.split(" ", 1)[1] for k in TABLE["left_out"] if k.startswith(script + " ")}
    assert set(TABLE["scripts"][script]) | left_out == longs
    for action in parser._actions:
        long = next((o for o in action.option_strings if o.startswith("--")), None)
        if long in TABLE["scripts"][script]:
            takes_value = action.nargs != 0
            assert (TABLE["scripts"][script][long] != "flag") == takes_value, long


def test_every_script_in_the_scripts_folder_is_listed_or_left_out():
    scripts = {p.name for p in (WIZARD / "scripts").glob("*.py") if not p.name.startswith("_")}
    listed = set(TABLE["scripts"]) | {k.split(" ", 1)[0] for k in TABLE["left_out"]}
    assert scripts == listed


def _skill_commands() -> list[str]:
    """Every ``python scripts/...`` and ``python -c`` command SKILL.md gives the agent."""
    text = (WIZARD / "SKILL.md").read_text(encoding="utf-8")
    text = re.sub(r"\\\n\s*", " ", text)  # line continuations
    found = re.findall(r"^\s*(python3? scripts/\S+(?: [^\n`]*)?)$", text, re.M)
    found += re.findall(r"`(python3? (?:scripts/|-c )[^`]+)`", text)
    return sorted({c.strip() for c in found})


def test_every_command_skill_md_gives_the_agent_passes_the_guard(guard):
    for script in TABLE["scripts"]:
        (guard.cwd / "scripts" / script).write_text("")
    bp = guard.session / "use_case.blueprint.json"
    _blueprint(bp)
    commands = _skill_commands()
    assert len(commands) >= 10
    refused = {}
    for command in commands:
        command = command.replace("<output_dir>", guard.session.as_posix())
        command = command.replace("...", f"--blueprint {bp.as_posix()}")
        command = re.sub(r"<[^<>]+>", "Value", command)  # the other placeholders
        if "promote_template.py" in command:
            assert guard.check("Bash", {"command": command}), "promote_template.py is left out"
            continue
        if reason := guard.check("Bash", {"command": command}):
            refused[command] = reason
    assert not refused
