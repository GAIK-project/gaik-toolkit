"""The audio and document PoCs reset a requirements default gaik cannot load.

gaik's FieldSpec.default is a string or null; a hand edit that wrote a list or a
number there made the approved schema unloadable.
"""

import json
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).parent.parent / "templates" / "poc"


def _normalise(template: str):
    source = (TEMPLATES / template / "run_poc.py.tmpl").read_text(encoding="utf-8")
    start = source.index("def _normalise_field_defaults")
    end = source.index("def _load_schema_if_fresh")
    namespace = {"json": json, "Path": Path}
    exec(source[start:end], namespace)
    return namespace["_normalise_field_defaults"]


@pytest.mark.parametrize("template", ["audio_to_structured", "document_to_structured"])
def test_a_non_string_default_is_reset_to_null(template, tmp_path, capsys):
    requirements = {
        "model_name": "Ticket",
        "requirements": {
            "use_case_name": "ticket",
            "fields": [
                {"field_name": "a", "default": "x", "has_explicit_default": True},
                {"field_name": "b", "default": [], "has_explicit_default": True},
                {"field_name": "c", "default": None, "has_explicit_default": False},
            ],
        },
    }
    path = tmp_path / "output_schema_requirements.json"
    path.write_text(json.dumps(requirements), encoding="utf-8")

    _normalise(template)(tmp_path, "output_schema")

    fields = json.loads(path.read_text(encoding="utf-8"))["requirements"]["fields"]
    assert fields[0]["default"] == "x" and fields[0]["has_explicit_default"] is True
    assert fields[1]["default"] is None and fields[1]["has_explicit_default"] is False
    assert fields[2]["default"] is None
    assert "WARNING" in capsys.readouterr().out


@pytest.mark.parametrize("template", ["audio_to_structured", "document_to_structured"])
def test_composite_requirements_are_reset_in_every_part(template, tmp_path):
    requirements = {
        "model_name": "Order",
        "requirements_type": "parent_with_nested_list",
        "requirements": {
            "structure_type": "parent_with_nested_list",
            "parent_requirements": {"fields": [{"field_name": "a", "default": 3}]},
            "children": [
                {
                    "container_name": "rows",
                    "requirements": {"fields": [{"field_name": "b", "default": {"x": 1}}]},
                }
            ],
        },
    }
    path = tmp_path / "output_schema_requirements.json"
    path.write_text(json.dumps(requirements), encoding="utf-8")

    _normalise(template)(tmp_path, "output_schema")

    saved = json.loads(path.read_text(encoding="utf-8"))["requirements"]
    assert saved["parent_requirements"]["fields"][0]["default"] is None
    assert saved["children"][0]["requirements"]["fields"][0]["default"] is None


def test_a_missing_requirements_file_is_left_alone(tmp_path):
    _normalise("audio_to_structured")(tmp_path, "output_schema")

    assert list(tmp_path.iterdir()) == []


def test_a_loadable_file_is_not_rewritten(tmp_path, capsys):
    path = tmp_path / "output_schema_requirements.json"
    text = json.dumps({"requirements": {"fields": [{"field_name": "a", "default": None}]}})
    path.write_text(text, encoding="utf-8")

    _normalise("document_to_structured")(tmp_path, "output_schema")

    assert path.read_text(encoding="utf-8") == text
    assert capsys.readouterr().out == ""
