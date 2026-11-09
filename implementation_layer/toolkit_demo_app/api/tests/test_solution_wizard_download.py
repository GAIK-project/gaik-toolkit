"""The ZIP a wizard download builds does not stay in the temp folder."""

from __future__ import annotations

import asyncio
import io
import time
import zipfile
from pathlib import Path

import pytest
from api.routers import solution_wizard as route
from fastapi import FastAPI
from fastapi.testclient import TestClient


class Client:
    async def disconnect(self) -> None:
        pass


@pytest.fixture
def zip_dir(monkeypatch, tmp_path) -> Path:
    folder = tmp_path / "zips"
    monkeypatch.setattr(route, "ZIP_DIR", folder)
    monkeypatch.setattr(route, "WIZARD_SESSIONS", {})
    return folder


def _session(tmp_path: Path, session_id: str, *, idle_for: float = 0.0) -> Path:
    workspace = tmp_path / f"workspace-{session_id}"
    workspace.mkdir()
    (workspace / "blueprint.json").write_text("{}", encoding="utf-8")
    route.WIZARD_SESSIONS[session_id] = {
        "client": Client(),
        "output_dir": workspace,
        "lock": asyncio.Lock(),
        "last_active": time.time() - idle_for,
    }
    return workspace


def test_the_archive_is_removed_once_it_is_sent(zip_dir, tmp_path) -> None:
    _session(tmp_path, "s1")
    app = FastAPI()
    app.include_router(route.router, prefix="/wizard")

    response = TestClient(app).get("/wizard/download/s1")

    assert response.status_code == 200
    assert zipfile.ZipFile(io.BytesIO(response.content)).namelist() == ["blueprint.json"]
    assert list(zip_dir.iterdir()) == []


def test_ending_the_session_removes_an_archive_that_was_never_sent(zip_dir, tmp_path) -> None:
    workspace = _session(tmp_path, "s1")
    _session(tmp_path, "s2")

    async def run() -> None:
        # Calling the handler builds the archive; nothing sends it, as when a
        # download breaks off.
        await route.download_zip("s1")
        await route.download_zip("s1")
        await route.download_zip("s2")
        assert len(list(zip_dir.glob("s1-*.zip"))) == 2
        await route.end_session("s1")

    asyncio.run(run())

    assert [path.name[:3] for path in zip_dir.iterdir()] == ["s2-"]
    assert not workspace.exists()


def test_the_idle_cleanup_removes_the_archive_too(monkeypatch, zip_dir, tmp_path) -> None:
    workspace = _session(tmp_path, "idle", idle_for=route.SESSION_IDLE_SECONDS + 1)
    _session(tmp_path, "active")

    async def run() -> None:
        await route.download_zip("idle")
        await route.download_zip("active")
        sleeps = 0

        async def sleep(seconds: float) -> None:
            nonlocal sleeps
            sleeps += 1
            if sleeps == 2:
                raise asyncio.CancelledError

        monkeypatch.setattr(route.asyncio, "sleep", sleep)
        with pytest.raises(asyncio.CancelledError):
            await route.cleanup_idle_sessions()

    asyncio.run(run())

    assert list(route.WIZARD_SESSIONS) == ["active"]
    assert [path.name.split("-")[0] for path in zip_dir.iterdir()] == ["active"]
    assert not workspace.exists()
