"""Text from blueprints and canvases stays text, and paths stay where they belong."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard import registry as registry_module  # noqa: E402
from solution_wizard.blueprint import Blueprint  # noqa: E402
from solution_wizard.bpmn_sync import (  # noqa: E402
    MAX_BPMN_XML_DEPTH,
    MAX_NAME_CHARS,
    sync_v2_blueprint_from_bpmn_xml,
)
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


# --------------------------------------------------------------------------- review additions


def _scaffold_cli_in(cwd: Path, blueprint: str, home: Path | None = None):
    import os

    env = dict(os.environ)
    if home is not None:
        env["HOME"] = env["USERPROFILE"] = str(home)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "scaffold_poc.py"), "--blueprint", blueprint],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=cwd,
        env=env,
    )


def test_the_relative_folder_run_wizard_saves_scaffolds_into_the_blueprint_folder(
    tmp_path,
) -> None:
    # run_wizard.py --blueprint case/use_case.blueprint.json saves output_dir "case".
    folder = tmp_path / "case"
    folder.mkdir()
    _blueprint_with_output_dir(folder, "case")
    result = _scaffold_cli_in(tmp_path, "case/use_case.blueprint.json")
    assert result.returncode == 0, result.stderr
    assert (folder / "poc" / "run_poc.py").exists()
    assert not (folder / "case").exists()


def test_a_home_relative_output_folder_is_expanded(tmp_path) -> None:
    folder = tmp_path / "case"
    folder.mkdir()
    blueprint = _blueprint_with_output_dir(folder, "~/case")
    result = _scaffold_cli_in(tmp_path, str(blueprint), home=tmp_path)
    assert result.returncode == 0, result.stderr
    assert (folder / "poc" / "run_poc.py").exists()
    assert not (folder / "~").exists()


def test_an_import_path_that_ends_in_a_line_break_is_refused(tmp_path) -> None:
    entries = json.loads(registry_module.REGISTRY_PATH.read_text(encoding="utf-8"))
    target = next(e for e in entries if e.get("import_path"))
    target["import_path"] += "\n"
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    with pytest.raises(ValueError, match="not a gaik module"):
        registry_module.Registry(path)


@pytest.mark.parametrize(
    ("language", "note"),
    [("fi", "an audio recording in FI (.wav"), ("auto", "an audio recording (.wav")],
)
def test_the_audio_input_note_names_a_language_code_only(tmp_path, language, note) -> None:
    bp = Blueprint.from_file(ROOT / "examples" / "incident_reporting_blueprint.json")
    bp.technical_spec["language"] = language
    poc = scaffold_poc(bp, tmp_path)["poc_dir"]
    assert note in (poc / "README.md").read_text(encoding="utf-8")


V2 = {
    "name": "Demo",
    "description": "",
    "goal": "",
    "steps": [{"id": "a", "name": "First", "type": "io"}],
}


def _canvas(new_id: str, new_name: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
  id="D1" targetNamespace="x">
  <bpmn:process id="Process_1" isExecutable="false">
    <bpmn:startEvent id="StartEvent_1" />
    <bpmn:userTask id="Activity_a" name="First" />
    <bpmn:userTask id="{new_id}" name="{new_name}" />
    <bpmn:exclusiveGateway id="Gateway_ok&quot; x" name="Check&#10;again" />
    <bpmn:endEvent id="EndEvent_1" />
    <bpmn:sequenceFlow id="F1" sourceRef="StartEvent_1" targetRef="Activity_a" />
    <bpmn:sequenceFlow id="F2" sourceRef="Activity_a" targetRef="{new_id}" />
    <bpmn:sequenceFlow id="F3" sourceRef="{new_id}" targetRef="EndEvent_1" />
  </bpmn:process>
</bpmn:definitions>
"""


def test_a_task_added_on_the_canvas_gets_a_clean_id_and_a_one_line_name() -> None:
    long_name = "Line one&#10;line two " + "x" * 400
    synced = sync_v2_blueprint_from_bpmn_xml(V2, _canvas("Activity_new&quot; step", long_name))
    added = synced["steps"][1]
    assert added["id"] == "new_step"
    assert "\n" not in added["name"] and len(added["name"]) <= MAX_NAME_CHARS
    assert added["name"].startswith("Line one")
    gateway = synced["gateways"][0]
    assert gateway["id"] == "Gateway_ok_x" and gateway["name"] == "Check again"


def test_xml_nested_deeper_than_a_diagram_is_refused() -> None:
    deep = "<a>" * (MAX_BPMN_XML_DEPTH + 1) + "</a>" * (MAX_BPMN_XML_DEPTH + 1)
    with pytest.raises(ValueError, match="nests deeper"):
        sync_v2_blueprint_from_bpmn_xml(V2, deep)


def test_the_parser_itself_refuses_a_document_type_and_entities() -> None:
    from solution_wizard.bpmn_sync import _parse

    nested = '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;">]><r>&b;</r>'
    with pytest.raises(ValueError, match="DTD or entities"):
        _parse(nested)
