"""A corrected output_schema.py reaches the PoC through output_schema_model.json."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("gaik.software_components.extractor.saved_schema")
from gaik.software_components.extractor.saved_schema import (  # noqa: E402
    read_model_file,
    write_model_file,
)
from pydantic import BaseModel, Field  # noqa: E402

SCRIPT = Path(__file__).parents[1] / "scripts" / "refresh_schema_model.py"


class Ticket(BaseModel):
    title: str = Field(description="Ticket title")


def _script():
    spec = importlib.util.spec_from_file_location("_refresh_schema_model", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _schemas(tmp_path: Path, py_source: str, model_name: str = "Ticket") -> Path:
    schemas = tmp_path / "schemas"
    schemas.mkdir()
    write_model_file(Ticket, schemas / "output_schema_model.json")
    (schemas / "output_schema_requirements.json").write_text(
        json.dumps({"model_name": model_name, "requirements": {}}), encoding="utf-8"
    )
    (schemas / "output_schema.py").write_text(py_source, encoding="utf-8")
    return schemas


CORRECTED = """
from pydantic import BaseModel, Field

class Ticket(BaseModel):
    title: str = Field(description="Ticket title")
    priority: int = Field(default=0, description="Priority, added in review")
"""


def test_a_field_added_to_the_py_file_reaches_the_model_file(tmp_path):
    schemas = _schemas(tmp_path, CORRECTED)

    _script().refresh(schemas)

    model = read_model_file(schemas / "output_schema_model.json")
    assert list(model.model_fields) == ["title", "priority"]


def test_a_py_file_without_the_named_class_leaves_the_model_file_as_it_was(tmp_path):
    schemas = _schemas(tmp_path, CORRECTED, model_name="Invoice")
    before = (schemas / "output_schema_model.json").read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="no class 'Invoice'"):
        _script().refresh(schemas)

    assert (schemas / "output_schema_model.json").read_text(encoding="utf-8") == before
    assert not list(schemas.glob("*.tmp"))


def test_a_model_the_saved_format_cannot_describe_is_refused_and_nothing_changes(tmp_path):
    schemas = _schemas(
        tmp_path,
        "from pydantic import BaseModel, Field\n\n"
        "class Ticket(BaseModel):\n    count: int = Field(ge=0)\n",
    )
    before = (schemas / "output_schema_model.json").read_text(encoding="utf-8")

    with pytest.raises(ValueError):
        _script().refresh(schemas)

    assert (schemas / "output_schema_model.json").read_text(encoding="utf-8") == before
    assert not list(schemas.glob("*.tmp"))


def test_the_command_line_reports_a_refusal_with_exit_code_1(tmp_path, monkeypatch, capsys):
    schemas = _schemas(tmp_path, CORRECTED, model_name="Invoice")
    monkeypatch.setattr("sys.argv", ["refresh_schema_model.py", "--schemas-dir", str(schemas)])

    assert _script().main() == 1
    assert "Model file not refreshed" in capsys.readouterr().err


def test_a_type_correction_in_the_py_file_is_the_type_load_schema_gives(tmp_path):
    pytest.importorskip("fitz")
    from gaik.software_modules.documents_to_structured_data.pipeline import (
        DocumentsToStructuredData,
    )

    schemas = _schemas(
        tmp_path,
        "from pydantic import BaseModel, Field\n\n"
        "class Ticket(BaseModel):\n"
        '    title: int = Field(description="Ticket title")\n',
    )
    requirements = {
        "use_case_name": "ticket",
        "fields": [{"field_name": "title", "field_type": "int", "description": "Ticket title"}],
    }
    (schemas / "output_schema_requirements.json").write_text(
        json.dumps({"model_name": "Ticket", "requirements": requirements}), encoding="utf-8"
    )
    pipeline = object.__new__(DocumentsToStructuredData)
    before, _ = pipeline.load_schema(schemas, "output_schema")
    assert before.model_fields["title"].annotation is str

    _script().refresh(schemas)

    after, _ = pipeline.load_schema(schemas, "output_schema")
    assert after.model_fields["title"].annotation is int


def test_with_a_gaik_that_reads_the_py_file_the_command_line_writes_nothing_and_passes(
    tmp_path, monkeypatch, capsys
):
    import builtins

    schemas = _schemas(tmp_path, CORRECTED)
    before = (schemas / "output_schema_model.json").read_text(encoding="utf-8")
    real_import = builtins.__import__

    def without_saved_schema(name, *args, **kwargs):
        if name == "gaik.software_components.extractor.saved_schema":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_saved_schema)
    monkeypatch.setattr("sys.argv", ["refresh_schema_model.py", "--schemas-dir", str(schemas)])

    assert _script().main() == 0
    assert "Model file not needed" in capsys.readouterr().out
    assert (schemas / "output_schema_model.json").read_text(encoding="utf-8") == before
