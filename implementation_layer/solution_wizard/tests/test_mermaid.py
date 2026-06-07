"""Tests for Mermaid generator (WP5)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint
from solution_wizard.visualizer import generate_mermaid, write_mermaid

EXAMPLES = Path(__file__).parent.parent / "examples"


def test_mermaid_starts_with_flowchart():
    bp = Blueprint.from_file(EXAMPLES / "incident_reporting_blueprint.json")
    mmd = generate_mermaid(bp)
    assert mmd.startswith("flowchart TD")


def test_mermaid_contains_all_step_names():
    bp = Blueprint.from_file(EXAMPLES / "incident_reporting_blueprint.json")
    mmd = generate_mermaid(bp)
    for step in bp.workflow.steps:
        assert step.name in mmd, f"Step '{step.name}' missing from diagram"


def test_mermaid_contains_style_lines():
    bp = Blueprint.from_file(EXAMPLES / "incident_reporting_blueprint.json")
    mmd = generate_mermaid(bp)
    assert "style " in mmd
    assert "fill:" in mmd


def test_mermaid_output_node_uses_green():
    bp = Blueprint.from_file(EXAMPLES / "incident_reporting_blueprint.json")
    mmd = generate_mermaid(bp)
    # Green is the output colour
    assert "#dcfce7" in mmd


def test_mermaid_write_creates_file(tmp_path):
    bp = Blueprint.from_file(EXAMPLES / "incident_reporting_blueprint.json")
    mmd_path = write_mermaid(bp, tmp_path)
    assert mmd_path.exists()
    content = mmd_path.read_text()
    assert "flowchart TD" in content


def test_mermaid_document_extraction():
    bp = Blueprint.from_file(EXAMPLES / "document_extraction_blueprint.json")
    mmd = generate_mermaid(bp)
    assert "flowchart TD" in mmd
    assert len(bp.workflow.steps) >= 2


def test_mermaid_rag_workflow():
    bp = Blueprint.from_file(EXAMPLES / "rag_workflow_blueprint.json")
    mmd = generate_mermaid(bp)
    assert "flowchart TD" in mmd


def test_mermaid_label_escaping():
    """Step names with quotes and brackets must not break Mermaid syntax."""
    from solution_wizard.visualizer import _node_label

    assert _node_label('Record "voice" note') == "Record #quot;voice#quot; note"
    assert _node_label("Review [optional]") == "Review #lsqb;optional#rsqb;"
    assert _node_label("Normal step name") == "Normal step name"
