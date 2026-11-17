"""The scaffolded input_bundle.py helper, and the manifest's documents() (#251, #255).

Layouts as the cases deliver them: a UC05-shaped bundle (``poc_input_bundle.json`` naming
``input/<name>.wav`` etc.) and a UC03-shaped one (bundle beside ``poc_input/`` with the
manifest and ``documents/``).
"""

import ast
import json
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).parent.parent / "templates" / "poc"
SKILL = Path(__file__).parent.parent / "SKILL.md"


def _module(name):
    namespace: dict = {"__name__": name}
    source = (TEMPLATES / "_common" / f"{name}.py.tmpl").read_text(encoding="utf-8")
    exec(compile(source, f"{name}.py", "exec"), namespace)
    return type("M", (), namespace)


@pytest.fixture
def ib():
    return _module("input_bundle")


@pytest.fixture
def dm():
    return _module("document_manifest")


def _write(path: Path, data="x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


def _meeting_bundle(root: Path) -> Path:
    _write(
        root / "poc_input_bundle.json",
        {
            "inputs": {
                "meeting_audio": "input/meeting.wav",
                "agenda_pdf": "input/agenda.pdf",
                "participant_list": "input/participants.json",
            },
            "output": {"directory": "output", "filename": "record.json"},
        },
    )
    for name in ("meeting.wav", "agenda.pdf", "participants.json"):
        _write(root / "input" / name)
    return root


def test_inputs_named_by_the_bundle_are_found_in_their_subfolder(ib, tmp_path):
    root = _meeting_bundle(tmp_path)

    assert ib.find_input(root, ".wav", ".mp3").name == "meeting.wav"
    assert ib.find_input(root, ".pdf").name == "agenda.pdf"
    # The bundle is a .json too; it is never returned as an input.
    assert ib.find_input(root, ".json").name == "participants.json"


def test_without_a_bundle_subfolders_are_searched(ib, tmp_path):
    _write(tmp_path / "input" / "meeting.wav")

    assert ib.load_bundle(tmp_path) is None
    assert ib.find_input(tmp_path, ".wav").name == "meeting.wav"


def test_the_flat_layout_still_works(ib, tmp_path):
    _write(tmp_path / "meeting.wav")

    assert ib.find_input(tmp_path, ".wav") == tmp_path / "meeting.wav"


def test_hints_pick_between_several_and_a_tie_is_an_error_that_lists_them(ib, tmp_path):
    _write(tmp_path / "agenda.pdf")
    _write(tmp_path / "minutes.pdf")

    assert ib.find_input(tmp_path, ".pdf", hints=("agenda",)).name == "agenda.pdf"
    with pytest.raises(ib.InputNotFound, match="2 inputs") as raised:
        ib.find_input(tmp_path, ".pdf")
    assert "agenda.pdf" in str(raised.value) and "minutes.pdf" in str(raised.value)
    assert ib.find_input(tmp_path, ".pdf", pick_first=True).name == "agenda.pdf"


def test_the_users_own_file_comes_before_the_packages_example(ib, tmp_path):
    # The wizard's example sorts first; the run read it and never the upload.
    _write(tmp_path / "delivery_note_sample.txt")
    _write(tmp_path / "lahete.txt")
    hints = ("delivery", "note", "lahete")
    assert ib.find_input(tmp_path, ".txt", hints=hints, pick_first=True).name == (
        "delivery_note_sample.txt"
    )

    _write(tmp_path / ib.UPLOADED_NAMES_FILE, "lahete.txt\n")

    assert ib.find_input(tmp_path, ".txt", hints=hints, pick_first=True).name == "lahete.txt"
    # No hint matches the upload's name: it is still the one.
    assert ib.find_input(tmp_path, ".txt", hints=("delivery",)).name == "lahete.txt"
    # Another type is not the upload's business: the example .pdf is still found.
    _write(tmp_path / "agenda.pdf")
    assert ib.find_input(tmp_path, ".pdf").name == "agenda.pdf"


def test_the_users_own_file_comes_before_the_file_the_bundle_names(ib, tmp_path):
    _write(tmp_path / "input" / "meeting.wav")
    _write(tmp_path / "poc_input_bundle.json", {"audio": "input/meeting.wav"})
    assert ib.find_input(tmp_path, ".wav").name == "meeting.wav"

    _write(tmp_path / "own_recording.wav")
    _write(tmp_path / ib.UPLOADED_NAMES_FILE, "own_recording.wav\n")

    assert ib.find_input(tmp_path, ".wav") == tmp_path / "own_recording.wav"


def test_a_listed_name_that_is_not_there_changes_nothing(ib, tmp_path):
    _write(tmp_path / "sample.txt")
    _write(tmp_path / "sub" / "gone.txt")
    # Removed since, and a same-named file in a subfolder is not the upload.
    _write(tmp_path / ib.UPLOADED_NAMES_FILE, "gone.txt\n\n")

    assert ib.find_input(tmp_path, ".txt", pick_first=True).name == "sample.txt"
    assert ib.uploaded_names(tmp_path) == {"gone.txt"}
    assert ib.uploaded_names(tmp_path / "missing") == set()


def test_the_list_of_uploads_is_not_named_among_the_files(ib, tmp_path):
    _write(tmp_path / "notes.txt")
    _write(tmp_path / ib.UPLOADED_NAMES_FILE, "notes.txt\n")

    with pytest.raises(ib.InputNotFound, match=r"files there: \['notes.txt'\]"):
        ib.find_input(tmp_path, ".wav")


def test_nothing_found_lists_what_is_there(ib, tmp_path):
    _write(tmp_path / "notes.txt")

    with pytest.raises(ib.InputNotFound, match=r"files there: \['notes.txt'\]"):
        ib.find_input(tmp_path, ".wav")


def test_a_folder_the_bundle_names_is_available(ib, tmp_path):
    _write(
        tmp_path / "poc_input_bundle.json",
        {"documents_directory": "poc_input/documents", "access_manifest": "poc_input/m.json"},
    )
    _write(tmp_path / "poc_input" / "documents" / "a.pdf")
    _write(tmp_path / "poc_input" / "m.json", {"documents": []})

    bundle = ib.load_bundle(tmp_path)

    assert bundle.dir("documents") == (tmp_path / "poc_input" / "documents").resolve()
    assert bundle.file(".json", hints=("manifest",)).name == "m.json"


def test_manifest_documents_resolve_against_the_manifest_not_the_bundle(dm, tmp_path):
    """UC03 run 9: the manifest was read with the helper, but its paths were joined to
    the bundle's folder by hand and no file was found."""
    _write(
        tmp_path / "poc_input_bundle.json", {"access_manifest": "poc_input/access_manifest.json"}
    )
    manifest_path = _write(
        tmp_path / "poc_input" / "access_manifest.json",
        {"documents": [{"file": "documents/a.pdf"}, {"file": "documents/b.pdf"}]},
    )
    _write(tmp_path / "poc_input" / "documents" / "a.pdf")
    _write(tmp_path / "poc_input" / "documents" / "b.pdf")

    manifest = dm.DocumentManifest.load(manifest_path, search_roots=[tmp_path])

    docs = manifest.documents()
    assert [p.name for p in docs] == ["a.pdf", "b.pdf"]
    assert all(p.is_file() for p in docs)
    assert manifest.path_for("documents/b.pdf") == docs[1]
    assert manifest.require(docs[0])["file"] == "documents/a.pdf"


def test_manifest_documents_found_when_laid_out_flat(dm, tmp_path):
    manifest_path = _write(tmp_path / "m.json", {"documents": [{"file": "documents/a.pdf"}]})
    _write(tmp_path / "a.pdf")

    manifest = dm.DocumentManifest.load(manifest_path)

    assert manifest.documents() == [(tmp_path / "a.pdf").resolve()]


def test_a_missing_manifest_document_is_an_error_unless_not_strict(dm, tmp_path):
    manifest_path = _write(
        tmp_path / "m.json",
        {"documents": [{"file": "documents/a.pdf"}, {"file": "documents/gone.pdf"}]},
    )
    _write(tmp_path / "documents" / "a.pdf")

    manifest = dm.DocumentManifest.load(manifest_path)

    with pytest.raises(FileNotFoundError, match="gone.pdf"):
        manifest.documents()
    assert [p.name for p in manifest.documents(strict=False)] == ["a.pdf"]
    assert manifest.missing_documents() == ["documents/gone.pdf"]


@pytest.mark.parametrize(
    "template", sorted(TEMPLATES.glob("*/run_poc.py.tmpl")), ids=lambda path: path.parent.name
)
def test_no_template_lists_only_the_top_level_of_sample_input(template):
    source = template.read_text(encoding="utf-8")

    assert "sample_dir.iterdir()" not in source


def test_every_scaffolded_package_gets_the_input_helper(tmp_path):
    from solution_wizard.blueprint import Blueprint
    from solution_wizard.scaffolder import scaffold_poc

    blueprint = Blueprint.model_validate(
        {
            "blueprint_version": "1.0",
            "use_case": {"id": "uc", "name": "Meeting record", "description": "x", "domain": "t"},
            "technical_spec": {
                "input_types": ["audio", "pdf"],
                "output_types": ["structured_json"],
                "language": "en",
            },
            "target_output_spec": {"schema_name": "Record", "fields": ["a"]},
            "components": {
                "selected_modules": [],
                "selected_building_blocks": ["Transcriber", "DataExtractor"],
                "custom_components": [],
            },
            "artifacts": {
                "meeting_audio": {"type": "audio", "source": "user_upload", "optional": False},
                "agenda_pdf": {"type": "pdf", "source": "user_upload", "optional": False},
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
                        "component": "DataExtractor",
                        "inputs": ["meeting_audio", "agenda_pdf"],
                        "outputs": ["out"],
                    }
                ]
            },
        }
    )

    info = scaffold_poc(blueprint, tmp_path)
    poc = info["poc_dir"]

    assert (poc / "input_bundle.py").read_text(encoding="utf-8") == (
        TEMPLATES / "_common" / "input_bundle.py.tmpl"
    ).read_text(encoding="utf-8")
    run_poc = (poc / "run_poc.py").read_text(encoding="utf-8")
    ast.parse(run_poc)
    assert "sample_dir.iterdir()" not in run_poc


def test_skill_tells_the_agent_to_use_both_helpers_for_inputs():
    text = SKILL.read_text(encoding="utf-8")

    assert "Take the list of documents from `manifest.documents()`" in text
    assert "Find inputs with `input_bundle.py`; do not list `sample_input/` yourself" in text


def test_bundle_paths_outside_the_sample_folder_are_ignored(ib, tmp_path):
    sample = tmp_path / "sample_input"
    _write(tmp_path / "elsewhere" / "notes.pdf")
    _write(sample / "poc_input_bundle.json", {"inputs": {"agenda_pdf": "../elsewhere/notes.pdf"}})

    bundle = ib.load_bundle(sample)
    assert bundle.files == {}
    with pytest.raises(ib.InputNotFound):
        ib.find_input(sample, ".pdf")


def test_links_out_of_the_sample_folder_are_not_inputs(ib, tmp_path):
    sample = tmp_path / "sample_input"
    target = _write(tmp_path / "elsewhere" / "meeting.wav")
    sample.mkdir()
    try:
        (sample / "meeting.wav").symlink_to(target)
    except OSError:  # Windows without the symlink privilege
        pytest.skip("this account cannot create symbolic links")
    _write(sample / "poc_input_bundle.json", {"inputs": {"meeting_audio": "meeting.wav"}})

    with pytest.raises(ib.InputNotFound):
        ib.find_input(sample, ".wav")


def test_manifest_paths_stay_inside_the_manifest_folder_or_a_search_root(dm, tmp_path):
    sample = tmp_path / "sample_input"
    _write(tmp_path / "elsewhere" / "c.pdf")
    _write(sample / "documents" / "a.pdf")
    manifest_path = _write(
        sample / "manifest" / "m.json",
        {"documents": [{"file": "../documents/a.pdf"}, {"file": "../../elsewhere/c.pdf"}]},
    )

    manifest = dm.DocumentManifest.load(manifest_path, search_roots=[sample])

    assert [p.name for p in manifest.documents(strict=False)] == ["a.pdf"]


def test_manifest_in_a_subfolder_of_sample_input_finds_sibling_documents(dm, tmp_path):
    """SKILL.md loads the manifest without search roots."""
    sample = tmp_path / "poc" / "sample_input"
    _write(sample / "documents" / "a.pdf")
    _write(tmp_path / "poc" / "notes.pdf")
    manifest_path = _write(
        sample / "meta" / "m.json",
        {"documents": [{"file": "../documents/a.pdf"}, {"file": "../../notes.pdf"}]},
    )

    manifest = dm.DocumentManifest.load(manifest_path)

    assert [p.name for p in manifest.documents(strict=False)] == ["a.pdf"]


def _link(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target)
    except OSError:  # Windows without the symlink privilege
        pytest.skip("this account cannot create symbolic links")


def test_a_bundle_file_linked_from_elsewhere_is_not_read(ib, tmp_path):
    sample = tmp_path / "sample_input"
    _write(sample / "input" / "meeting.wav")
    outside = _write(tmp_path / "elsewhere" / "bundle.json", {"inputs": {"a": "input/meeting.wav"}})
    _link(sample / "poc_input_bundle.json", outside)

    assert ib.load_bundle(sample) is None


def test_an_uploads_list_linked_from_elsewhere_is_not_read(ib, tmp_path):
    sample = tmp_path / "sample_input"
    sample.mkdir()
    outside = _write(tmp_path / "elsewhere" / "names.txt", "lahete.txt\n")
    _link(sample / ib.UPLOADED_NAMES_FILE, outside)

    assert ib.uploaded_names(sample) == set()


def test_a_bundle_path_written_with_backslashes_is_found(ib, tmp_path):
    _write(tmp_path / "input" / "meeting.wav")
    _write(tmp_path / "poc_input_bundle.json", {"inputs": {"audio": "input\\meeting.wav"}})

    assert ib.find_input(tmp_path, ".wav").name == "meeting.wav"


def test_the_rag_poc_reads_no_pdf_linked_from_outside(tmp_path):
    source = (TEMPLATES / "rag" / "run_poc.py.tmpl").read_text(encoding="utf-8")
    start = source.index("def find_documents")
    end = source.index("\ndef ", start + 1)
    namespace = {"Path": Path, "__file__": str(tmp_path / "run_poc.py")}
    exec(source[start:end], namespace)
    sample = tmp_path / "sample_input"
    _write(sample / "docs" / "inside.pdf")
    _link(sample / "docs" / "outside.pdf", _write(tmp_path / "elsewhere" / "outside.pdf"))

    found = namespace["find_documents"]({"paths": {"sample_input": str(sample)}})

    assert [p.name for p in found] == ["inside.pdf"]


def test_a_file_type_in_the_artifact_id_is_no_hint(tmp_path):
    """agenda_pdf's hint is "agenda": "pdf" is in every PDF's name and would pick none."""
    from solution_wizard.blueprint import Artifact, ArtifactSource, Blueprint
    from solution_wizard.scaffolder import _build_input_loaders

    blueprint = Blueprint.model_validate(
        {"use_case": {"id": "uc", "name": "N", "description": "d", "domain": "t"}}
    )
    blueprint.artifacts = {
        "agenda_pdf": Artifact(type="pdf", source=ArtifactSource.USER_UPLOAD, optional=False),
        "meeting_audio": Artifact(type="audio", source=ArtifactSource.USER_UPLOAD, optional=False),
    }

    loaders = _build_input_loaders(blueprint)

    assert "hints=('agenda',)" in loaders
    assert "hints=('meeting', 'audio')" in loaders


@pytest.mark.parametrize("content", ["not json", '{"participants": ["Ann", "Bo"]}'])
def test_a_file_named_like_a_bundle_that_is_not_one_is_an_input(ib, tmp_path, content):
    """bundle.json may be the case's own JSON input: not JSON, or naming no file there."""
    _write(tmp_path / "bundle.json", content)
    _write(tmp_path / "agenda.pdf")

    assert ib.load_bundle(tmp_path) is None
    assert ib.find_input(tmp_path, ".pdf").name == "agenda.pdf"
    if content.startswith("{"):
        assert ib.find_input(tmp_path, ".json").name == "bundle.json"


def test_a_manifest_name_with_glob_characters_is_found_by_name(dm, tmp_path):
    manifest_path = _write(
        tmp_path / "manifest.json", {"documents": [{"file": "documents/report[2024].pdf"}]}
    )
    _write(tmp_path / "docs" / "report[2024].pdf")
    _write(tmp_path / "docs" / "report2.pdf")

    manifest = dm.DocumentManifest.load(manifest_path)

    assert [p.name for p in manifest.documents()] == ["report[2024].pdf"]
