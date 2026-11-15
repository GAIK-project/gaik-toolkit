"""output_schema.json is built from the spec as data, and says the same as output_schema.py."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from solution_wizard import schema_designer  # noqa: E402
from solution_wizard.schema_designer import build_pydantic_model, write_schema_files  # noqa: E402

SPECS = {
    "plain": {
        "schema_name": "SimpleOutput",
        "fields": ["name", "value", "count", "ratio", "done", "tags", "when"],
        "field_types": {
            "count": "integer",
            "ratio": "number",
            "done": "boolean",
            "tags": "list",
            "when": "date",
        },
        "required_fields": ["name", "count"],
        "field_descriptions": {"name": "Who", "ratio": "Share of the whole"},
    },
    "choices": {
        "schema_name": "Ticket",
        "fields": ["urgency", "kind", "code"],
        "required_fields": ["urgency"],
        "allowed_values": {
            "urgency": ["low", "high", "2nd line"],
            "kind": ["a b", "c-d"],
            "code": [1, 2],
        },
        "field_descriptions": {"urgency": "How urgent"},
    },
    "money": {
        "schema_name": "Invoice",
        "fields": ["total", "tax", "currency_note"],
        "field_types": {"total": "decimal", "tax": "money"},
        "required_fields": ["total"],
        "field_descriptions": {"tax": "VAT amount"},
    },
    "sections": {
        "schema_name": "Report",
        "fields": [
            {"id": "summary", "title": "Summary", "instructions": "Two sentences"},
            {"id": "risks", "title": "Risks"},
        ],
        "required_fields": [{"id": "summary"}],
    },
}


def _schema_of_source(spec: dict, name: str) -> dict:
    """The JSON Schema of the generated source, run here in the test only, as the reference."""
    namespace: dict = {}
    exec(build_pydantic_model(spec, name), namespace)  # noqa: S102 - test reference
    return namespace[name].model_json_schema()


@pytest.mark.parametrize("key", list(SPECS))
def test_the_json_schema_is_the_one_the_source_defines(key) -> None:
    spec = SPECS[key]
    built = schema_designer._model_from_spec(spec, spec["schema_name"]).model_json_schema()
    assert built == _schema_of_source(spec, spec["schema_name"])


def test_writing_the_schema_files_runs_no_generated_code(tmp_path, monkeypatch) -> None:
    def refuse(*_args, **_kwargs):
        raise AssertionError("generated source was executed")

    # Looked up in the module's globals before the builtins, so only its own calls refuse.
    monkeypatch.setattr(schema_designer, "exec", refuse, raising=False)
    monkeypatch.setattr(schema_designer, "compile", refuse, raising=False)
    spec = SPECS["choices"]
    written = write_schema_files(spec, spec["schema_name"], tmp_path)

    schema = json.loads(written["output_schema.json"].read_text())
    assert schema["title"] == "Ticket"
    assert "UrgencyEnum" in schema["$defs"]


def test_text_in_the_spec_stays_text(tmp_path) -> None:
    spec = {
        "schema_name": "Note",
        "fields": ["body"],
        "required_fields": ["body"],
        "field_descriptions": {"body": 'Quote " and a new\nline, and {braces}'},
    }
    written = write_schema_files(spec, "Note", tmp_path)
    schema = json.loads(written["output_schema.json"].read_text())
    assert schema["properties"]["body"]["description"] == 'Quote " and a new\nline, and {braces}'
