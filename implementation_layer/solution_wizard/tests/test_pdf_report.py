"""Tests for the PoC PDF report renderer (templates/poc/_common/pdf_report.py.tmpl)
and the scaffolder's opt-in PDF wiring.

The renderer template has no ${...} variables, so it is imported directly from a
copy of the template. ReportLab runs fully offline — no API, no network.
"""

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint
from solution_wizard.scaffolder import _build_variables, _read_template, _fill, _wants_pdf

reportlab = pytest.importorskip("reportlab")  # skip if reportlab not installed

TEMPLATE = Path(__file__).parent.parent / "templates" / "poc" / "_common" / "pdf_report.py.tmpl"


def _load_renderer(tmp_path: Path):
    """Copy the template to a .py file and import write_pdf_report from it."""
    mod_path = tmp_path / "pdf_report.py"
    mod_path.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("pdf_report_under_test", mod_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.write_pdf_report


def _is_pdf(path: Path) -> bool:
    data = path.read_bytes()
    return len(data) > 0 and data[:5] == b"%PDF-"


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def test_template_is_valid_python():
    ast.parse(TEMPLATE.read_text(encoding="utf-8"))


def test_structured_dict_with_nesting(tmp_path):
    write = _load_renderer(tmp_path)
    data = {
        "full_name": "Jane Doe",
        "age": 41,
        "allergies": None,  # blank -> em dash
        "medications": [
            {"name": "Aspirin", "dose": "100mg", "frequency": "daily"},
            {"name": "Metformin", "dose": "500mg"},
        ],
        "notes": ["stable", "review in 2 weeks"],
    }
    out = tmp_path / "struct.pdf"
    write(data, out, title="Clinical Record", subtitle="Schema", metadata={"Source file": "note.wav"})
    assert _is_pdf(out)


def test_list_of_records(tmp_path):
    write = _load_renderer(tmp_path)
    data = [{"po_number": "PO-1", "total": 1200}, {"po_number": "PO-2", "total": None}]
    out = tmp_path / "records.pdf"
    write(data, out, title="Purchase Orders")
    assert _is_pdf(out)


def test_unstructured_text_with_headings(tmp_path):
    write = _load_renderer(tmp_path)
    text = "# Summary\nA leak occurred.\n\n## Details\nLocation: pump room.\n\n## Action\nDispatched."
    out = tmp_path / "text.pdf"
    write(text, out, title="Incident Report")
    assert _is_pdf(out)


def test_empty_and_unicode(tmp_path):
    write = _load_renderer(tmp_path)
    out = tmp_path / "uni.pdf"
    write({"kuvaus": "Sähkövika työmaalla", "arvo": ""}, out, title="Raportti")
    assert _is_pdf(out)


def test_creates_parent_dir(tmp_path):
    write = _load_renderer(tmp_path)
    out = tmp_path / "nested" / "deep" / "r.pdf"
    write({"a": 1}, out, title="T")
    assert out.exists() and _is_pdf(out)


# ---------------------------------------------------------------------------
# Scaffolder opt-in wiring
# ---------------------------------------------------------------------------

def _blueprint(output_types) -> Blueprint:
    return Blueprint.model_validate({
        "blueprint_version": "1.0",
        "use_case": {"id": "uc", "name": "My Use Case", "description": "x", "domain": "test"},
        "technical_spec": {"input_types": ["audio"], "output_types": output_types, "language": "en"},
        "target_output_spec": {"schema_name": "MyOut", "fields": ["a", "b"]},
        "components": {"selected_modules": [], "selected_building_blocks": ["Transcriber", "Extractor", "LLMJudge"], "custom_components": []},
        "artifacts": {
            "src": {"type": "audio", "source": "user_upload", "optional": False},
            "out": {"type": "structured_json", "source": "generated", "optional": False, "final_output": True, "produced_by": "e"},
        },
        "workflow": {"steps": [
            {"id": "e", "name": "E", "type": "automated_task", "component": "Extractor", "inputs": ["src"], "outputs": ["out"]},
        ]},
    })


def test_wants_pdf_detection():
    assert _wants_pdf(_blueprint(["structured_json", "pdf"])) is True
    assert _wants_pdf(_blueprint(["report"])) is True
    assert _wants_pdf(_blueprint(["structured_json"])) is False
    assert _wants_pdf(_blueprint([])) is False


@pytest.mark.parametrize("pattern", ["audio_to_structured", "document_to_structured", "rag", "_generic"])
def test_pdf_block_present_only_when_requested(pattern):
    for wants, output_types in [(True, ["structured_json", "pdf"]), (False, ["structured_json"])]:
        variables = _build_variables(_blueprint(output_types), pattern)
        filled = _fill(_read_template(pattern, "run_poc.py.tmpl"), variables)
        ast.parse(filled)  # must always be valid Python
        assert ("write_pdf_report" in filled) is wants


def test_scaffold_writes_pdf_helper_and_requirement(tmp_path):
    from solution_wizard.scaffolder import scaffold_poc
    info = scaffold_poc(_blueprint(["structured_json", "pdf"]), tmp_path)
    poc = info["poc_dir"]
    assert (poc / "pdf_report.py").exists()
    assert "reportlab" in (poc / "requirements.txt").read_text()
    run_poc = (poc / "run_poc.py").read_text()
    assert "write_pdf_report" in run_poc
    ast.parse(run_poc)


def test_scaffold_no_pdf_when_not_requested(tmp_path):
    from solution_wizard.scaffolder import scaffold_poc
    info = scaffold_poc(_blueprint(["structured_json"]), tmp_path)
    poc = info["poc_dir"]
    assert not (poc / "pdf_report.py").exists()
    assert "reportlab" not in (poc / "requirements.txt").read_text()
