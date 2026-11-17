"""The scaffolded document_manifest.py helper (#251).

A UC03-shaped input: a bundle file, a manifest that names its documents by a path
relative to itself (``documents/<name>.pdf``), and the documents in that folder.
"""

import json
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).parent.parent / "templates" / "poc"
SKILL = Path(__file__).parent.parent / "SKILL.md"


@pytest.fixture
def dm():
    namespace: dict = {"__name__": "document_manifest"}
    source = (TEMPLATES / "_common" / "document_manifest.py.tmpl").read_text(encoding="utf-8")
    exec(compile(source, "document_manifest.py", "exec"), namespace)
    return type("M", (), namespace)


def _write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")
    return path


def _customer_layout(root: Path) -> Path:
    """sample_input/ with the bundle and poc_input/{manifest, documents/}."""
    _write(root / "poc_input_bundle.json", {"access_manifest": "poc_input/access_manifest.json"})
    manifest = _write(
        root / "poc_input" / "access_manifest.json",
        {
            "documents": [
                {"file": "documents/a.pdf", "allowed_roles": ["employee", "manager"]},
                {"file": "documents/b.pdf", "allowed_roles": ["manager"]},
            ]
        },
    )
    for name in ("a.pdf", "b.pdf"):
        _write(root / "poc_input" / "documents" / name, "%PDF")
    return manifest


def test_a_document_found_on_disk_matches_its_relative_manifest_entry(dm, tmp_path):
    manifest = dm.DocumentManifest.load(_customer_layout(tmp_path))

    for pdf in sorted(tmp_path.rglob("*.pdf")):
        entry = manifest.require(pdf)
        assert entry["file"] == f"documents/{pdf.name}"
    assert manifest.require(tmp_path / "poc_input" / "documents" / "b.pdf")["allowed_roles"] == [
        "manager"
    ]
    assert manifest.missing_documents() == []


def test_the_bare_name_and_the_manifest_key_match_too(dm, tmp_path):
    manifest = dm.DocumentManifest.load(_customer_layout(tmp_path))

    assert manifest.require("a.pdf")["file"] == "documents/a.pdf"
    assert manifest.require("documents/a.pdf")["file"] == "documents/a.pdf"
    assert manifest.require(Path("/elsewhere/documents/b.pdf"))["file"] == "documents/b.pdf"


def test_a_flat_layout_still_matches_by_name(dm, tmp_path):
    """The PDFs at the top level, the manifest still saying documents/<name>.pdf."""
    manifest_path = _write(
        tmp_path / "access_manifest.json", {"documents": [{"file": "documents/a.pdf"}]}
    )
    _write(tmp_path / "a.pdf", "%PDF")

    manifest = dm.DocumentManifest.load(manifest_path)

    assert manifest.require(tmp_path / "a.pdf")["file"] == "documents/a.pdf"
    # Found by its bare name under the manifest's folder, so not missing.
    assert manifest.missing_documents() == []


def test_paths_relative_to_the_bundle_resolve_with_a_search_root(dm, tmp_path):
    manifest_path = _write(
        tmp_path / "poc_input" / "access_manifest.json",
        {"documents": [{"file": "poc_input/documents/a.pdf"}]},
    )
    _write(tmp_path / "poc_input" / "documents" / "a.pdf", "%PDF")

    manifest = dm.DocumentManifest.load(manifest_path, search_roots=[tmp_path])

    assert manifest.missing_documents() == []
    assert manifest.require(tmp_path / "poc_input" / "documents" / "a.pdf")


def test_two_files_with_one_name_are_told_apart_by_path_not_guessed(dm, tmp_path):
    manifest_path = _write(
        tmp_path / "m.json",
        {"files": [{"path": "x/same.pdf", "tag": "x"}, {"path": "y/same.pdf", "tag": "y"}]},
    )
    _write(tmp_path / "x" / "same.pdf", "%PDF")
    _write(tmp_path / "y" / "same.pdf", "%PDF")

    manifest = dm.DocumentManifest.load(manifest_path)

    assert manifest.require(tmp_path / "y" / "same.pdf")["tag"] == "y"
    assert manifest.entry_for("same.pdf") is None
    with pytest.raises(KeyError, match="2 manifest entries are named 'same.pdf'"):
        manifest.require("same.pdf")


def test_a_document_without_an_entry_names_the_file_and_the_keys(dm, tmp_path):
    manifest = dm.DocumentManifest.load(_customer_layout(tmp_path))

    assert manifest.entry_for("c.pdf") is None
    with pytest.raises(dm.ManifestEntryNotFound) as caught:
        manifest.require("c.pdf")
    message = str(caught.value)
    assert "c.pdf is not in the manifest" in message
    assert "documents/a.pdf" in message and "documents/b.pdf" in message


@pytest.mark.parametrize(
    "data",
    [
        [{"file_name": "a.pdf"}],
        {"manifest": {"a.pdf": {"allowed_roles": ["employee"]}}},
        {"items": [{"filename": "a.pdf"}]},
    ],
)
def test_other_manifest_shapes_are_read(dm, tmp_path, data):
    manifest = dm.DocumentManifest.load(_write(tmp_path / "m.json", data))

    assert manifest.keys == ["a.pdf"]
    assert manifest.require(tmp_path / "a.pdf")


def test_a_manifest_with_no_document_list_is_an_error(dm, tmp_path):
    with pytest.raises(ValueError, match="no list of documents"):
        dm.DocumentManifest.load(_write(tmp_path / "m.json", {"policy": "deny"}))


def test_every_scaffolded_package_gets_the_helper(tmp_path):
    from solution_wizard.blueprint import Blueprint
    from solution_wizard.scaffolder import scaffold_poc

    blueprint = Blueprint.model_validate(
        {
            "blueprint_version": "1.0",
            "use_case": {"id": "uc", "name": "Gated Q&A", "description": "x", "domain": "test"},
            "technical_spec": {
                "input_types": ["pdf"],
                "output_types": ["structured_json"],
                "language": "en",
            },
            "target_output_spec": {"schema_name": "Answer", "fields": ["answer"]},
            "components": {
                "selected_modules": [],
                "selected_building_blocks": ["Extractor"],
                "custom_components": [],
            },
            "artifacts": {
                "src": {"type": "pdf", "source": "user_upload", "optional": False},
                "out": {
                    "type": "structured_json",
                    "source": "generated",
                    "optional": False,
                    "final_output": True,
                    "produced_by": "e",
                },
            },
            "workflow": {
                "steps": [
                    {
                        "id": "e",
                        "name": "E",
                        "type": "automated_task",
                        "component": "Extractor",
                        "inputs": ["src"],
                        "outputs": ["out"],
                    }
                ]
            },
        }
    )

    info = scaffold_poc(blueprint, tmp_path)

    helper = info["poc_dir"] / "document_manifest.py"
    assert helper.read_text(encoding="utf-8") == (
        TEMPLATES / "_common" / "document_manifest.py.tmpl"
    ).read_text(encoding="utf-8")


def test_skill_tells_the_agent_to_use_the_helper():
    text = SKILL.read_text(encoding="utf-8")

    assert "do not write your own lookup" in text
    assert "DocumentManifest.load(manifest_path)" in text
