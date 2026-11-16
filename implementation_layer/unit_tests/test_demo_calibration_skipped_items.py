"""The calibration example prints a skipped item (judge_score None) without crashing."""

import ast
from pathlib import Path

EXAMPLE = (
    Path(__file__).resolve().parents[1]
    / "examples/software_components/validators/demo_calibration.py"
)


def _format_item():
    tree = ast.parse(EXAMPLE.read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "format_item")
    namespace: dict = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(EXAMPLE), "exec"), namespace)
    return namespace["format_item"]


def test_a_skipped_item_prints_without_a_judge_score():
    line = _format_item()(
        {"human_score": 4, "judge_score": None, "skipped": "no_flag", "note": "a.pdf"}
    )
    assert "judge=skipped (no_flag)" in line


def test_a_scored_item_prints_its_judge_score():
    line = _format_item()({"human_score": 4, "judge_score": 3.5, "note": "a.pdf"})
    assert "judge=3.50" in line
