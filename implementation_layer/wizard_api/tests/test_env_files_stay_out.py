"""An environment file with keys is never listed or put into a package zip.

The editor's routes refused ``.env`` in every spelling, while the listing and the
two zips left out the exact name ``.env`` only (the working copy not even that):
a ``.env.local``, ``.env.production``, ``.envrc`` or ``.ENV`` the agent or a tool
left in ``poc/`` was listed in the PoC tab and shipped in both downloads.
"""

import io
import os
import uuid
import zipfile

import pytest
from helpers import requires_postgres, write_gate_artifacts
from wizard_api.schemas.session import SessionUpdate
from wizard_api.services import poc_service, session_service

SECRET_NAMES = [
    ".env",
    ".env.local",
    ".env.production",
    ".envrc",
    ".ENV",
    os.path.join("config", ".env.development"),
    # The name the other way round.
    "prod.env",
    "keys.env",
    os.path.join("config", "Local.ENV"),
]


def _case_blind(folder: str) -> bool:
    """Whether the filesystem under ``folder`` takes ``.ENV`` and ``.env`` for one file
    (macOS and Windows by default)."""
    probe = os.path.join(folder, "case-probe")
    with open(probe, "w", encoding="utf-8"):
        pass
    try:
        return os.path.exists(os.path.join(folder, "CASE-PROBE"))
    finally:
        os.remove(probe)


def _package(poc: str) -> list[str]:
    """A complete package with every spelling of an environment file in it.

    Returns the spellings written: where the filesystem does not tell case apart,
    one that differs from an earlier one only in case is the same file, so it is
    left out.
    """
    os.makedirs(os.path.join(poc, "schemas"), exist_ok=True)
    os.makedirs(os.path.join(poc, "config"), exist_ok=True)
    secrets = SECRET_NAMES
    if _case_blind(poc):
        kept: dict[str, str] = {}
        for name in SECRET_NAMES:
            kept.setdefault(name.lower(), name)
        secrets = list(kept.values())
    files = {
        "run_poc.py": "from gaik.software_components.extractor import Extractor\n",
        "requirements.txt": "gaik[extract]\n",
        "README.md": "# PoC\n",
        os.path.join("schemas", "output_schema.json"): "{}\n",
        ".env.example": "AZURE_API_KEY=\n",
        **{name: "NAME=not-for-the-package\n" for name in secrets},
    }
    for name, content in files.items():
        with open(os.path.join(poc, name), "w", encoding="utf-8") as fh:
            fh.write(content)
    return secrets


@pytest.mark.parametrize("name", [*SECRET_NAMES, "sub/dir/.Env.Local"])
def test_no_spelling_of_an_environment_file_is_deployable(name) -> None:
    assert not poc_service.is_deployable_path(name)
    assert not poc_service.is_deployable_path(name.replace(os.sep, "/"))


def test_the_list_of_variables_and_ordinary_files_are_deployable() -> None:
    for name in (
        ".env.example",
        "config/.env.example",
        "environment.py",
        "env.yaml",
        "run_poc.py",
        "prod.env.md",
        "dotenv",
    ):
        assert poc_service.is_deployable_path(name), name


def test_the_package_listings_leave_them_out(tmp_path) -> None:
    poc = str(tmp_path / "poc")
    written = _package(poc)

    listed = poc_service.package_files(poc)
    deployable = poc_service.deployable_files(poc)

    for files in (listed, deployable):
        assert ".env.example" in files and "run_poc.py" in files
        assert not [f for f in files if poc_service.is_secret_name(f)]
        assert not set(files) & set(written)
    # They are still files of the session: only the package's view skips them.
    assert set(written) <= set(poc_service.regular_files(poc))


def _session(client, db_session) -> dict:
    created = client.post("/sessions", json={"user_id": "env-files", "title": "Env"}).json()
    write_gate_artifacts(created["output_dir"], "gate_3")
    _package(os.path.join(created["output_dir"], "poc"))
    session = session_service.get_session(db_session, uuid.UUID(created["id"]))
    session_service.update_session(
        db_session, session, SessionUpdate(metadata={"last_successful_run": "run-1"})
    )
    return created


def _names(response) -> list[str]:
    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        return archive.namelist()


def _secret(names: list[str]) -> list[str]:
    return [name for name in names if poc_service.is_secret_name(name)]


@requires_postgres
def test_the_poc_tabs_listing_names_none_of_them(client, db_session) -> None:
    sid = _session(client, db_session)["id"]

    listing = client.get(f"/sessions/{sid}/poc/files").json()

    assert ".env.example" in listing["files"]
    assert "poc/.env.example" in listing["package_files"]
    assert _secret(listing["files"]) == []
    assert _secret(listing["package_files"]) == []


@requires_postgres
def test_neither_zip_carries_one(client, db_session) -> None:
    sid = _session(client, db_session)["id"]

    working = _names(client.get(f"/sessions/{sid}/poc"))
    deployable = _names(client.get(f"/sessions/{sid}/poc/deployable"))

    for names in (working, deployable):
        assert "poc/.env.example" in names and "poc/run_poc.py" in names
        assert _secret(names) == []
        assert not [name for name in names if "not-for-the-package" in name]
    # Checked by content too: no entry is one of the files under another name.
    for response in (
        client.get(f"/sessions/{sid}/poc"),
        client.get(f"/sessions/{sid}/poc/deployable"),
    ):
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            for name in archive.namelist():
                assert b"not-for-the-package" not in archive.read(name), name
