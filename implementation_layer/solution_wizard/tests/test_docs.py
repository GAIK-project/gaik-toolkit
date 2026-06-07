"""Tests for the documentation suite generator (§18, V3)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint
from solution_wizard.docs_generator import DOC_NAMES, generate_docs


def _blueprint() -> Blueprint:
    data = {
        "blueprint_version": "1.0",
        "use_case": {
            "id": "clinic_uc",
            "name": "Clinical Extraction",
            "description": "Extract fields.",
            "domain": "healthcare",
        },
        "business_spec": {
            "intended_users": ["doctor"],
            "reviewers": ["supervisor"],
            "pain_points": ["manual entry", "errors"],
            "expected_value": ["faster", "fewer errors"],
            "poc_goal": "demonstrate extraction",
            "success_criteria": ["F1 >= 0.9"],
        },
        "technical_spec": {
            "input_types": ["audio", "pdf"],
            "output_types": ["structured_json"],
            "language": "en",
            "model_provider": "azure_openai",
            "integration_targets": ["patient_management_system"],
            "human_review": True,
            "evaluation_requirements": "field-level F1",
        },
        "target_output_spec": {
            "schema_name": "Rec",
            "fields": ["full_name", "allergies"],
            "required_fields": ["full_name"],
        },
        "components": {
            "selected_modules": [
                {
                    "id": "audio_to_structured_data",
                    "name": "AudioToStructuredData",
                    "reason": "audio->structured",
                }
            ],
            "selected_building_blocks": ["LLMJudge"],
            "custom_components": [],
        },
        "artifacts": {
            "src_audio": {"type": "audio", "source": "user_upload", "optional": False},
            "out": {
                "type": "structured_json",
                "source": "generated",
                "optional": False,
                "final_output": True,
                "produced_by": "extract",
            },
        },
        "workflow": {
            "steps": [
                {
                    "id": "upload",
                    "name": "Upload",
                    "type": "user_task",
                    "inputs": [],
                    "outputs": ["src_audio"],
                },
                {
                    "id": "extract",
                    "name": "Extract",
                    "type": "automated_task",
                    "component": "AudioToStructuredData",
                    "inputs": ["src_audio"],
                    "outputs": ["out"],
                    "depends_on": ["upload"],
                    "parameters": {"enhanced_transcript": True},
                },
            ]
        },
        "governance": {
            "data_handling": {
                "contains_personal_data": "yes",
                "output_sensitivity": "high",
                "audit_log_required": True,
            }
        },
    }
    return Blueprint.model_validate(data)


def test_all_five_docs_written(tmp_path):
    written = generate_docs(_blueprint(), tmp_path)
    assert len(written) == 5
    for name in DOC_NAMES:
        p = tmp_path / "docs" / f"{name}.md"
        assert p.exists(), f"{name}.md not written"


def test_no_stray_placeholders(tmp_path):
    generate_docs(_blueprint(), tmp_path)
    for name in DOC_NAMES:
        text = (tmp_path / "docs" / f"{name}.md").read_text(encoding="utf-8")
        assert "${" not in text, f"unfilled placeholder in {name}.md"


def test_facts_present(tmp_path):
    generate_docs(_blueprint(), tmp_path)
    canvas = (tmp_path / "docs" / "genai_product_canvas.md").read_text(encoding="utf-8")
    assert "Clinical Extraction" in canvas
    assert "healthcare" in canvas
    techspec = (tmp_path / "docs" / "technical_specification.md").read_text(encoding="utf-8")
    assert "AudioToStructuredData" in techspec
    assert "extract" in techspec  # workflow step id
    assert "enhanced_transcript=True" in techspec  # option recorded in step params


def test_agent_markers_present(tmp_path):
    """Narrative markers must survive generation for the agent to fill."""
    generate_docs(_blueprint(), tmp_path)
    canvas = (tmp_path / "docs" / "genai_product_canvas.md").read_text(encoding="utf-8")
    assert "<!-- AGENT:" in canvas


def test_run_command_reflects_runtime(tmp_path):
    bp = _blueprint()
    generate_docs(bp, tmp_path)
    guide = (tmp_path / "docs" / "user_guide.md").read_text(encoding="utf-8")
    assert "python poc/run_poc.py" in guide
