"""Text from blueprints stays text in documents, and paths stay where they belong."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard import registry as registry_module  # noqa: E402
from solution_wizard.blueprint import Blueprint  # noqa: E402
from solution_wizard.docs_generator import generate_docs, md_text  # noqa: E402
from solution_wizard.scaffolder import scaffold_poc  # noqa: E402

ROOT = Path(__file__).parent.parent
EXAMPLE = ROOT / "examples" / "document_extraction_blueprint.json"
MARKUP = "Invoices <img src=x> [link](http://example.org) **bold** | cell\n# heading"

# --------------------------------------------------------------------------- Markdown (W16)


def test_markup_in_blueprint_text_is_shown_as_text() -> None:
    shown = md_text(MARKUP)
    assert "<img" not in shown and "&lt;img src=x&gt;" in shown
    assert r"\[link\](http://example.org)" in shown
    assert r"\*\*bold\*\*" in shown and r"\|" in shown
    assert "\n" not in shown
    assert md_text("# heading").startswith("\\#")
    assert md_text("enhance_transcript") == "enhance_transcript"


def test_the_documents_carry_the_description_without_markup(tmp_path) -> None:
    bp = Blueprint.from_file(EXAMPLE)
    bp.use_case.description = MARKUP
    for path in generate_docs(bp, tmp_path):
        text = Path(path).read_text(encoding="utf-8")
        assert "<img" not in text
        assert "](http://example.org)" not in text or r"\](http://example.org)" in text


def test_the_poc_readme_carries_the_name_without_markup(tmp_path) -> None:
    bp = Blueprint.from_file(EXAMPLE)
    bp.use_case.name = MARKUP
    poc = scaffold_poc(bp, tmp_path)["poc_dir"]
    readme = (poc / "README.md").read_text(encoding="utf-8")
    assert "<img" not in readme and "&lt;img src=x&gt;" in readme


# --------------------------------------------------------------------------- registry (W13)


def test_the_shipped_registry_passes_the_check() -> None:
    registry_module.Registry()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("import_path", "os"),
        ("import_path", "gaik.x; import os"),
        ("name", "Extractor\nimport os"),
    ],
)
def test_an_import_path_or_name_outside_the_pattern_is_refused(tmp_path, field, value) -> None:
    entries = json.loads(registry_module.REGISTRY_PATH.read_text(encoding="utf-8"))
    target = next(e for e in entries if e.get("import_path"))
    target[field] = value
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    with pytest.raises(ValueError):
        registry_module.Registry(path)


# --------------------------------------------------------------------------- output folder (W11)


def _blueprint_with_output_dir(folder: Path, output_dir: str) -> Path:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["package"]["output_dir"] = output_dir
    path = folder / "use_case.blueprint.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _scaffold_cli(blueprint: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "scaffold_poc.py"), "--blueprint", str(blueprint)],
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_a_blueprint_cannot_send_the_poc_outside_its_own_folder(tmp_path) -> None:
    folder = tmp_path / "case"
    folder.mkdir()
    elsewhere = tmp_path / "elsewhere"
    result = _scaffold_cli(_blueprint_with_output_dir(folder, str(elsewhere)))
    assert result.returncode == 1
    assert "outside the blueprint's folder" in result.stderr
    assert not elsewhere.exists()


def test_a_blueprint_in_its_own_output_folder_scaffolds_as_before(tmp_path) -> None:
    folder = tmp_path / "case"
    folder.mkdir()
    result = _scaffold_cli(_blueprint_with_output_dir(folder, str(folder)))
    assert result.returncode == 0, result.stderr
    assert (folder / "poc" / "run_poc.py").exists()
    shutil.rmtree(folder / "poc")
