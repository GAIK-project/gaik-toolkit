"""Tests for Mermaid generator (WP5)."""

import re
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


def test_mermaid_label_escapes_markup_and_line_breaks():
    from solution_wizard.visualizer import _node_label

    assert _node_label("<b>Bold</b> & co") == "#lt;b#gt;Bold#lt;/b#gt; #amp; co"
    assert _node_label("Use `code`") == "Use #96;code#96;"
    assert _node_label("First\nsecond") == "First second"


def test_mermaid_node_ids_cannot_change_the_diagram_syntax():
    from solution_wizard.visualizer import _node_id

    # Plain ids keep their form.
    assert _node_id("extract_fields") == "extract_fields"
    assert _node_id("Step2") == "Step2"
    # Other characters are replaced, and distinct ids stay distinct.
    odd = _node_id('a"]-->b')
    assert re.fullmatch(r"[A-Za-z0-9_]+", odd)
    assert _node_id("a;b") != _node_id("a:b")
    assert _node_id("extract-fields").startswith("extract_fields_")
    # Keywords and empty ids get a hash, and never collide with a plain id.
    ids = {_node_id(x) for x in ("end", "step_end", "step end", "step-end", "", "step")}
    assert len(ids) == 6
    assert all(re.fullmatch(r"[A-Za-z0-9_]+", x) for x in ids)
    assert _node_id("end").startswith("end_")


def test_mermaid_step_with_quotes_and_line_breaks_stays_one_node():
    bp = Blueprint.model_validate(
        {
            "use_case": {"id": "uc", "name": "UC", "description": "d", "domain": "x"},
            "workflow": {
                "steps": [
                    {"id": "end", "name": "Start", "type": "user_task"},
                    {
                        "id": 'b"]\nclick b',
                        "name": 'Check "draft"] --> next["copy',
                        "type": "automated_task",
                        "depends_on": ["end"],
                    },
                ]
            },
        }
    )
    mmd = generate_mermaid(bp)
    body = [line for line in mmd.splitlines()[1:] if line.strip()]
    node = re.compile(r'^    \w+(\["[^"]*"\]|\{"[^"]*"\})$')
    edge = re.compile(r"^    \w+ --> \w+$")
    style = re.compile(r"^    style \w+ fill:#[0-9a-f]{6}$")
    assert all(node.match(x) or edge.match(x) or style.match(x) for x in body), body
    assert sum(1 for x in body if node.match(x)) == 2
    assert sum(1 for x in body if edge.match(x)) == 1
