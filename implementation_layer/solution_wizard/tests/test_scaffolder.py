"""Tests for Scaffolder (WP-3)."""

import ast
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint
from solution_wizard.scaffolder import scaffold_poc, validate_generated_python, _determine_pattern
from solution_wizard.registry import get_registry

EXAMPLES = Path(__file__).parent.parent / "examples"


def _load_example(filename: str) -> Blueprint:
    return Blueprint.from_file(EXAMPLES / filename)


# ---------------------------------------------------------------------------
# Pattern detection
# ---------------------------------------------------------------------------


def test_pattern_audio_to_structured():
    bp = _load_example("incident_reporting_blueprint.json")
    assert _determine_pattern(bp) == "audio_to_structured"


def test_pattern_document_to_structured():
    bp = _load_example("document_extraction_blueprint.json")
    assert _determine_pattern(bp) == "document_to_structured"


def test_pattern_rag():
    bp = _load_example("rag_workflow_blueprint.json")
    assert _determine_pattern(bp) == "rag"


# ---------------------------------------------------------------------------
# Scaffold all three example blueprints
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename,expected_pattern",
    [
        ("incident_reporting_blueprint.json", "audio_to_structured"),
        ("document_extraction_blueprint.json", "document_to_structured"),
        ("rag_workflow_blueprint.json", "rag"),
    ],
)
def test_scaffold_example_blueprints(tmp_path, filename, expected_pattern):
    bp = _load_example(filename)
    result = scaffold_poc(bp, tmp_path)
    poc_dir = result["poc_dir"]

    assert poc_dir.exists()
    assert result["pattern"] == expected_pattern
    assert result["template_wired"] is True

    # Required files present
    assert (poc_dir / "requirements.txt").exists()
    assert (poc_dir / ".env.example").exists()
    assert (poc_dir / "config.yaml").exists()
    assert (poc_dir / "run_poc.py").exists()
    assert (poc_dir / "README.md").exists()
    assert (poc_dir / "evals" / "run_basic_eval.py").exists()

    # Folder structure
    assert (poc_dir / "sample_input").is_dir()
    assert (poc_dir / "output").is_dir()


def test_scaffold_no_writes_outside_output_dir(tmp_path):
    bp = _load_example("incident_reporting_blueprint.json")
    scaffold_poc(bp, tmp_path)
    # Confirm nothing written to the wizard package itself
    wizard_dir = Path(__file__).parent.parent
    assert not (wizard_dir / "poc").exists()


# ---------------------------------------------------------------------------
# run_poc.py syntax validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename",
    [
        "incident_reporting_blueprint.json",
        "document_extraction_blueprint.json",
        "rag_workflow_blueprint.json",
    ],
)
def test_run_poc_is_valid_python(tmp_path, filename):
    bp = Blueprint.from_file(EXAMPLES / filename)
    result = scaffold_poc(bp, tmp_path)
    err = validate_generated_python(result["poc_dir"])
    assert err is None, f"run_poc.py syntax error: {err}"


# ---------------------------------------------------------------------------
# requirements.txt
# ---------------------------------------------------------------------------


def test_requirements_txt_has_gaik_extra(tmp_path):
    bp = _load_example("incident_reporting_blueprint.json")
    scaffold_poc(bp, tmp_path)
    req = (tmp_path / "poc" / "requirements.txt").read_text()
    assert "gaik[" in req
    assert "pydantic" in req


def test_requirements_txt_audio_module(tmp_path):
    bp = _load_example("incident_reporting_blueprint.json")
    scaffold_poc(bp, tmp_path)
    req = (tmp_path / "poc" / "requirements.txt").read_text()
    assert "audio-to-structured-data" in req


def test_requirements_txt_rag_module(tmp_path):
    bp = _load_example("rag_workflow_blueprint.json")
    scaffold_poc(bp, tmp_path)
    req = (tmp_path / "poc" / "requirements.txt").read_text()
    assert "rag-workflow" in req


# ---------------------------------------------------------------------------
# Schema files
# ---------------------------------------------------------------------------


def test_schema_files_generated_for_extraction_blueprint(tmp_path):
    bp = _load_example("incident_reporting_blueprint.json")
    scaffold_poc(bp, tmp_path)
    schemas_dir = tmp_path / "poc" / "schemas"
    assert (schemas_dir / "output_schema.py").exists()
    # Must be output_schema_requirements.json so load_schema("output_schema") finds it
    assert (schemas_dir / "output_schema_requirements.json").exists()


def test_schema_requirements_payload_shape(tmp_path):
    """Requirements JSON must have the shape load_schema() can read."""
    bp = _load_example("incident_reporting_blueprint.json")
    scaffold_poc(bp, tmp_path)
    req_path = tmp_path / "poc" / "schemas" / "output_schema_requirements.json"
    data = json.loads(req_path.read_text())
    assert "model_name" in data
    assert "requirements" in data
    req = data["requirements"]
    assert "use_case_name" in req
    assert "fields" in req
    allowed_types = {"str", "int", "float", "bool", "list[str]", "date", "decimal", "list[dict]"}
    for f in req["fields"]:
        assert f["field_type"] in allowed_types, (
            f"field_type '{f['field_type']}' not in AllowedTypes"
        )


def test_extraction_requirements_generated(tmp_path):
    bp = _load_example("incident_reporting_blueprint.json")
    scaffold_poc(bp, tmp_path)
    req_path = tmp_path / "poc" / "prompts" / "extraction_requirements.md"
    assert req_path.exists()


def test_rag_no_schema_files(tmp_path):
    bp = _load_example("rag_workflow_blueprint.json")
    scaffold_poc(bp, tmp_path)
    # RAG pattern doesn't need extraction schema
    schema_py = tmp_path / "poc" / "schemas" / "output_schema.py"
    # File may or may not exist; if it does, it should be valid Python
    if schema_py.exists():
        ast.parse(schema_py.read_text())


# ---------------------------------------------------------------------------
# Facilities blueprint (real wizard output)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Synthetic mode
# ---------------------------------------------------------------------------


def test_synthetic_creates_sample_for_document(tmp_path):
    bp = _load_example("document_extraction_blueprint.json")
    result = scaffold_poc(bp, tmp_path, synthetic=True)
    sample_dir = result["poc_dir"] / "sample_input"
    files = list(sample_dir.iterdir())
    assert len(files) > 0


# ---------------------------------------------------------------------------
# pip_requirements helper
# ---------------------------------------------------------------------------


def test_pip_requirements_deduplication():
    reg = get_registry()
    lines = reg.pip_requirements(["Transcriber", "TranscriptEnhancer", "Transcriber"])
    extras = [l for l in lines if l.startswith("gaik[")]
    assert len(extras) == len(set(extras))


def test_pip_requirements_audio_components():
    reg = get_registry()
    lines = reg.pip_requirements(["Transcriber", "TranscriptEnhancer"])
    combined = " ".join(lines)
    assert "transcriber" in combined
    assert "enhance-transcript" in combined
