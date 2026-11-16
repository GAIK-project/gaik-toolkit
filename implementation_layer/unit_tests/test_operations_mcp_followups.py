"""Follow-ups to the operations layer and the MCP server (issue #133). Offline."""

from __future__ import annotations

import asyncio
import base64
import io
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from gaik.operations import OperationSettings, classify_text, quiet_stdout

CONFIG = {"provider": "anthropic", "model": "fake-model", "api_key": "fake-key"}
LABELS = {"urgent": "Needs action today", "normal": "Can wait"}


# classify_text on a ProviderClient ----------------------------------------------------------


def _provider_client(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    llm = pytest.importorskip("gaik.software_components.llm")
    seen: dict[str, Any] = {}

    class Provider:
        provider, model, raw = "anthropic", "fake-model", None

        def chat_parsed(self, messages, response_format, **kwargs):
            seen.update(kwargs)
            return response_format(best="urgent", scores=[{"label": "urgent", "probability": 1}])

        def chat(self, *args, **kwargs):
            raise AssertionError

        def chat_stream(self, *args, **kwargs):
            raise AssertionError

        def embed(self, *args, **kwargs):
            raise AssertionError

    monkeypatch.setattr(llm, "build_compat_client", lambda config: Provider())
    return seen


def test_a_provider_client_gets_temperature_and_reasoning_effort(monkeypatch):
    seen = _provider_client(monkeypatch)
    settings = OperationSettings(config=CONFIG, temperature=0.0, reasoning_effort="low")

    classify_text("A leak.", LABELS, settings=settings)

    assert seen == {"model": "fake-model", "temperature": 0.0, "reasoning_effort": "low"}


def test_a_provider_client_gets_no_option_that_is_not_set(monkeypatch):
    seen = _provider_client(monkeypatch)
    settings = OperationSettings(config=CONFIG, temperature=None, reasoning_effort=None)

    classify_text("A leak.", LABELS, settings=settings)

    assert seen == {"model": "fake-model"}


# quiet_stdout: bytes and the file descriptor -------------------------------------------------


class _Bytes(io.BytesIO):
    def close(self) -> None:
        """Stay readable after the wrapper around it is collected."""

    def fileno(self) -> int:
        """A real console stream has a descriptor; a capture must not hand it out."""
        return 1


def _real_stdout(monkeypatch: pytest.MonkeyPatch) -> io.BytesIO:
    """A real stdout to watch. Set in the test body: pytest's own capture replaces
    ``sys.stdout`` after the fixtures have run."""
    raw = _Bytes()
    stream = io.TextIOWrapper(raw, encoding="utf-8", write_through=True)
    monkeypatch.setattr(sys, "stdout", stream)
    return raw


def test_bytes_written_to_stdout_buffer_stay_in_the_capture(monkeypatch):
    real_stdout = _real_stdout(monkeypatch)
    with quiet_stdout() as printed:
        sys.stdout.buffer.write("bytes line ä\n".encode())
        sys.stdout.buffer.flush()

    assert printed.getvalue() == "bytes line ä\n"
    assert real_stdout.getvalue() == b""


def test_stdout_buffer_outside_a_capture_is_the_real_one(monkeypatch):
    real_stdout = _real_stdout(monkeypatch)
    with quiet_stdout():
        pass

    sys.stdout.buffer.write(b"after\n")

    assert real_stdout.getvalue() == b"after\n"


def test_fileno_is_refused_inside_a_capture(monkeypatch):
    _real_stdout(monkeypatch)
    assert sys.stdout.fileno() == 1
    with quiet_stdout():
        with pytest.raises(io.UnsupportedOperation):
            sys.stdout.fileno()


def test_a_character_split_across_buffer_writes_is_decoded_whole(monkeypatch):
    _real_stdout(monkeypatch)
    encoded = "ä.".encode()
    with quiet_stdout() as printed:
        sys.stdout.buffer.write(encoded[:1])
        sys.stdout.buffer.write(encoded[1:])

    assert printed.getvalue() == "ä."


# MCP server ---------------------------------------------------------------------------------


def test_an_empty_root_argument_means_no_root(tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    from gaik.mcp_server import ServerSettings

    monkeypatch.chdir(tmp_path)

    assert ServerSettings.from_env({}, root="").root is None
    assert ServerSettings.from_env({}, root="   ").root is None
    assert ServerSettings.from_env({"GAIK_MCP_ROOT": str(tmp_path)}, root="").root is None


@pytest.mark.parametrize(
    "path",
    [
        r"C:\Users\someone\report.pdf",
        "C:/Users/someone/report.pdf",
        r"d:\data\report.pdf",
        r"\\fileserver\share\report.pdf",
        "//fileserver/share/report.pdf",
        r"\\?\C:\Users\someone\report.pdf",
        r"\Users\someone\report.pdf",
        r"~\Documents\report.pdf",
        "~/documents/report.pdf",
        "~someone/report.pdf",
        "/tmp/gaik-mcp-abc/input.docx",
        "/home/someone/report.pdf",
        "/srv",
        "file:///etc/report.pdf",
    ],
)
@pytest.mark.parametrize("framing", ["{}", "file '{}' is broken", "path={}", "({})", "<{}>"])
def test_the_local_path_filter_catches_every_path_form(path, framing):
    pytest.importorskip("mcp")
    from gaik.mcp_server import tools

    error = ValueError(framing.format(path) + " is not a DOCX document.")

    assert tools._message("parse_document", error) is None


@pytest.mark.parametrize(
    "text",
    [
        "Give exactly one of path and content_base64.",
        "max_chars must be 1 or more.",
        "The file type image/png is not supported.",
        "Use one and/or the other.",
        "A ratio of 1/2 is too small.",
    ],
)
def test_ordinary_messages_pass_the_local_path_filter(text):
    pytest.importorskip("mcp")
    from gaik.mcp_server import tools

    assert tools._message("parse_document", ValueError(text)) == text


def _parse_tool(monkeypatch: pytest.MonkeyPatch, root: Path) -> tuple[Any, list[Path]]:
    pytest.importorskip("mcp")
    import gaik.operations as operations
    from gaik.mcp_server import ServerSettings
    from gaik.mcp_server.tools import build_tools

    parsed: list[Path] = []

    def parse_document(path: Path, **kwargs: Any) -> Any:
        parsed.append(path)
        return SimpleNamespace(kind="text", pages=[None], text=Path(path).read_text())

    monkeypatch.setattr(operations, "parse_document", parse_document)
    tool = next(
        t for t in build_tools(ServerSettings(root=root.resolve())) if t.name == "parse_document"
    )
    return tool.run, parsed


def _page(run: Any, **arguments: Any) -> list[str]:
    windows: list[str] = []
    offset: int | None = 0
    while offset is not None:
        result = asyncio.run(run(offset=offset, max_chars=100, **arguments))
        windows.append(result["text"])
        offset = result["next_offset"]
    return windows


def test_paging_through_a_file_parses_it_once(tmp_path, monkeypatch):
    (tmp_path / "note.txt").write_text("x" * 300)
    run, parsed = _parse_tool(monkeypatch, tmp_path)

    windows = _page(run, path="note.txt")

    assert len(windows) == 3 and "".join(windows) == "x" * 300
    assert len(parsed) == 1


def test_paging_through_sent_content_parses_it_once(tmp_path, monkeypatch):
    run, parsed = _parse_tool(monkeypatch, tmp_path)
    content = base64.b64encode(b"y" * 250).decode()

    windows = _page(run, content_base64=content, filename="note.txt")

    assert "".join(windows) == "y" * 250
    assert len(parsed) == 1


def test_a_changed_file_is_parsed_again(tmp_path, monkeypatch):
    note = tmp_path / "note.txt"
    note.write_text("first")
    run, parsed = _parse_tool(monkeypatch, tmp_path)

    first = asyncio.run(run(path="note.txt"))
    note.write_text("second version")
    second = asyncio.run(run(path="note.txt"))

    assert (first["text"], second["text"]) == ("first", "second version")
    assert len(parsed) == 2


# packaging ----------------------------------------------------------------------------------


def test_all_cpu_includes_the_mcp_extra():
    import tomllib

    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    extras = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"][
        "optional-dependencies"
    ]

    assert "gaik[mcp]" in extras["all"]
    assert "gaik[mcp]" in extras["all-cpu"]
