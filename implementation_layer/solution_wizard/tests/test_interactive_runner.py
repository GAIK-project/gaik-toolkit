"""The interactive runner gives the agent only the tools and settings the wizard uses.

These tests build the runner's options and call its permission callback directly;
no model or CLI is started.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import re
import sys
from pathlib import Path

import pytest

pytest.importorskip("claude_agent_sdk")
pytest.importorskip("dotenv")

from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "run_wizard_interactive", ROOT / "run_wizard_interactive.py"
)
runner = importlib.util.module_from_spec(_spec)
sys.modules["run_wizard_interactive"] = runner
_spec.loader.exec_module(runner)

FOUNDRY = {
    "CLAUDE_CODE_USE_FOUNDRY": "1",
    "ANTHROPIC_FOUNDRY_API_KEY": "test-foundry-key",
    "ANTHROPIC_FOUNDRY_RESOURCE": "test-resource",
}


class _Answers:
    """Stands in for the terminal question; records what was asked."""

    def __init__(self, answer: bool) -> None:
        self.answer = answer
        self.questions: list[str] = []

    async def __call__(self, question: str) -> bool:
        self.questions.append(question)
        return self.answer


def _decide(permissions, tool: str, tool_input: dict):
    return asyncio.run(permissions(tool, tool_input, None))


# ── Options ───────────────────────────────────────────────────────────────────


def test_the_session_has_only_the_wizard_tools_and_no_blanket_approval(tmp_path) -> None:
    options = runner.build_session_options({"PATH": "/bin"}, "test-model", tmp_path)
    assert options.tools == ["Read", "Grep", "Glob", "Write", "Edit", "Bash"]
    assert options.allowed_tools == []
    assert options.permission_mode == "default"
    assert isinstance(options.can_use_tool, runner.WizardPermissions)
    assert set(options.disallowed_tools) == {"Read(**/.env)", "Read(**/.env.*)"}
    assert options.setting_sources == []
    assert options.cwd == str(runner.WIZARD_DIR)
    assert options.add_dirs == [str(tmp_path)]


def test_the_preflight_has_no_tools() -> None:
    options = runner.build_preflight_options({"PATH": "/bin"}, "test-model")
    assert options.tools == []
    assert options.allowed_tools == []
    assert options.permission_mode == "default"
    assert options.max_turns == 1


# ── Environment ───────────────────────────────────────────────────────────────


def test_the_agent_env_keeps_provider_and_system_settings_only() -> None:
    source = {
        **FOUNDRY,
        "PATH": "/usr/bin",
        "HOME": "/home/test",
        "AZURE_API_KEY": "test-azure-key",
        "AWS_SECRET_ACCESS_KEY": "not-for-the-agent",
        "GITHUB_TOKEN": "not-for-the-agent",
        "DATABASE_URL": "not-for-the-agent",
        "SSH_AUTH_SOCK": "not-for-the-agent",
        "CLAUDECODE": "1",
    }
    env = runner.build_agent_env(source)
    for name in (*FOUNDRY, "PATH", "HOME", "AZURE_API_KEY"):
        assert env[name] == source[name]
    for name in ("AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN", "DATABASE_URL", "SSH_AUTH_SOCK"):
        assert name not in env
    assert "CLAUDECODE" not in env
    assert env["API_TIMEOUT_MS"] == "600000"
    assert env["DISABLE_TELEMETRY"] == "1"
    assert env["CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR"] == "1"


def test_a_named_variable_is_passed_on_request() -> None:
    env = runner.build_agent_env({"MY_PROVIDER_SETTING": "x"}, ["MY_PROVIDER_SETTING"])
    assert env["MY_PROVIDER_SETTING"] == "x"


def test_load_environment_reads_the_env_file_without_exporting_it(tmp_path, monkeypatch) -> None:
    for name in (*FOUNDRY, "OTHER_SERVICE_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "".join(f"{k}={v}\n" for k, v in FOUNDRY.items()) + "OTHER_SERVICE_TOKEN=nope\n",
        encoding="utf-8",
    )
    env = runner.load_environment(env_file)
    assert env["ANTHROPIC_FOUNDRY_API_KEY"] == "test-foundry-key"
    assert "OTHER_SERVICE_TOKEN" not in env
    assert "ANTHROPIC_FOUNDRY_API_KEY" not in os.environ


def test_the_shell_value_wins_over_the_env_file(tmp_path, monkeypatch) -> None:
    for k, v in FOUNDRY.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_RESOURCE", "from-shell")
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_FOUNDRY_RESOURCE=from-file\n", encoding="utf-8")
    assert runner.load_environment(env_file)["ANTHROPIC_FOUNDRY_RESOURCE"] == "from-shell"


def test_load_environment_still_names_missing_foundry_settings(tmp_path, monkeypatch) -> None:
    for name in FOUNDRY:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_FOUNDRY_API_KEY"):
        runner.load_environment(tmp_path / "missing.env")


def test_narrow_process_environment_leaves_only_the_agent_env(monkeypatch) -> None:
    monkeypatch.setattr(os, "environ", dict(os.environ))
    os.environ["OTHER_SERVICE_TOKEN"] = "nope"
    runner.narrow_process_environment({"PATH": "/usr/bin", **FOUNDRY})
    assert "OTHER_SERVICE_TOKEN" not in os.environ
    assert os.environ["ANTHROPIC_FOUNDRY_API_KEY"] == "test-foundry-key"


def test_the_session_starts_the_agent_with_the_narrowed_environment(monkeypatch) -> None:
    monkeypatch.setattr(os, "environ", {"OTHER_SERVICE_TOKEN": "nope", **FOUNDRY})
    seen: dict = {}

    class FakeClient:
        def __init__(self, options) -> None:
            seen["options"] = options

        async def __aenter__(self):
            # The SDK copies os.environ when it starts the CLI, here.
            seen["environ"] = dict(os.environ)
            return self

        async def __aexit__(self, *exc) -> None:
            return None

        async def query(self, prompt: str) -> None:
            return None

        async def receive_response(self):
            return
            yield

    monkeypatch.setattr(runner, "ClaudeSDKClient", FakeClient)
    monkeypatch.setattr(runner, "_read_user_input", lambda: None)
    env = runner.build_agent_env(dict(os.environ))
    assert asyncio.run(runner.run_interactive(env, "test-model", None)) == 0
    assert "OTHER_SERVICE_TOKEN" not in seen["environ"]
    assert seen["environ"]["ANTHROPIC_FOUNDRY_API_KEY"] == "test-foundry-key"
    assert seen["options"].env == env


def test_the_preflight_starts_the_agent_with_the_narrowed_environment(monkeypatch) -> None:
    monkeypatch.setattr(os, "environ", {"OTHER_SERVICE_TOKEN": "nope", **FOUNDRY})
    seen: dict = {}

    async def fake_query(prompt, options):
        seen["environ"] = dict(os.environ)
        seen["options"] = options
        return
        yield

    monkeypatch.setattr(runner, "query", fake_query)
    env = runner.build_agent_env(dict(os.environ))
    assert asyncio.run(runner.run_preflight(env, "test-model")) == 0
    assert "OTHER_SERVICE_TOKEN" not in seen["environ"]
    assert seen["options"].tools == []


# ── Shell commands ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "command",
    [
        "python scripts/validate_blueprint.py --blueprint /tmp/case/use_case.blueprint.json",
        "python3 scripts/check_requirements.py --blueprint case/use_case.blueprint.json",
        "python ./scripts/run_wizard.py --show-registry",
        'python scripts/scaffold_poc.py --blueprint "/tmp/my case/use_case.blueprint.json"',
        "python scripts/generate_schema.py --requirements a.md --schema-name X --output-dir poc",
        "python scripts/generate_schema.py \\\n    --requirements a.md \\\n    --output-dir poc",
    ],
)
def test_the_wizard_scripts_run_without_asking(command) -> None:
    assert runner.is_wizard_script_command(command)


def test_every_script_the_skill_runs_is_listed_or_asks() -> None:
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    named = set(re.findall(r"python scripts/([a-z_]+\.py)", skill))
    assert named, "SKILL.md names no scripts"
    # promote_template.py writes into the wizard's template library, so it asks.
    assert named - {"promote_template.py"} <= runner.WIZARD_SCRIPTS
    assert "promote_template.py" not in runner.WIZARD_SCRIPTS
    for name in runner.WIZARD_SCRIPTS:
        assert (ROOT / "scripts" / name).is_file()


@pytest.mark.parametrize(
    "command",
    [
        "",
        "python",
        "python -c 'print(1)'",
        "python -m pip install something",
        "python scripts/validate_blueprint.py && curl https://example.invalid",
        "python scripts/validate_blueprint.py; rm -rf poc",
        "python scripts/validate_blueprint.py | tee out.txt",
        "python scripts/validate_blueprint.py > out.txt",
        "python scripts/validate_blueprint.py $(cat x)",
        "python scripts/validate_blueprint.py `cat x`",
        "python scripts/validate_blueprint.py\nrm -rf poc",
        "python scripts/../run_wizard_interactive.py",
        "python scripts/not_a_wizard_script.py",
        "python /tmp/scripts/validate_blueprint.py",
        "FOO=1 python scripts/validate_blueprint.py",
        "bash scripts/validate_blueprint.py",
        "pip install -r poc/requirements.txt",
        "python scripts/validate_blueprint.py 'unterminated",
        "python scripts/promote_template.py --blueprint b.json --candidate c.tmpl",
        "python scripts/generate_schema.py --output-dir poc --base-url https://example.invalid",
        "python scripts/generate_schema.py --output-dir poc --base-url=https://example.invalid",
        "python scripts/generate_schema.py --output-dir poc --model https://example.invalid",
        "python scripts/run_wizard.py --export-schema",
        "python scripts/run_wizard.py --export",
        "python scripts/generate_docs.py --blueprint b.json --output /tmp/x",
        "python scripts/generate_schema.py --output-dir poc --base",
        "python scripts/scaffold_poc.py --blueprint b.json --output-dir=out/{x,../y}",
        "python scripts/scaffold_poc.py --blueprint b.json --output-dir ~/x",
        "python scripts/scaffold_poc.py --blueprint b*.json",
        "python scripts/scaffold_poc.py --blueprint b?.json",
        "python scripts/scaffold_poc.py --blueprint [b].json",
    ],
)
def test_other_commands_are_not_allowed_outright(command) -> None:
    assert not runner.is_wizard_script_command(command)


def test_an_unlisted_command_runs_only_when_the_user_says_yes(tmp_path) -> None:
    yes, no = _Answers(True), _Answers(False)
    command = {"command": "pip install -r poc/requirements.txt"}
    assert isinstance(
        _decide(runner.WizardPermissions(tmp_path, ask=yes), "Bash", command),
        PermissionResultAllow,
    )
    assert "pip install" in yes.questions[0]
    assert isinstance(
        _decide(runner.WizardPermissions(tmp_path, ask=no), "Bash", command),
        PermissionResultDeny,
    )


def test_a_wizard_script_on_the_output_folder_does_not_ask(tmp_path) -> None:
    ask = _Answers(False)
    blueprint = tmp_path / "use_case.blueprint.json"
    command = f'python scripts/run_wizard.py --blueprint "{blueprint}" --output-dir "{tmp_path}"'
    result = _decide(runner.WizardPermissions(tmp_path, ask=ask), "Bash", {"command": command})
    assert isinstance(result, PermissionResultAllow)
    assert ask.questions == []


@pytest.mark.parametrize(
    "arguments",
    [
        "--blueprint {case}/b.json --output-dir {other}",
        "--blueprint={other}/b.json",
        "--blueprint {case}/b.json --output-dir scripts",
        "--blueprint {case}/b.json --output-dir",
    ],
)
def test_a_wizard_script_writing_outside_the_output_folder_asks(arguments, tmp_path) -> None:
    ask = _Answers(False)
    case, other = tmp_path / "case", tmp_path / "other"
    command = "python scripts/scaffold_poc.py " + arguments.format(case=case, other=other)
    result = _decide(runner.WizardPermissions(case, ask=ask), "Bash", {"command": command})
    assert isinstance(result, PermissionResultDeny)
    assert len(ask.questions) == 1


def test_a_requirements_file_outside_the_readable_folders_asks(tmp_path) -> None:
    ask = _Answers(False)
    case = tmp_path / "case"
    command = (
        f"python scripts/generate_schema.py --requirements {tmp_path}/secret/notes.txt "
        f"--schema-name X --output-dir {case}/poc"
    )
    result = _decide(runner.WizardPermissions(case, ask=ask), "Bash", {"command": command})
    assert isinstance(result, PermissionResultDeny)
    assert len(ask.questions) == 1


def test_a_requirements_file_in_the_output_folder_does_not_ask(tmp_path) -> None:
    ask = _Answers(False)
    command = (
        f"python scripts/generate_schema.py --requirements {tmp_path}/poc/prompts/req.md "
        f"--schema-name X --output-dir {tmp_path}/poc --provider azure"
    )
    result = _decide(runner.WizardPermissions(tmp_path, ask=ask), "Bash", {"command": command})
    assert isinstance(result, PermissionResultAllow)
    assert ask.questions == []


def test_a_script_on_an_output_folder_inside_the_wizard_folder_does_not_ask() -> None:
    ask = _Answers(False)
    permissions = runner.WizardPermissions(runner.WIZARD_DIR / "my-case-output", ask=ask)
    command = (
        "python scripts/generate_docs.py --blueprint my-case-output/use_case.blueprint.json "
        "--output-dir my-case-output"
    )
    assert isinstance(_decide(permissions, "Bash", {"command": command}), PermissionResultAllow)
    assert ask.questions == []


def test_two_writes_into_one_new_folder_ask_once(tmp_path) -> None:
    ask = _Answers(True)
    permissions = runner.WizardPermissions(None, ask=ask)
    case = tmp_path / "case"

    async def both():
        return await asyncio.gather(
            permissions("Write", {"file_path": str(case / "a.json")}, None),
            permissions("Write", {"file_path": str(case / "b.json")}, None),
        )

    results = asyncio.run(both())
    assert all(isinstance(r, PermissionResultAllow) for r in results)
    assert len(ask.questions) == 1


def test_questions_are_asked_one_at_a_time(tmp_path) -> None:
    active, most = 0, 0

    async def slow_ask(question: str) -> bool:
        nonlocal active, most
        active += 1
        most = max(most, active)
        await asyncio.sleep(0.01)
        active -= 1
        return False

    permissions = runner.WizardPermissions(tmp_path, ask=slow_ask)

    async def both():
        await asyncio.gather(
            permissions("Bash", {"command": "pip install a"}, None),
            permissions("Write", {"file_path": "/elsewhere-folder/x.txt"}, None),
        )

    asyncio.run(both())
    assert most == 1


# ── Files ─────────────────────────────────────────────────────────────────────


def test_writes_in_the_output_folder_do_not_ask(tmp_path) -> None:
    ask = _Answers(False)
    permissions = runner.WizardPermissions(tmp_path, ask=ask)
    for tool in ("Write", "Edit"):
        result = _decide(permissions, tool, {"file_path": str(tmp_path / "poc" / "run_poc.py")})
        assert isinstance(result, PermissionResultAllow)
    assert ask.questions == []


def test_a_new_folder_asks_once_and_is_remembered(tmp_path) -> None:
    ask = _Answers(True)
    permissions = runner.WizardPermissions(None, ask=ask)
    case = tmp_path / "case"
    first = _decide(permissions, "Write", {"file_path": str(case / "use_case.blueprint.json")})
    second = _decide(permissions, "Write", {"file_path": str(case / "poc" / "run_poc.py")})
    assert isinstance(first, PermissionResultAllow)
    assert isinstance(second, PermissionResultAllow)
    assert len(ask.questions) == 1
    assert str(case) in ask.questions[0]


def test_a_declined_folder_is_not_written(tmp_path) -> None:
    permissions = runner.WizardPermissions(None, ask=_Answers(False))
    result = _decide(permissions, "Write", {"file_path": str(tmp_path / "x.txt")})
    assert isinstance(result, PermissionResultDeny)
    assert permissions.write_dirs == []


def test_a_write_outside_the_output_folder_asks(tmp_path) -> None:
    ask = _Answers(False)
    permissions = runner.WizardPermissions(tmp_path / "case", ask=ask)
    result = _decide(permissions, "Edit", {"file_path": str(tmp_path / "elsewhere" / "x.py")})
    assert isinstance(result, PermissionResultDeny)
    assert len(ask.questions) == 1


def test_a_relative_path_that_leaves_the_output_folder_asks(tmp_path) -> None:
    ask = _Answers(False)
    case = tmp_path / "case"
    permissions = runner.WizardPermissions(case, ask=ask)
    result = _decide(permissions, "Write", {"file_path": str(case / ".." / "x.py")})
    assert isinstance(result, PermissionResultDeny)
    assert len(ask.questions) == 1


@pytest.mark.parametrize("approved", [True, False])
def test_the_wizard_own_files_always_ask_and_are_not_remembered(approved) -> None:
    ask = _Answers(approved)
    # Even an output folder that contains the wizard does not cover its files.
    permissions = runner.WizardPermissions(runner.WIZARD_DIR.parent, ask=ask)
    for target in ("scripts/validate_blueprint.py", str(runner.WIZARD_DIR / "SKILL.md")):
        result = _decide(permissions, "Edit", {"file_path": target})
        expected = PermissionResultAllow if approved else PermissionResultDeny
        assert isinstance(result, expected)
    assert len(ask.questions) == 2
    assert all(runner.WIZARD_DIR != d for d in permissions.write_dirs)


def test_an_output_folder_inside_the_wizard_folder_does_not_ask() -> None:
    ask = _Answers(False)
    case = runner.WIZARD_DIR / "my-case-output"
    permissions = runner.WizardPermissions(case, ask=ask)
    result = _decide(permissions, "Write", {"file_path": "my-case-output/poc/run_poc.py"})
    assert isinstance(result, PermissionResultAllow)
    assert ask.questions == []


def test_a_new_output_folder_inside_the_wizard_folder_is_remembered() -> None:
    ask = _Answers(True)
    permissions = runner.WizardPermissions(None, ask=ask)
    for name in ("use_case.blueprint.json", "poc/run_poc.py"):
        result = _decide(permissions, "Write", {"file_path": f"my-new-case/{name}"})
        assert isinstance(result, PermissionResultAllow)
    assert len(ask.questions) == 1
    assert permissions.write_dirs == [runner.WIZARD_DIR / "my-new-case"]


def test_a_yes_for_the_home_folder_is_not_remembered(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(runner.Path, "home", classmethod(lambda cls: tmp_path))
    ask = _Answers(True)
    permissions = runner.WizardPermissions(None, ask=ask)
    for name in ("notes.md", "other.md"):
        result = _decide(permissions, "Write", {"file_path": str(tmp_path / name)})
        assert isinstance(result, PermissionResultAllow)
    assert len(ask.questions) == 2
    assert permissions.write_dirs == []


def test_a_write_without_a_path_is_refused(tmp_path) -> None:
    ask = _Answers(True)
    result = _decide(runner.WizardPermissions(tmp_path, ask=ask), "Write", {})
    assert isinstance(result, PermissionResultDeny)
    assert ask.questions == []


# ── Other tools ───────────────────────────────────────────────────────────────


def test_reading_in_the_wizard_and_output_folders_does_not_ask(tmp_path) -> None:
    ask = _Answers(False)
    permissions = runner.WizardPermissions(tmp_path, ask=ask)
    calls = [
        ("Read", {"file_path": "SKILL.md"}),
        ("Read", {"file_path": str(tmp_path / "use_case.blueprint.json")}),
        ("Grep", {"pattern": "Extractor", "path": "registries"}),
        ("Glob", {"pattern": "**/*.md"}),
        ("Glob", {"pattern": "*.json", "path": str(tmp_path)}),
    ]
    for tool, tool_input in calls:
        assert isinstance(_decide(permissions, tool, tool_input), PermissionResultAllow)
    assert ask.questions == []


def test_reading_a_new_folder_asks_once(tmp_path) -> None:
    ask = _Answers(True)
    permissions = runner.WizardPermissions(tmp_path / "case", ask=ask)
    docs = tmp_path / "docs"
    for name in ("a.pdf", "b.pdf"):
        assert isinstance(
            _decide(permissions, "Read", {"file_path": str(docs / name)}), PermissionResultAllow
        )
    assert len(ask.questions) == 1


@pytest.mark.parametrize(
    ("tool", "tool_input"),
    [
        ("Read", {"file_path": "../.env"}),
        ("Read", {"file_path": ".env"}),
        ("Read", {"file_path": "{case}/.env.local"}),
        ("Grep", {"pattern": "KEY", "path": "{case}", "glob": ".env*"}),
        ("Grep", {"pattern": "KEY", "path": "{case}/.env"}),
        ("Glob", {"pattern": "**/.env", "path": "{case}"}),
    ],
)
def test_an_env_file_is_refused_without_asking(tool, tool_input, tmp_path) -> None:
    ask = _Answers(True)
    tool_input = {k: v.format(case=tmp_path) for k, v in tool_input.items()}
    permissions = runner.WizardPermissions(tmp_path, ask=ask)
    assert isinstance(_decide(permissions, tool, tool_input), PermissionResultDeny)
    assert ask.questions == []


def test_a_search_for_env_in_file_contents_is_not_refused(tmp_path) -> None:
    permissions = runner.WizardPermissions(tmp_path, ask=_Answers(False))
    result = _decide(permissions, "Grep", {"pattern": "load .env", "path": str(tmp_path)})
    assert isinstance(result, PermissionResultAllow)


@pytest.mark.parametrize("pattern", ["/etc/*", "~/.ssh/*", "../**/*.md"])
def test_a_glob_that_leaves_its_folder_asks(pattern, tmp_path) -> None:
    ask = _Answers(False)
    result = _decide(runner.WizardPermissions(tmp_path, ask=ask), "Glob", {"pattern": pattern})
    assert isinstance(result, PermissionResultDeny)
    assert len(ask.questions) == 1


@pytest.mark.parametrize("tool", ["WebFetch", "WebSearch", "Task", "NotebookEdit", "mcp__x__y"])
def test_other_tools_are_refused_without_asking(tool, tmp_path) -> None:
    ask = _Answers(True)
    result = _decide(runner.WizardPermissions(tmp_path, ask=ask), tool, {})
    assert isinstance(result, PermissionResultDeny)
    assert ask.questions == []
