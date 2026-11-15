"""A FieldsToDocx step validates with the inputs its reference card names."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint  # noqa: E402
from solution_wizard.validator import validate  # noqa: E402


def _step(step_id: str, component: str, inputs: list[str], output: str, after: str | None):
    return {
        "id": step_id,
        "name": step_id.title(),
        "type": "automated_task",
        "component": component,
        "inputs": inputs,
        "outputs": [output],
        **({"depends_on": [after]} if after else {}),
    }


def _generated(kind: str, step_id: str, final: bool = False) -> dict:
    return {
        "type": kind,
        "source": "generated",
        "optional": False,
        "produced_by": step_id,
        "final_output": final,
    }


def test_a_word_report_from_fields_their_trace_and_the_source_text_validates() -> None:
    blueprint = Blueprint.model_validate(
        {
            "blueprint_version": "1.0",
            "use_case": {
                "id": "service_report",
                "name": "Service report",
                "description": "A service note becomes a Word report with evidence.",
                "domain": "test",
            },
            "components": {
                "selected_modules": [],
                "selected_building_blocks": ["Extractor", "SourceTracing", "FieldsToDocx"],
                "custom_components": [],
            },
            "artifacts": {
                "note": {"type": "text", "source": "user_upload", "optional": False},
                "fields": _generated("structured_json", "extract"),
                "trace": _generated("validation_report", "check"),
                "report": _generated("word_document", "write", final=True),
            },
            "workflow": {
                "steps": [
                    _step("extract", "Extractor", ["note"], "fields", None),
                    _step("check", "SourceTracing", ["fields", "note"], "trace", "extract"),
                    _step("write", "FieldsToDocx", ["fields", "trace", "note"], "report", "check"),
                ]
            },
        }
    )
    result = validate(blueprint)
    assert result.ok, result.summary()
