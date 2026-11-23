"""A long document gets more than gaik's 30 seconds per model call."""

import io
import uuid
import zipfile
from pathlib import Path

import pytest
import yaml
from helpers import requires_postgres
from wizard_api.models import WizardSession
from wizard_api.services import poc_service

CONFIG = """# Provider settings.
provider: azure
models:
  extraction: model-a
stages:
  transcription:
    provider: azure
  extraction:
    provider: azure
    model: model-a
  judge:
    provider: azure
"""


def _package(tmp_path: Path, text: str = CONFIG) -> str:
    (tmp_path / "config.yaml").write_text(text)
    return str(tmp_path)


def test_structured_stages_get_a_limit_and_others_stay_as_they_were(tmp_path) -> None:
    config = yaml.safe_load(poc_service.config_with_model_timeout(_package(tmp_path)))
    assert config["stages"]["extraction"] == {
        "provider": "azure",
        "model": "model-a",
        "timeout": 120,
    }
    assert config["stages"]["judge"]["timeout"] == 120
    assert "timeout" not in config["stages"]["transcription"]
    assert config["models"] == {"extraction": "model-a"}


def test_a_limit_in_the_package_is_kept(tmp_path) -> None:
    text = "stages:\n  extraction:\n    timeout: 45\n"
    assert poc_service.config_with_model_timeout(_package(tmp_path, text)) is None


def test_a_stage_the_config_does_not_list_is_not_added(tmp_path) -> None:
    text = "models:\n  extraction: a\nstages:\n  transcription:\n    provider: azure\n"
    assert poc_service.config_with_model_timeout(_package(tmp_path, text)) is None


@pytest.mark.parametrize("text", ["a: [", "just text", "stages: nothing", ""])
def test_a_config_that_cannot_be_read_is_left_alone(tmp_path, text) -> None:
    assert poc_service.config_with_model_timeout(_package(tmp_path, text)) is None


def test_no_config_is_fine(tmp_path) -> None:
    assert poc_service.config_with_model_timeout(str(tmp_path)) is None


@pytest.mark.parametrize(
    ("value", "expected"), [("300", 300), ("0", 120), ("-5", 120), ("soon", 120), ("", 120)]
)
def test_the_limit_can_be_set_for_a_deployment(monkeypatch, value, expected) -> None:
    monkeypatch.setenv("WIZARD_POC_MODEL_TIMEOUT_SECONDS", value)
    assert poc_service.model_timeout_seconds() == expected


@requires_postgres
@pytest.mark.parametrize("path", ["poc", "poc/deployable"])
def test_the_package_handed_out_carries_the_limit(
    client, db_session, tmp_path, monkeypatch, path
) -> None:
    monkeypatch.setenv("WIZARD_SESSION_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setattr(poc_service, "package_problems", lambda _poc: [])
    body = client.post("/sessions", json={"user_id": "u", "title": "t"}).json()
    poc = Path(body["output_dir"]) / "poc"
    poc.mkdir(parents=True)
    (poc / "config.yaml").write_text(CONFIG)
    row = db_session.get(WizardSession, uuid.UUID(body["id"]))
    row.session_metadata = {**row.session_metadata, "last_successful_run": "run-1"}
    db_session.commit()

    res = client.get(f"/sessions/{body['id']}/{path}")
    assert res.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(res.content))
    assert archive.namelist().count("poc/config.yaml") == 1
    config = yaml.safe_load(archive.read("poc/config.yaml"))
    assert config["stages"]["extraction"]["timeout"] == 120
    assert (poc / "config.yaml").read_text() == CONFIG
