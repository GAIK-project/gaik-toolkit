"""The full blueprint draft is written whole, after validation, never through a link."""

import json
import os

import pytest
from pydantic import ValidationError
from wizard_api.services import draft_store
from wizard_api.services.artifact_sync import (
    DRAFT_BLUEPRINT_FILE,
    WORKFLOW_BPMN_FILE,
    WORKFLOW_MMD_FILE,
)


def _blueprint(name: str = "Invoice intake") -> dict:
    return {
        "use_case": {
            "id": "invoice_intake",
            "name": name,
            "description": "Read invoices into a sheet.",
            "domain": "finance",
        },
        "workflow": {
            "steps": [
                {"id": "extract", "name": "Extract fields", "type": "automated_task"},
                {"id": "review", "name": "Review fields", "type": "human_review"},
            ]
        },
    }


def test_an_invalid_blueprint_leaves_the_old_file_untouched(tmp_path) -> None:
    draft = tmp_path / DRAFT_BLUEPRINT_FILE
    draft.write_text('{"old": true}\n', encoding="utf-8")

    with pytest.raises(ValidationError):
        draft_store.write_draft(str(tmp_path), {"workflow": "not a workflow"})

    assert draft.read_text(encoding="utf-8") == '{"old": true}\n'
    assert sorted(os.listdir(tmp_path)) == [DRAFT_BLUEPRINT_FILE]


def test_a_symlinked_draft_is_refused(tmp_path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text("keep me", encoding="utf-8")
    session = tmp_path / "session"
    session.mkdir()
    os.symlink(outside, session / DRAFT_BLUEPRINT_FILE)

    with pytest.raises(ValueError, match="symlink"):
        draft_store.write_draft(str(session), _blueprint())

    assert outside.read_text(encoding="utf-8") == "keep me"
    assert os.path.islink(session / DRAFT_BLUEPRINT_FILE)
    assert os.listdir(session) == [DRAFT_BLUEPRINT_FILE]


def test_the_write_replaces_the_file_whole(tmp_path) -> None:
    (tmp_path / DRAFT_BLUEPRINT_FILE).write_text('{"old": true}', encoding="utf-8")
    blueprint = _blueprint("Kuittien käsittely")

    draft_store.write_draft(str(tmp_path), blueprint)

    assert os.listdir(tmp_path) == [DRAFT_BLUEPRINT_FILE]  # no temp file is left
    text = (tmp_path / DRAFT_BLUEPRINT_FILE).read_text(encoding="utf-8")
    assert json.loads(text) == blueprint
    assert "Kuittien käsittely" in text  # written as UTF-8, not escaped


def test_derived_files_follow_the_blueprint(tmp_path) -> None:
    draft_store.refresh_derived_files(str(tmp_path), _blueprint())
    assert "Extract fields" in (tmp_path / WORKFLOW_MMD_FILE).read_text(encoding="utf-8")
    renamed = _blueprint()
    renamed["workflow"]["steps"][0]["name"] = "Read invoice lines"

    draft_store.refresh_derived_files(str(tmp_path), renamed)

    mmd = (tmp_path / WORKFLOW_MMD_FILE).read_text(encoding="utf-8")
    assert "Read invoice lines" in mmd
    assert "Extract fields" not in mmd
    bpmn = (tmp_path / WORKFLOW_BPMN_FILE).read_text(encoding="utf-8")
    assert "Read invoice lines" in bpmn
    assert "Extract fields" not in bpmn
    assert sorted(os.listdir(tmp_path)) == [WORKFLOW_BPMN_FILE, WORKFLOW_MMD_FILE]


def test_a_derived_file_failure_is_logged_not_raised(tmp_path, caplog) -> None:
    draft_store.refresh_derived_files(str(tmp_path), {"workflow": "not a workflow"})

    assert not (tmp_path / WORKFLOW_MMD_FILE).exists()
    assert any(r.name == draft_store.__name__ for r in caplog.records)


def test_a_symlinked_derived_file_is_not_followed(tmp_path) -> None:
    outside = tmp_path / "outside.mmd"
    outside.write_text("keep me", encoding="utf-8")
    session = tmp_path / "session"
    session.mkdir()
    os.symlink(outside, session / WORKFLOW_MMD_FILE)

    draft_store.refresh_derived_files(str(session), _blueprint())

    assert outside.read_text(encoding="utf-8") == "keep me"
    assert os.path.islink(session / WORKFLOW_MMD_FILE)
    assert (session / WORKFLOW_BPMN_FILE).is_file()  # the other file is still refreshed


def test_restore_puts_back_what_the_snapshot_took(tmp_path) -> None:
    draft = tmp_path / DRAFT_BLUEPRINT_FILE
    draft.write_bytes(b'{"agent": "wrote this"}')
    taken = draft_store.snapshot(str(tmp_path))

    draft_store.write_draft(str(tmp_path), _blueprint())
    draft_store.refresh_derived_files(str(tmp_path), _blueprint())
    draft_store.restore(str(tmp_path), taken)

    assert draft.read_bytes() == b'{"agent": "wrote this"}'
    # Not there before the edit, so not there after it was undone.
    assert not (tmp_path / WORKFLOW_BPMN_FILE).exists()
    assert not (tmp_path / WORKFLOW_MMD_FILE).exists()
