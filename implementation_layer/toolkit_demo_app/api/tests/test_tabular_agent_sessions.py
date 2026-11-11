"""Tabular agent sessions: expiry by last use, no eviction under a question, upload names."""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import pytest
from api.routers import tabular_agent as route
from fastapi import FastAPI
from fastapi.testclient import TestClient


class Agent:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def sessions(monkeypatch, tmp_path) -> dict:
    store: dict = {}
    monkeypatch.setattr(route, "_SESSIONS", store)
    monkeypatch.setattr(route, "_SESSIONS_LOCK", asyncio.Lock())
    monkeypatch.setattr(route.tempfile, "tempdir", str(tmp_path))
    monkeypatch.setenv("AZURE_API_KEY", "key")
    return store


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(route.router, prefix="/tabular-agent")
    return TestClient(app)


def _session(tmp_path: Path, name: str, *, idle_for: float = 0.0, busy: int = 0) -> dict:
    folder = tmp_path / name
    folder.mkdir()
    session = {
        "agent": Agent(),
        "dir": str(folder),
        "last_used": time.time() - idle_for,
        "busy": busy,
        "closing": False,
        "filename": "data.csv",
        "tables": [],
    }
    route._SESSIONS[name] = session
    return session


def _fake_load(monkeypatch) -> list[Path]:
    stored: list[Path] = []

    def load(path: Path, layout_inference: str):
        stored.append(path)
        return Agent(), [], "schema"

    monkeypatch.setattr(route, "_load_agent", load)
    return stored


def _folders(tmp_path: Path) -> list[Path]:
    return sorted(tmp_path.glob("gaik_tabular_*"))


def test_the_sweep_expires_an_idle_session_without_an_upload(monkeypatch, tmp_path) -> None:
    idle = _session(tmp_path, "idle", idle_for=route.SESSION_TTL_SECONDS + 1)
    _session(tmp_path, "recent", idle_for=60)
    sleeps = 0

    async def sleep(seconds: float) -> None:
        nonlocal sleeps
        sleeps += 1
        if sleeps == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(route.asyncio, "sleep", sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(route.cleanup_idle_sessions())

    assert list(route._SESSIONS) == ["recent"]
    assert idle["agent"].closed
    assert not Path(idle["dir"]).exists()


def test_a_question_renews_the_session(monkeypatch, tmp_path, client) -> None:
    session = _session(tmp_path, "s1", idle_for=route.SESSION_TTL_SECONDS - 60)
    monkeypatch.setattr(
        route,
        "_run_ask",
        lambda agent, question: route.AskResponse(question=question, answer="42", succeeded=True),
    )

    response = client.post("/tabular-agent/ask", json={"session_id": "s1", "question": "How many?"})

    assert response.status_code == 200
    assert time.time() - session["last_used"] < 5
    asyncio.run(route._evict_stale())
    assert list(route._SESSIONS) == ["s1"]


def test_a_session_with_a_question_in_flight_is_not_evicted(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(route, "MAX_SESSIONS", 1)
    busy = _session(tmp_path, "busy", idle_for=route.SESSION_TTL_SECONDS + 1, busy=1)

    fits = asyncio.run(route._evict_stale(make_room=True))

    assert not fits
    assert list(route._SESSIONS) == ["busy"]
    assert not busy["agent"].closed
    assert Path(busy["dir"]).exists()


def test_an_upload_is_refused_when_every_session_is_busy(monkeypatch, tmp_path, client) -> None:
    monkeypatch.setattr(route, "MAX_SESSIONS", 1)
    _session(tmp_path, "busy", busy=1)
    _fake_load(monkeypatch)

    response = client.post(
        "/tabular-agent/upload", files={"file": ("data.csv", b"a,b\n1,2\n", "text/csv")}
    )

    assert response.status_code == 503
    assert list(route._SESSIONS) == ["busy"]
    assert _folders(tmp_path) == []


def test_the_cap_evicts_the_least_recently_used_idle_session(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(route, "MAX_SESSIONS", 2)
    _session(tmp_path, "older", idle_for=200)
    _session(tmp_path, "newer", idle_for=100)

    assert asyncio.run(route._evict_stale(make_room=True))

    assert list(route._SESSIONS) == ["newer"]


def test_ending_a_session_waits_for_its_question(monkeypatch, tmp_path, client) -> None:
    session = _session(tmp_path, "s1")
    asking = threading.Event()
    release = threading.Event()
    seen: dict = {}

    def ask(agent, question):
        asking.set()
        assert release.wait(5)
        seen["closed_during_ask"] = agent.closed
        seen["folder_during_ask"] = Path(session["dir"]).exists()
        return route.AskResponse(question=question, answer="42", succeeded=True)

    monkeypatch.setattr(route, "_run_ask", ask)
    answers: list = []
    question = threading.Thread(
        target=lambda: answers.append(
            client.post("/tabular-agent/ask", json={"session_id": "s1", "question": "How many?"})
        )
    )
    question.start()
    assert asking.wait(5)

    ended = client.delete("/tabular-agent/session/s1")
    release.set()
    question.join(5)

    assert ended.status_code == 200
    assert answers[0].status_code == 200
    assert seen == {"closed_during_ask": False, "folder_during_ask": True}
    assert session["agent"].closed
    assert not Path(session["dir"]).exists()
    assert route._SESSIONS == {}


def test_a_very_long_file_name_is_stored_under_a_shorter_one(monkeypatch, tmp_path, client) -> None:
    stored = _fake_load(monkeypatch)
    name = "ä" * 300 + ".csv"

    response = client.post(
        "/tabular-agent/upload", files={"file": (name, b"a,b\n1,2\n", "text/csv")}
    )

    assert response.status_code == 200
    assert response.json()["filename"] == name
    assert len(response.json()["session_id"]) == 32
    [path] = stored
    assert path.suffix == ".csv"
    assert len(path.name.encode("utf-8")) <= route.STORED_NAME_MAX_BYTES
    assert path.read_bytes() == b"a,b\n1,2\n"


def test_a_name_the_server_cannot_store_is_a_400_and_leaves_no_folder(
    monkeypatch, tmp_path, client
) -> None:
    _fake_load(monkeypatch)

    def refuse(self, data):
        raise OSError(36, "File name too long")

    monkeypatch.setattr(route.Path, "write_bytes", refuse)

    response = client.post(
        "/tabular-agent/upload", files={"file": ("data.csv", b"a,b\n1,2\n", "text/csv")}
    )

    assert response.status_code == 400
    assert _folders(tmp_path) == []
    assert route._SESSIONS == {}


def test_stored_names_drop_folders_and_keep_the_suffix() -> None:
    assert route._stored_name("C:\\Users\\me\\sales 2024.xlsx") == "sales 2024.xlsx"
    assert route._stored_name("../../etc/data.csv") == "data.csv"
    assert route._stored_name("x" * 400 + ".parquet").endswith(".parquet")
