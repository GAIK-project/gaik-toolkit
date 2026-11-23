"""A regeneration touches only the package files its manifest names inside poc/.

The manifest sits in the session directory, which the agent can write, so an
entry that points outside the package is ignored rather than followed, a link
inside the package is removed as a link, and a manifest of the wrong shape counts
as no manifest.
"""

import json
import os

import pytest
from wizard_api.services import artifact_sync, poc_service

requires_scaffolder = pytest.mark.skipif(
    not poc_service.solution_wizard_available(),
    reason="solution_wizard is not installed",
)


def _package(tmp_path):
    poc = tmp_path / "session" / "poc"
    poc.mkdir(parents=True)
    (poc / "run_poc.py").write_text("print('ours')\n", encoding="utf-8")
    outside = tmp_path / "other" / "use_case.blueprint.json"
    outside.parent.mkdir()
    outside.write_text("{}", encoding="utf-8")
    return poc, outside


def test_entries_outside_the_package_are_not_deleted_and_links_are_removed(tmp_path) -> None:
    poc, outside = _package(tmp_path)
    os.symlink(outside, poc / "linked.json")
    manifest = {
        "files": [
            str(outside),
            "../../other/use_case.blueprint.json",
            "linked.json",
            7,
            "run_poc.py",
        ]
    }

    poc_service._clear_previous(poc, manifest)

    assert outside.read_text(encoding="utf-8") == "{}"
    # The link itself goes, so nothing written at that path later lands outside.
    assert not os.path.lexists(poc / "linked.json")
    assert not (poc / "run_poc.py").exists()


def test_a_link_on_the_way_to_a_manifest_path_is_removed_not_followed(tmp_path) -> None:
    poc, outside = _package(tmp_path)
    os.symlink(outside.parent, poc / "schemas")

    poc_service._clear_previous(poc, {"files": ["schemas/use_case.blueprint.json"]})

    assert not os.path.lexists(poc / "schemas")
    assert outside.read_text(encoding="utf-8") == "{}"


def test_a_dot_prefixed_preserved_entry_survives(tmp_path) -> None:
    poc, _ = _package(tmp_path)
    (poc / "sample_input").mkdir()
    (poc / "sample_input" / "notes.txt").write_text("kept", encoding="utf-8")
    (poc / "evals" / "ground_truth").mkdir(parents=True)
    (poc / "evals" / "ground_truth" / "expected.json").write_text("{}", encoding="utf-8")

    poc_service._clear_previous(
        poc,
        {
            "files": [
                "./sample_input/notes.txt",
                "sample_input/./notes.txt",
                "./evals/ground_truth/expected.json",
                "./run_poc.py",
            ]
        },
    )

    assert (poc / "sample_input" / "notes.txt").read_text(encoding="utf-8") == "kept"
    assert (poc / "evals" / "ground_truth" / "expected.json").exists()
    assert not (poc / "run_poc.py").exists()


def test_entries_are_normalised_once() -> None:
    assert poc_service._normalise("./sample_input/a.pdf") == "sample_input/a.pdf"
    assert poc_service._normalise("schemas/./output_schema.py") == "schemas/output_schema.py"
    for refused in ("", "/abs/file.txt", "a/../b.txt", "..", ".", 3, None):
        assert poc_service._normalise(refused) is None


def test_only_package_files_count_as_edited(tmp_path) -> None:
    poc, outside = _package(tmp_path)
    ours = poc_service._file_hash(poc / "run_poc.py")

    assert not poc_service._agent_edited(
        poc, {"hashes": {str(outside): "0" * 64, "run_poc.py": ours}}
    )
    assert poc_service._agent_edited(poc, {"hashes": {"run_poc.py": "0" * 64}})


def test_a_manifest_of_the_wrong_shape_changes_nothing(tmp_path) -> None:
    poc, _ = _package(tmp_path)

    poc_service._clear_previous(poc, {"files": "run_poc.py"})
    assert not poc_service._agent_edited(poc, {"hashes": ["run_poc.py"]})
    assert (poc / "run_poc.py").exists()


@pytest.mark.parametrize(
    "content",
    [
        "[]",
        '"run_poc.py"',
        "7",
        "null",
        '{"files": [1, 2]}',
        '{"files": "run_poc.py"}',
        '{"files": ["run_poc.py"], "hashes": ["run_poc.py"]}',
        '{"files": ["run_poc.py"], "hashes": {"run_poc.py": 5}}',
        '{"files": ["run_poc.py"], "blueprint": {}}',
        "{not json",
    ],
)
def test_a_malformed_manifest_reads_as_none(tmp_path, content) -> None:
    (tmp_path / poc_service.MANIFEST_NAME).write_text(content, encoding="utf-8")

    assert poc_service._read_manifest(tmp_path) is None


def test_a_well_formed_manifest_is_read(tmp_path) -> None:
    manifest = {"blueprint": "abc", "files": ["run_poc.py"], "hashes": {"run_poc.py": "0"}}
    (tmp_path / poc_service.MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")

    assert poc_service._read_manifest(tmp_path) == manifest


def test_a_poc_folder_that_is_a_link_is_refused(tmp_path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    session = tmp_path / "session"
    session.mkdir()
    os.symlink(elsewhere, session / "poc")

    with pytest.raises(poc_service.PackageFolderError):
        poc_service.generate_poc(
            {"use_case": {"title": "Linked"}}, session_id="linked", output_dir=str(session)
        )

    assert list(elsewhere.iterdir()) == []


_DRAFT = {
    "use_case": {
        "id": "uc",
        "name": "Manifest PoC",
        "description": "Extract fields from a document.",
        "domain": "maintenance",
    },
    "technical_spec": {"input_types": ["pdf"]},
    "target_output_spec": {
        "schema_name": "Ticket",
        "fields": ["asset"],
        "field_types": {"asset": "str"},
    },
    "components": {
        "selected_modules": [
            {"id": "documents_to_structured_data", "name": "documents_to_structured_data"}
        ],
        "selected_building_blocks": [],
    },
}


def _generate(session, force=True):
    path = artifact_sync.artifact_path(str(session), artifact_sync.DRAFT_BLUEPRINT_FILE)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(_DRAFT, fh)
    return poc_service.generate_poc(
        {"use_case": {"title": "Manifest PoC"}},
        session_id="manifest",
        output_dir=str(session),
        force=force,
    )


@requires_scaffolder
@pytest.mark.parametrize(
    "content",
    ["[]", '{"files": [1]}', '{"files": ["run_poc.py"], "hashes": "x"}', "{not json"],
)
def test_a_malformed_manifest_regenerates_without_error(tmp_path, content) -> None:
    session = tmp_path / "session"
    session.mkdir()
    _generate(session)
    (session / poc_service.MANIFEST_NAME).write_text(content, encoding="utf-8")

    result = _generate(session)

    assert result["source"] == "scaffolder"
    assert (session / "poc" / "run_poc.py").is_file()
    assert poc_service._read_manifest(session) is not None


@requires_scaffolder
def test_a_link_at_a_scaffolded_path_is_replaced_and_its_target_untouched(tmp_path) -> None:
    session = tmp_path / "session"
    session.mkdir()
    _generate(session)
    target = tmp_path / "other" / "notes.md"
    target.parent.mkdir()
    target.write_text("unchanged", encoding="utf-8")
    readme = session / "poc" / "README.md"
    readme.unlink()
    os.symlink(target, readme)

    _generate(session)

    assert target.read_text(encoding="utf-8") == "unchanged"
    assert not readme.is_symlink()


@requires_scaffolder
def test_a_dot_prefixed_preserved_entry_survives_regeneration(tmp_path) -> None:
    session = tmp_path / "session"
    session.mkdir()
    _generate(session)
    upload = session / "poc" / "sample_input" / "case.pdf"
    upload.parent.mkdir(exist_ok=True)
    upload.write_bytes(b"%PDF-1.4 kept")
    manifest = json.loads((session / poc_service.MANIFEST_NAME).read_text(encoding="utf-8"))
    manifest["files"].append("./sample_input/case.pdf")
    (session / poc_service.MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")

    _generate(session)

    assert upload.read_bytes() == b"%PDF-1.4 kept"
