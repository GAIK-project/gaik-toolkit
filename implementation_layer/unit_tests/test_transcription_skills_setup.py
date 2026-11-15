"""The Claude Desktop transcription skills: the MCP server transcribes only audio and
video files in approved folders and answers with short errors; setup keeps the key out
of the skill folder, installs into a virtual environment and pins the file server."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import types
from pathlib import Path

import pytest

pytest.importorskip("dotenv")

SKILLS = Path(__file__).resolve().parents[1] / "no-code-assets" / "agent-skills" / "skills"
TRANSCRIBING_SKILLS = ("report-writing", "incident-report-writing", "construction-diary-creation")
WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 32


class _FakeFastMCP:
    def __init__(self, name: str) -> None:
        self.name = name

    def tool(self):
        return lambda function: function

    def run(self, transport: str) -> None:  # pragma: no cover - never started here
        raise AssertionError("the server must not start in a test")


@pytest.fixture(scope="module")
def server():
    """The server module, with a stand-in for FastMCP (the dev env has mcp 2.x)."""
    fastmcp = types.ModuleType("mcp.server.fastmcp")
    fastmcp.FastMCP = _FakeFastMCP
    saved = {name: sys.modules.get(name) for name in ("mcp", "mcp.server", "mcp.server.fastmcp")}
    sys.modules.update(
        {
            "mcp": types.ModuleType("mcp"),
            "mcp.server": types.ModuleType("mcp.server"),
            "mcp.server.fastmcp": fastmcp,
        }
    )
    try:
        path = SKILLS / "report-writing" / "transcription-MCP" / "server.py"
        spec = importlib.util.spec_from_file_location("transcription_server_under_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        yield module
    finally:
        for name, value in saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


@pytest.fixture
def folders(tmp_path):
    approved = tmp_path / "approved"
    other = tmp_path / "other"
    approved.mkdir()
    other.mkdir()
    return approved, other


def test_the_three_skills_ship_the_same_server():
    texts = {
        (SKILLS / name / "transcription-MCP" / "server.py").read_text(encoding="utf-8")
        for name in TRANSCRIBING_SKILLS
    }
    assert len(texts) == 1


def test_an_audio_file_in_an_approved_folder_is_accepted(server, folders):
    approved, _ = folders
    (approved / "sub").mkdir()
    recording = approved / "sub" / "meeting.wav"
    recording.write_bytes(WAV)
    assert server.checked_media_file(str(recording), [approved.resolve()]) == recording.resolve()


def test_a_file_outside_the_approved_folders_is_refused(server, folders):
    approved, other = folders
    recording = other / "meeting.wav"
    recording.write_bytes(WAV)
    with pytest.raises(server.FileRefusedError, match="outside the folders approved"):
        server.checked_media_file(str(recording), [approved.resolve()])
    traversal = approved / ".." / "other" / "meeting.wav"
    with pytest.raises(server.FileRefusedError, match="outside the folders approved"):
        server.checked_media_file(str(traversal), [approved.resolve()])


def test_a_link_inside_an_approved_folder_to_a_file_outside_is_refused(server, folders):
    approved, other = folders
    target = other / "meeting.wav"
    target.write_bytes(WAV)
    link = approved / "meeting.wav"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks are not available here")
    with pytest.raises(server.FileRefusedError, match="outside the folders approved"):
        server.checked_media_file(str(link), [approved.resolve()])


def test_a_file_with_another_extension_or_other_content_is_refused(server, folders):
    approved, _ = folders
    notes = approved / "notes.txt"
    notes.write_bytes(WAV)
    with pytest.raises(server.FileRefusedError, match="not an audio or video file"):
        server.checked_media_file(str(notes), [approved.resolve()])
    renamed = approved / "secrets.mp3"
    renamed.write_text("OPENAI_API_KEY=not-a-recording\n", encoding="utf-8")
    with pytest.raises(server.FileRefusedError, match="does not contain audio or video"):
        server.checked_media_file(str(renamed), [approved.resolve()])


def test_no_approved_folder_refuses_every_file(server, folders):
    approved, _ = folders
    recording = approved / "meeting.wav"
    recording.write_bytes(WAV)
    with pytest.raises(server.FileRefusedError, match="No folder is approved"):
        server.checked_media_file(str(recording), [])


def test_a_drive_root_or_the_home_folder_is_never_approved(server, tmp_path, monkeypatch):
    home = tmp_path / "home"
    work = home / "work"
    work.mkdir(parents=True)
    monkeypatch.setattr(server.Path, "home", classmethod(lambda cls: home))
    root = str(Path(tmp_path.anchor))
    approved = server.approved_folders(
        [str(home), root, str(work), str(tmp_path / "missing")], env_value="", start=home
    )
    assert approved == [work.resolve()]


def test_named_folders_replace_the_working_folder(server, tmp_path, monkeypatch):
    monkeypatch.setattr(server.Path, "home", classmethod(lambda cls: tmp_path / "home"))
    start, given, listed = (tmp_path / n for n in ("start", "given", "listed"))
    for folder in (start, given, listed):
        folder.mkdir()
    approved = server.approved_folders([str(given)], env_value=str(listed), start=start)
    assert approved == [given.resolve(), listed.resolve()]
    assert server.approved_folders([], env_value="", start=start) == [start.resolve()]


def test_refused_named_folders_never_fall_back_to_the_working_folder(server, tmp_path, monkeypatch):
    monkeypatch.setattr(server.Path, "home", classmethod(lambda cls: tmp_path / "home"))
    start = tmp_path / "start"
    start.mkdir()
    approved = server.approved_folders([str(tmp_path / "missing")], env_value="", start=start)
    assert approved == []


def test_check_folder_prints_the_absolute_folder_or_exits_1(server, tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    work = home / "work"
    work.mkdir(parents=True)
    monkeypatch.setattr(server.Path, "home", classmethod(lambda cls: home))
    monkeypatch.chdir(home)
    with pytest.raises(SystemExit) as done:
        server.main(["--check-folder", "work"])
    assert done.value.code == 0 and capsys.readouterr().out.strip() == str(work.resolve())
    for refused in (str(home), "", str(tmp_path / "missing")):
        with pytest.raises(SystemExit) as done:
            server.main(["--check-folder", refused])
        assert done.value.code == 1 and capsys.readouterr().out == ""


@pytest.mark.parametrize(
    ("name", "head"),
    [
        ("old-camera.mov", b"\x00\x00\x00\x08wide\x00\x00\x00\x00mdat"),
        ("long.wav", b"RF64\xff\xff\xff\xffWAVEds64"),
        ("padded.mp3", b"\x00" * 600 + b"\xff\xfb\x90\x64"),
    ],
)
def test_recordings_in_less_common_layouts_are_accepted(server, folders, name, head):
    approved, _ = folders
    recording = approved / name
    recording.write_bytes(head + b"\x00" * 64)
    assert server.checked_media_file(str(recording), [approved.resolve()]) == recording.resolve()


def test_a_refused_file_never_reaches_the_provider(server, folders, monkeypatch):
    approved, other = folders
    recording = other / "meeting.wav"
    recording.write_bytes(WAV)
    called = []
    fake = types.ModuleType("gaik.software_components.transcriber")
    fake.Transcriber = lambda **kwargs: called.append(kwargs)
    monkeypatch.setitem(sys.modules, "gaik.software_components.transcriber", fake)
    monkeypatch.setattr(server, "APPROVED", [approved.resolve()])
    answer = server.transcribe_audio(str(recording))
    assert answer.startswith("Error:") and "outside the folders approved" in answer
    assert called == []


def test_a_provider_failure_returns_a_short_error_without_a_traceback(server, folders, monkeypatch):
    approved, _ = folders
    recording = approved / "meeting.wav"
    recording.write_bytes(WAV)

    class FailingTranscriber:
        def __init__(self, **kwargs):
            pass

        def transcribe(self, **kwargs):
            raise RuntimeError("provider said: request id 123, key sk-test-abc")

    fake = types.ModuleType("gaik.software_components.transcriber")
    fake.Transcriber = FailingTranscriber
    monkeypatch.setitem(sys.modules, "gaik.software_components.transcriber", fake)
    monkeypatch.setattr(server, "APPROVED", [approved.resolve()])
    monkeypatch.setattr(server, "_api_config", lambda: {})
    answer = server.transcribe_audio(str(recording))
    assert answer.startswith("Error: transcribing meeting.wav failed (RuntimeError)")
    assert "log has the details" in answer
    assert "Traceback" not in answer and "sk-test" not in answer and "request id" not in answer


@pytest.mark.parametrize("name", TRANSCRIBING_SKILLS)
def test_setup_keeps_the_key_out_of_the_skill_folder_and_uses_a_virtual_environment(name):
    text = (SKILLS / name / "setup.bat").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=!OPENAI_KEY!" not in text and "AZURE_API_KEY=!AZURE_KEY!" not in text
    assert '> "%TRANSCRIPTION_MCP_PATH%\\.env"' not in text
    assert 'setx OPENAI_API_KEY "!OPENAI_KEY!"' in text
    assert 'setx AZURE_API_KEY "!AZURE_KEY!"' in text
    assert 'python -m venv "%VENV_DIR%"' in text
    assert '"%VENV_PYTHON%" -m pip install' in text
    assert "\npip install" not in text
    assert '"command": "!VENV_PYTHON_JSON!"' in text
    assert '"--folder", "!WORK_FOLDER_JSON!"' in text
    assert '"%VENV_PYTHON%" "%SERVER_PATH%" --check-folder "%WORK_FOLDER%"' in text


def test_the_file_server_is_installed_from_a_lockfile_and_limited_to_the_chosen_folder():
    skill = SKILLS / "report-writing"
    text = (skill / "setup.bat").read_text(encoding="utf-8")
    assert "npx" not in text and '"C:\\\\"' not in text
    assert "call npm ci --omit=dev --ignore-scripts" in text
    assert '"args": ["!FS_SERVER_JSON!", "!WORK_FOLDER_JSON!"]' in text

    manifest = json.loads((skill / "filesystem-MCP" / "package.json").read_text("utf-8"))
    lock = json.loads((skill / "filesystem-MCP" / "package-lock.json").read_text("utf-8"))
    pinned = manifest["dependencies"]["@modelcontextprotocol/server-filesystem"]
    packages = {k: v for k, v in lock["packages"].items() if k}
    assert packages["node_modules/@modelcontextprotocol/server-filesystem"]["version"] == pinned
    for key, entry in packages.items():
        assert entry.get("integrity", "").startswith("sha512-"), key
        assert entry["resolved"].startswith("https://registry.npmjs.org/"), key


@pytest.mark.parametrize(
    ("error", "hint"),
    [
        (ModuleNotFoundError("gaik"), "run setup.bat again"),
        (FileNotFoundError("ffmpeg"), "FFmpeg"),
        (type("AuthenticationError", (Exception,), {})("bad key"), "refused the key"),
    ],
)
def test_a_failure_names_what_to_check(server, error, hint):
    assert hint in server._hint(error)


def test_a_legacy_env_file_is_read_only_when_no_key_is_set(server, tmp_path, monkeypatch):
    legacy = tmp_path / ".env"
    legacy.write_text("OPENAI_API_TYPE=azure\nAZURE_API_KEY=old\n", encoding="utf-8")
    monkeypatch.setattr(server, "__file__", str(tmp_path / "server.py"))
    monkeypatch.setattr(server, "_user_environment_value", lambda name: "")
    for name in server.SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "new")
    server.load_settings()
    assert "OPENAI_API_TYPE" not in server.os.environ and "AZURE_API_KEY" not in server.os.environ

    monkeypatch.delenv("OPENAI_API_KEY")
    server.load_settings()
    assert server.os.environ["AZURE_API_KEY"] == "old"
    # The loop above recorded both names as unset, so monkeypatch removes them again.


@pytest.mark.parametrize("name", TRANSCRIBING_SKILLS)
def test_setup_has_no_exclamation_mark_outside_delayed_variables(name):
    """setup.bat runs with delayed expansion, where a stray ! empties part of a line."""
    for number, line in enumerate((SKILLS / name / "setup.bat").read_text("utf-8").splitlines()):
        stripped = re.sub(r"![A-Za-z_][A-Za-z0-9_]*!", "", line)
        assert "!" not in stripped, f"setup.bat line {number + 1}: {line}"
