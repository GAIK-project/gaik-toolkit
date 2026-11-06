"""Working files of the tabular loader and the local transcriber are always removed."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_root(tmp_path, monkeypatch):
    root = tmp_path / "tmp"
    root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(root))
    return root


# --- tabular agent loader ---------------------------------------------------


def test_loader_leaves_no_working_file_after_a_load(temp_root):
    duckdb = pytest.importorskip("duckdb")
    pytest.importorskip("openpyxl")
    from gaik.software_components.tabular_agent.loader import _create_from_rows

    con = duckdb.connect(":memory:")
    _create_from_rows(con, "orders", ["item", "qty"], [["bolt", 3], ["nut", 5]])

    assert con.execute('SELECT SUM(qty) FROM "orders"').fetchone()[0] == 8
    assert list(temp_root.iterdir()) == []


def test_loader_leaves_no_working_file_after_a_failure(temp_root):
    pytest.importorskip("duckdb")
    pytest.importorskip("openpyxl")
    from gaik.software_components.tabular_agent.loader import TableLoadError, _create_from_rows

    seen = {}

    class _Refusing:
        def execute(self, sql, *_args, **_kwargs):
            seen["csv"] = Path(sql.split("read_csv('")[1].split("'")[0])
            seen["existed"] = seen["csv"].exists()
            raise RuntimeError("no such reader")

    with pytest.raises(TableLoadError):
        _create_from_rows(_Refusing(), "orders", ["item"], [["bolt"]])

    # The rows were in a directory of their own, not directly in the shared one.
    assert seen["existed"]
    assert seen["csv"].parent != temp_root
    assert seen["csv"].parent.parent == temp_root
    assert list(temp_root.iterdir()) == []


# --- local transcriber ------------------------------------------------------


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.fixture
def whisper_local(monkeypatch):
    pytest.importorskip("requests")
    from gaik.software_components.transcriber import whisper_local as module

    def fake_extract(video_path, output_dir=None):
        target = Path(output_dir) / f"{video_path.stem}_extracted.wav"
        target.write_bytes(b"RIFF")
        return target

    monkeypatch.setattr(module, "extract_audio_from_video", fake_extract)
    monkeypatch.setattr(module.requests, "get", lambda *a, **k: _Response({"status": "ok"}))
    return module


def test_extracted_audio_is_not_written_beside_the_video(whisper_local, temp_root, tmp_path):
    video = tmp_path / "meeting.mp4"
    video.write_bytes(b"video")
    seen = {}

    def post(url, data=None, files=None, headers=None, timeout=None):
        seen["name"] = files["file"][0]
        seen["dir"] = Path(files["file"][1].name).parent
        return _Response({"text": "hello", "segments": []})

    whisper_local.requests.post = post
    result = whisper_local.transcribe(video, api_base="http://local.test", key="k")

    assert result["text"] == "hello"
    assert seen["name"] == "meeting_extracted.wav"
    assert seen["dir"].parent == temp_root
    assert sorted(p.name for p in tmp_path.iterdir()) == ["meeting.mp4", "tmp"]
    assert list(temp_root.iterdir()) == []


def test_extracted_audio_is_removed_when_the_request_fails(whisper_local, temp_root, tmp_path):
    video = tmp_path / "meeting.mp4"
    video.write_bytes(b"video")

    def post(*_args, **_kwargs):
        raise ConnectionError("server went away")

    whisper_local.requests.post = post
    with pytest.raises(ConnectionError):
        whisper_local.transcribe(video, api_base="http://local.test", key="k")

    assert sorted(p.name for p in tmp_path.iterdir()) == ["meeting.mp4", "tmp"]
    assert list(temp_root.iterdir()) == []


def test_audio_input_is_sent_as_it_is(whisper_local, temp_root, tmp_path):
    audio = tmp_path / "call.wav"
    audio.write_bytes(b"RIFF")
    seen = {}

    def post(url, data=None, files=None, headers=None, timeout=None):
        seen["path"] = Path(files["file"][1].name)
        return _Response({"text": "hi", "segments": []})

    whisper_local.requests.post = post
    whisper_local.transcribe(audio, api_base="http://local.test", key="k")

    assert seen["path"] == audio
    assert audio.exists()
    assert list(temp_root.iterdir()) == []


def test_extraction_keeps_writing_beside_the_video_by_default(tmp_path, monkeypatch):
    from gaik.software_components.transcriber import whisper_local as module

    commands = []

    def run(cmd, capture_output=None, text=None):
        commands.append(cmd)
        return type("Done", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr(module.shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(module.subprocess, "run", run)
    video = tmp_path / "clip.mp4"

    assert module.extract_audio_from_video(video) == tmp_path / "clip_extracted.wav"
    other = tmp_path / "work"
    assert module.extract_audio_from_video(video, other) == other / "clip_extracted.wav"
    assert commands[1][-1] == str(other / "clip_extracted.wav")
