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
import os
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
    bp = _blueprint(guard.session / "use_case.blueprint.json").as_posix()
    s = guard.session.as_posix()
    for command in (
        f"python scripts/validate_blueprint.py --blueprint {bp}",
        f"python3 scripts/scaffold_poc.py --blueprint {bp} --synthetic",
        f"python -c \"import ast; ast.parse(open('{s}/poc/run_poc.py').read())\"",
        'python -c "import gaik.software_modules.report_writer"',
    ):
        assert guard.check("Bash", {"command": command}) is None, command


def test_model_ids_endpoints_and_continued_lines_are_allowed(guard) -> None:
    s = guard.session.as_posix()
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
    blueprint = bp.as_posix()

    command = f"python scripts/scaffold_poc.py --blueprint {blueprint}"
    reason = guard.check("Bash", {"command": command})
    assert reason and "package.output_dir" in reason
    ok = (
        f"python scripts/scaffold_poc.py --blueprint {blueprint} "
        f"--output-dir {guard.session.as_posix()}"
    )
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


@pytest.mark.parametrize(
    "name", [".env.", ".env ", ".env. .", ".env::$DATA", ".env:notes", "C:.env", "prod.env."]
)
def test_the_names_windows_also_opens_an_env_file_under_count_as_env_files(guard, name):
    assert agent_tool_guard.is_env_file(name)
    assert agent_tool_guard.is_env_file(f"poc\\{name}")
    path = f"{guard.session.as_posix()}/poc/{name}"
    assert ".env" in guard.check("Read", {"file_path": path})
    assert ".env" in guard.check("Write", {"file_path": path})
    assert ".env" in guard.check("Grep", {"pattern": "KEY", "path": path})
    one_liner = f"python -c \"import ast; ast.parse(open('{path}').read())\""
    assert guard.check("Bash", {"command": one_liner})


@pytest.mark.parametrize("name", [".env.example", "env.py", "run_poc.py", "notes:draft.txt"])
def test_other_names_are_not_env_files(name):
    assert not agent_tool_guard.is_env_file(name)


def test_a_link_to_an_env_file_is_judged_by_the_file_it_opens(guard):
    (guard.session / "poc" / ".env").write_text("KEY=x")
    link = guard.session / "poc" / "notes.txt"
    try:
        link.symlink_to(guard.session / "poc" / ".env")
    except OSError:
        pytest.skip("this system cannot create the link")

    assert ".env" in guard.check("Read", {"file_path": str(link)})
    assert ".env" in guard.check("Write", {"file_path": str(link)})


@pytest.mark.skipif(sys.platform != "win32", reason="Windows short (8.3) names")
def test_a_windows_short_name_of_an_env_file_is_judged_by_its_long_name(guard):
    import ctypes

    env_file = guard.session / "poc" / ".env.local"
    env_file.write_text("KEY=x")
    buffer = ctypes.create_unicode_buffer(1024)
    ctypes.windll.kernel32.GetShortPathNameW(str(env_file), buffer, len(buffer))  # type: ignore[attr-defined]
    short = buffer.value
    if not short or Path(short).name.lower() == env_file.name:
        pytest.skip("short names are off on this volume")

    assert not agent_tool_guard.is_env_file(short)
    assert ".env" in guard.check("Read", {"file_path": short})
    assert ".env" in guard.check("Read", {"file_path": Path(short).as_posix()})


def test_a_folder_search_outside_the_allowed_folders_is_refused_before_it_is_walked(
    guard, monkeypatch
):
    (guard.other / ".env").write_text("KEY=x")

    def walked(_folder):
        raise AssertionError("the folder was looked through")

    monkeypatch.setattr(agent_tool_guard, "_has_env_file", walked)
    reason = guard.check("Grep", {"pattern": "KEY", "path": str(guard.other)})

    assert reason and "output folder" in reason and ".env file" not in reason


# ------------------------------------------- an output folder holding the wizard


def test_the_wizards_own_files_stay_read_only_when_the_output_folder_holds_them(tmp_path):
    wizard = tmp_path / "solution_wizard"
    (wizard / "scripts").mkdir(parents=True)
    (wizard / "scripts" / "validate_blueprint.py").write_text("")
    (wizard / "scripts" / "scaffold_poc.py").write_text("")
    (wizard / "SKILL.md").write_text("")
    g = agent_tool_guard.ToolGuard(wizard, tmp_path)
    bp = _blueprint(tmp_path / "use_case.blueprint.json").as_posix()

    assert g.check("Write", {"file_path": str(wizard / "SKILL.md")})
    assert g.check("Edit", {"file_path": str(wizard / "scripts" / "scaffold_poc.py")})
    into_wizard = (
        f"python scripts/scaffold_poc.py --blueprint {bp} --output-dir {wizard.as_posix()}/poc"
    )
    assert g.check("Bash", {"command": into_wizard})
    assert g.check("Read", {"file_path": str(wizard / "SKILL.md")}) is None
    assert g.check("Write", {"file_path": str(tmp_path / "case" / "notes.md")}) is None
    own = f"python scripts/scaffold_poc.py --blueprint {bp} --output-dir {tmp_path.as_posix()}/poc"
    assert g.check("Bash", {"command": own}) is None


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
    # `python scripts/<name>.py` names the form of every command, not a command.
    return sorted({c.strip() for c in found if "scripts/<" not in c})


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
        if "refresh_schema_model.py" in command:
            reason = guard.check("Bash", {"command": command})
            assert reason and "Skip it" in reason, "refresh_schema_model.py runs the agent's code"
            continue
        if reason := guard.check("Bash", {"command": command}):
            refused[command] = reason
    assert not refused


# --- folders the agent must not write, path forms, links and case -----------


def test_a_protected_folder_inside_the_output_folder_is_not_written(tmp_path):
    wizard = tmp_path / "solution_wizard"
    (wizard / "scripts").mkdir(parents=True)
    out = tmp_path / "out"
    keep = out / "keep"
    keep.mkdir(parents=True)
    g = agent_tool_guard.ToolGuard(wizard, out, scripts={}, protected=[keep])
    assert g.check("Write", {"file_path": str(keep / "x.py")})
    assert g.check("Write", {"file_path": str(out / "ok.txt")}) is None


def test_where_the_scripts_python_loads_code_from_is_never_written(tmp_path, monkeypatch):
    out = tmp_path / "out"
    site_dir = out / "venv" / "site-packages"
    site_dir.mkdir(parents=True)
    monkeypatch.setattr(agent_tool_guard, "python_code_dirs", lambda: [site_dir.resolve()])
    g = agent_tool_guard.ToolGuard(tmp_path / "wizard", out, scripts={})
    assert g.check("Write", {"file_path": str(site_dir / "sitecustomize.py")})
    assert g.check("Write", {"file_path": str(out / "notes.md")}) is None


def test_the_running_pythons_own_folders_are_protected(guard):
    import sys

    real_prefix = Path(os.path.realpath(sys.prefix))
    assert agent_tool_guard.under_any(real_prefix, guard.protected)


@pytest.mark.parametrize(
    "value",
    ["C:out", "out/a:stream", "//?/c:/out", "\\\\server\\share\\out", "out/name.", "out/name "],
)
def test_path_forms_windows_reads_differently_are_refused(guard, value):
    assert agent_tool_guard.odd_path_form(value)
    if not set(value) & set("?\\ "):  # those the shell check refuses before
        # A drive-relative path is given as it is: behind the session folder it
        # would no longer be one.
        drive_relative = re.match(r"^[A-Za-z]:[^\\/]", value)
        where = value if drive_relative else f"{guard.session.as_posix()}/{value}"
        command = f"python scripts/generate_schema.py --output-dir {where}"
        assert "output folder" in guard.check("Bash", {"command": command})


def test_help_alone_is_allowed_for_the_wizards_own_scripts(guard):
    assert guard.check("Bash", {"command": "python scripts/generate_schema.py --help"}) is None
    assert guard.check("Bash", {"command": "python scripts/scaffold_poc.py --help"}) is None
    for command in (
        "python scripts/generate_schema.py --help --model m",
        "python scripts/generate_schema.py --model m --help",
        "python scripts/promote_template.py --help",
        "python scripts/refresh_schema_model.py --help",
        "python scripts/not_listed.py --help",
        "python ../elsewhere/generate_schema.py --help",
    ):
        assert guard.check("Bash", {"command": command}), command


def test_a_path_in_the_disks_case_is_inside_a_root_typed_in_another_case(guard):
    """On macOS realpath keeps the case the output folder was typed in, and Glob
    returns paths in the disk's case: the same folder where names ignore case."""
    if not agent_tool_guard._ignores_case(guard.session):
        pytest.skip("this filesystem tells names apart by case")
    (guard.session / "poc" / "notes.json").write_text("{}")
    typed = Path(str(guard.session).swapcase())  # the root as the user typed it
    on_disk = (guard.session / "poc" / "notes.json").as_posix()
    assert agent_tool_guard._inside(on_disk, [typed], guard.cwd)
    assert not agent_tool_guard._inside(guard.other.as_posix(), [typed], guard.cwd)


@pytest.mark.parametrize("ignores_case", [True, False])
def test_macos_paths_in_the_disks_case_are_inside_only_where_names_ignore_case(
    monkeypatch, ignores_case
):
    """As on macOS: POSIX paths, which compare case, and a realpath that keeps the
    output folder in the case it was typed in. Runs on every system."""
    from pathlib import PurePosixPath

    typed = PurePosixPath("/Users/me/Projects/Case")
    opened = {
        "notes": PurePosixPath("/Users/me/projects/case/poc/notes.json"),
        "sibling": PurePosixPath("/Users/me/projects/case-b/notes.json"),
        "parent": PurePosixPath("/Users/me/projects"),
    }
    monkeypatch.setattr(agent_tool_guard, "_real", lambda path, cwd: opened[path])
    monkeypatch.setattr(agent_tool_guard, "_ignores_case", lambda folder: ignores_case)
    assert agent_tool_guard._inside("notes", [typed], Path()) is ignores_case
    assert not agent_tool_guard._inside("sibling", [typed], Path())
    assert not agent_tool_guard._inside("parent", [typed], Path())


def test_plain_paths_are_not_odd_forms():
    for value in ("out/case", "C:/work/case", "C:\\work\\case", "/c/work/case", "./x", "../x"):
        assert not agent_tool_guard.odd_path_form(value), value


def _link_or_skip(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError:  # Windows without the symlink privilege: a junction needs none
        pass
    try:
        import _winapi

        _winapi.CreateJunction(str(target.resolve()), str(link))
    except (ImportError, OSError):
        pytest.skip("this system cannot create the link")


def test_a_script_does_not_write_into_a_folder_that_holds_a_link_and_names_it(guard, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    bp = _blueprint(guard.session / "use_case.blueprint.json")
    command = (
        f"python scripts/scaffold_poc.py --blueprint {bp.as_posix()} "
        f"--output-dir {guard.session.as_posix()}"
    )
    assert guard.check("Bash", {"command": command}) is None
    link = guard.session / "poc" / "out"
    _link_or_skip(link, elsewhere)
    reason = guard.check("Bash", {"command": command})
    assert reason and link.as_posix() in reason


def test_a_link_outside_the_folders_a_script_writes_does_not_stop_it(guard, tmp_path):
    """A virtual environment in the output folder is normal once the user has run the
    PoC (Phase 11); its links are in no folder a script writes into."""
    for venv in (guard.session / ".venv", guard.session / "poc" / ".venv"):
        (venv / "lib").mkdir(parents=True)
        _link_or_skip(venv / "lib64", venv / "lib")
    bp = _blueprint(guard.session / "use_case.blueprint.json")
    out = guard.session.as_posix()
    for command in (
        f"python scripts/validate_blueprint.py --blueprint {bp.as_posix()}",
        f"python scripts/scaffold_poc.py --blueprint {bp.as_posix()} --output-dir {out}",
        f"python scripts/generate_schema.py --requirements {out}/poc/prompts/r.md "
        f"--output-dir {out}/poc",
        f"python scripts/run_wizard.py --blueprint {bp.as_posix()}",
    ):
        assert guard.check("Bash", {"command": command}) is None, command


def test_a_script_that_writes_nothing_is_not_stopped_by_a_link(guard, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    _link_or_skip(guard.session / "poc" / "out", elsewhere)
    bp = _blueprint(guard.session / "use_case.blueprint.json")
    command = f"python scripts/validate_blueprint.py --blueprint {bp.as_posix()}"
    assert guard.check("Bash", {"command": command}) is None


def test_without_output_dir_the_scaffolders_folder_is_the_blueprints_package_output_dir(
    guard, tmp_path
):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    bp = _blueprint(guard.session / "use_case.blueprint.json")
    data = json.loads(bp.read_text())
    data["package"] = {"output_dir": (guard.session / "case").as_posix()}
    bp.write_text(json.dumps(data))
    command = f"python scripts/scaffold_poc.py --blueprint {bp.as_posix()}"
    assert guard.check("Bash", {"command": command}) is None
    link = guard.session / "case" / "poc" / "prompts"
    _link_or_skip(link, elsewhere)
    reason = guard.check("Bash", {"command": command})
    assert reason and link.as_posix() in reason


def test_the_writes_table_names_every_listed_script_and_the_folders_of_each_that_writes():
    assert set(TABLE["writes"]) == set(TABLE["scripts"])
    for script, options in TABLE["scripts"].items():
        if "--output-dir" in options:
            assert TABLE["writes"].get(script), f"{script} writes, but no folders are listed"
    for folders in TABLE["writes"].values():
        if not folders:
            continue  # a script that writes nothing
        assert "." in folders
        for folder in folders:
            parent = folder.rsplit("/", 1)[0] if "/" in folder else "."
            assert parent in folders, f"{folder} is listed without {parent}"


@pytest.mark.parametrize(
    "writes", [None, ["."], {"scaffold_poc.py": "."}, {"scaffold_poc.py": [1]}]
)
def test_a_table_without_a_writes_list_for_each_script_is_refused(tmp_path, writes):
    """Read as "writes nothing", a missing table would let every script run unchecked."""
    table = {key: value for key, value in TABLE.items() if key != "writes"}
    if writes is not None:
        table["writes"] = writes
    path = tmp_path / "agent_scripts.json"
    path.write_text(json.dumps(table), encoding="utf-8")
    with pytest.raises(ValueError, match="writes"):
        agent_tool_guard.load_writes(path)


@pytest.mark.parametrize("script", ["validate_blueprint.py", "scaffold_poc.py"])
def test_a_listed_script_without_a_writes_entry_is_not_run(guard, script):
    bp = _blueprint(guard.session / "use_case.blueprint.json")
    command = f"python scripts/{script} --blueprint {bp.as_posix()}"
    assert guard.check("Bash", {"command": command}) is None
    del guard.writes[script]
    reason = guard.check("Bash", {"command": command})
    assert reason and script in reason and "writes" in reason
    assert guard.check("Bash", {"command": f"python scripts/{script} --help"}) is None


def _written_folders(root: Path) -> set[str]:
    """Every folder under ``root`` that holds something, relative to it."""
    return {
        Path(os.path.relpath(path.parent, root)).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }


_POC_TEMPLATES = WIZARD / "templates" / "poc"
#: The pattern each example blueprint scaffolds with.
_EXAMPLE_PATTERNS = {
    "audio_to_structured": "incident_reporting_blueprint.json",
    "document_to_structured": "document_extraction_blueprint.json",
    "rag": "rag_workflow_blueprint.json",
}
#: Every PoC pattern the scaffolder can write: one folder per template, _common
#: holding the files every pattern shares. A promoted template added there is
#: covered below without a change here.
_SCAFFOLD_PATTERNS = sorted(
    p.name for p in _POC_TEMPLATES.iterdir() if (p / "run_poc.py.tmpl").is_file()
)


def _pattern_blueprint(pattern: str, monkeypatch):
    """A blueprint the scaffolder writes with ``pattern``, asking for a PDF report too
    (pdf_report.py) so every file the scaffolder can add is written."""
    from solution_wizard import scaffolder
    from solution_wizard.blueprint import Blueprint

    example = _EXAMPLE_PATTERNS.get(pattern, "incident_reporting_blueprint.json")
    blueprint = Blueprint.from_file(WIZARD / "examples" / example)
    if pattern not in _EXAMPLE_PATTERNS:
        # No single module covers this pipeline: the _generic skeleton, or a
        # promoted template when one is saved under the pipeline's key.
        blueprint.components.selected_modules = []
        blueprint.components.selected_building_blocks = [
            "Transcriber",
            "PyMuPDFParser",
            "DataExtractor",
            "LLMJudge",
        ]
        key = "_generic" if pattern == "_generic" else pattern
        monkeypatch.setattr(scaffolder, "_derive_pattern_key", lambda _blueprint: key)
    blueprint.technical_spec["output_types"] = [
        *blueprint.technical_spec.get("output_types", []),
        "pdf",
    ]
    return blueprint


def test_the_coverage_test_below_knows_the_fixed_patterns():
    assert set(_EXAMPLE_PATTERNS) | {"_generic"} <= set(_SCAFFOLD_PATTERNS)
    assert len(_SCAFFOLD_PATTERNS) > len(_EXAMPLE_PATTERNS) + 1  # a promoted one too


@pytest.mark.parametrize("pattern", _SCAFFOLD_PATTERNS)
def test_the_scaffolder_and_the_diagram_and_docs_writers_write_only_the_listed_folders(
    tmp_path, monkeypatch, pattern
):
    from solution_wizard.bpmn_generator import write_bpmn
    from solution_wizard.docs_generator import generate_docs
    from solution_wizard.scaffolder import scaffold_poc
    from solution_wizard.visualizer import write_mermaid

    blueprint = _pattern_blueprint(pattern, monkeypatch)
    out = tmp_path / "scaffold_poc.py"
    scaffolded = scaffold_poc(blueprint, out, synthetic=True)
    assert scaffolded["pattern"] == pattern
    assert (out / "poc" / "pdf_report.py").is_file()
    assert _written_folders(out) <= set(TABLE["writes"]["scaffold_poc.py"])
    writers = {
        "generate_docs.py": lambda out: generate_docs(blueprint, out),
        "generate_mermaid.py": lambda out: write_mermaid(blueprint, out),
        "generate_bpmn.py": lambda out: write_bpmn(blueprint, out),
    }
    for script, write in writers.items():
        out = tmp_path / script
        write(out)
        assert _written_folders(out) <= set(TABLE["writes"][script]), script


def test_a_folder_search_through_a_link_is_refused(guard, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / ".env").write_text("KEY=x")
    _link_or_skip(guard.session / "poc" / "shared", elsewhere)
    assert guard.check("Grep", {"pattern": "KEY", "path": str(guard.session)})


def test_a_refused_folder_is_matched_in_any_case_where_the_filesystem_ignores_it(tmp_path):
    keep = tmp_path / "Keep"
    keep.mkdir()
    if not agent_tool_guard._ignores_case(keep):
        pytest.skip("this filesystem tells names apart by case")
    other_case = Path(str(keep).swapcase())
    assert agent_tool_guard.under_any(other_case / "x.py", [keep])
