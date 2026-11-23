"""The wizard agent's tools reach only its session and the wizard's own scripts.

The agent runs with bypassPermissions; a PreToolUse hook decides every tool
call, so files outside the session and the wizard's assets, other tools and
other commands are refused with a reason the agent can act on.
"""

import asyncio
import json

import pytest
from wizard_api.services import agent_tool_guard


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
        "refresh_schema_model.py",
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


def test_the_schema_refresh_script_is_refused_even_on_the_sessions_schemas(guard) -> None:
    # SKILL.md Step 4.5 asks for it, but it imports the session's output_schema.py,
    # and the guard runs only scripts that run the wizard's own code.
    for target in (guard.session / "poc" / "schemas", guard.other):
        command = f"python scripts/refresh_schema_model.py --schemas-dir {target.as_posix()}"
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


def test_the_ai_act_screening_scripts_are_allowed(guard) -> None:
    """SKILL.md Phase 12 has the agent check and render the screening it wrote."""
    s = guard.session
    check = "python ai_act_screening/scripts/check_screening.py"
    render = "python3 ai_act_screening/scripts/render_brief.py"
    for command in (
        f"{check} --pack {s}",
        f"{check} --pack {s} --status",
        f"{check} --pack {s} --hash",
        f"{check} --pack {s} --transcript {s}/conversation.md",
        f"{check} --pack {s} --screening {s}/ai_act_screening.json",
        f"{render} --pack {s}",
        f"{render} --pack {s} --outdated",
    ):
        assert guard.check("Bash", {"command": command}) is None, command


@pytest.mark.parametrize(
    "command",
    [
        # a path outside the session
        "python ai_act_screening/scripts/check_screening.py --pack {other}",
        "python ai_act_screening/scripts/check_screening.py --pack {session} --transcript /etc/x",
        "python ai_act_screening/scripts/render_brief.py --pack /etc",
        # an option the script does not have, an abbreviation, a value on a flag
        "python ai_act_screening/scripts/render_brief.py --pack {session} --output {session}/x.md",
        "python ai_act_screening/scripts/check_screening.py --pack {session} --stat",
        "python ai_act_screening/scripts/check_screening.py --pack {session} --status=yes",
        # nothing may be chained on
        "python ai_act_screening/scripts/check_screening.py --pack {session} --status; env",
        "python ai_act_screening/scripts/render_brief.py --pack {session} > /tmp/x",
    ],
)
def test_the_screening_scripts_keep_to_the_session_and_their_own_options(guard, command) -> None:
    command = command.format(session=guard.session, other=guard.other)

    assert guard.check("Bash", {"command": command})


@pytest.mark.parametrize(
    "command",
    [
        # a screening script's name, from the folder of the wizard's own scripts
        "python scripts/check_screening.py --pack {session}",
        "python scripts/render_brief.py --pack {session}",
        # the screening folder is not another place for the wizard's scripts
        "python ai_act_screening/scripts/validate_blueprint.py --blueprint {session}/b.json",
        # a file of that name in the session, or beside the references
        "python {session}/render_brief.py --pack {session}",
        "python ai_act_screening/references/render_brief.py --pack {session}",
        "python ai_act_screening/scripts/../../scripts/render_brief.py --pack {session}",
    ],
)
def test_a_script_is_run_only_from_its_own_folder(guard, command) -> None:
    command = command.format(session=guard.session)

    assert guard.check("Bash", {"command": command})


def test_the_screening_scripts_are_not_metered(guard) -> None:
    """They call no model and no network, so they fall under no metered limit."""
    command = f"python ai_act_screening/scripts/render_brief.py --pack {guard.session}"

    assert agent_tool_guard.call_kind("Bash", {"command": command}) == (
        "command",
        "render_brief.py",
    )


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


def test_scaffolding_a_blueprint_with_unprepared_text_is_refused(guard) -> None:
    bp = _blueprint(guard.session / "use_case.blueprint.json", 'Asset "id" with quotes')

    reason = guard.check("Bash", {"command": f"python scripts/scaffold_poc.py --blueprint {bp}"})

    assert reason and "double quotes" in reason


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


def test_the_agent_is_started_with_the_hook(tmp_path) -> None:
    from wizard_api.services import agent_service

    if not agent_service._SDK_AVAILABLE:
        pytest.skip("claude_agent_sdk is not installed")
    guard = agent_tool_guard.ToolGuard(tmp_path, tmp_path / "out")
    options = agent_service._build_options(tmp_path, tmp_path / "out", guard=guard)

    [matcher] = options.hooks["PreToolUse"]
    assert matcher.matcher is None  # every tool, not only Bash
    assert matcher.hooks[0].__self__.__class__ is agent_tool_guard.ToolGuard
