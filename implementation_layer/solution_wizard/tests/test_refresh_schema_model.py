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


def _without_saved_schema(monkeypatch) -> None:
    import builtins

    real_import = builtins.__import__

    def without_saved_schema(name, *args, **kwargs):
        if name == "gaik.software_components.extractor.saved_schema":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_saved_schema)


def test_with_a_gaik_that_reads_the_py_file_an_older_model_file_is_named_and_kept(
    tmp_path, monkeypatch, capsys
):
    """A later gaik would load the older model file, so the script says so. It keeps the
    file: without it gaik rebuilds the model from the requirements, which drops an edit
    made only in output_schema.py, and the PoC no longer writes it again from the .py."""
    schemas = _schemas(tmp_path, CORRECTED)
    before = (schemas / "output_schema_model.json").read_text(encoding="utf-8")
    _without_saved_schema(monkeypatch)
    monkeypatch.setattr("sys.argv", ["refresh_schema_model.py", "--schemas-dir", str(schemas)])

    assert _script().main() == 0
    captured = capsys.readouterr()
    assert "Model file not needed" not in captured.out
    assert "WARNING" in captured.err and "output_schema_model.json" in captured.err
    assert "before this edit" in captured.err
    assert (schemas / "output_schema_model.json").read_text(encoding="utf-8") == before


def test_with_a_gaik_that_reads_the_py_file_and_no_model_file_nothing_is_needed(
    tmp_path, monkeypatch, capsys
):
    schemas = _schemas(tmp_path, CORRECTED)
    (schemas / "output_schema_model.json").unlink()
    _without_saved_schema(monkeypatch)
    monkeypatch.setattr("sys.argv", ["refresh_schema_model.py", "--schemas-dir", str(schemas)])

    assert _script().main() == 0
    captured = capsys.readouterr()
    assert "Model file not needed" in captured.out and not captured.err
    assert not (schemas / "output_schema_model.json").exists()


@pytest.mark.parametrize(
    "field",
    [
        'title: str = Field(max_length=5, description="Ticket title")',
        'title: str = Field(min_length=1, description="Ticket title")',
        'count: int = Field(le=10, description="Count")',
    ],
)
def test_a_field_constraint_is_refused_as_step_4_5_says(tmp_path, field):
    schemas = _schemas(
        tmp_path,
        f"from pydantic import BaseModel, Field\n\nclass Ticket(BaseModel):\n    {field}\n",
    )
    before = (schemas / "output_schema_model.json").read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="constraint"):
        _script().refresh(schemas)

    assert (schemas / "output_schema_model.json").read_text(encoding="utf-8") == before


_PATTERN_IMPORTS = (
    "from typing import Annotated, Optional\n"
    "from pydantic import BaseModel, Field, StringConstraints, constr\n\n"
)


@pytest.mark.parametrize(
    ("annotation", "saved_type"),
    [
        ('Annotated[str, constr(pattern=r"^T-")]', {"type": "str", "pattern": "^T-"}),
        (
            'Optional[Annotated[str, constr(pattern=r"^T-")]]',
            {"type": "optional", "inner": {"type": "str", "pattern": "^T-"}},
        ),
        (
            'list[Annotated[str, constr(pattern=r"^T-")]]',
            {"type": "list", "items": {"type": "str", "pattern": "^T-"}},
        ),
    ],
)
def test_a_pattern_on_a_text_field_is_kept_in_the_form_step_4_5_names(
    tmp_path, annotation, saved_type
):
    schemas = _schemas(
        tmp_path,
        _PATTERN_IMPORTS + "class Ticket(BaseModel):\n"
        f'    title: {annotation} = Field(description="Ticket title")\n',
    )

    _script().refresh(schemas)

    saved = json.loads((schemas / "output_schema_model.json").read_text(encoding="utf-8"))
    [field] = saved["models"][0]["fields"]
    assert field["type"] == saved_type


@pytest.mark.parametrize(
    "field",
    [
        'title: str = Field(pattern=r"^T-", description="Ticket title")',
        'title: constr(pattern=r"^T-") = Field(description="Ticket title")',
        'title: Annotated[str, StringConstraints(pattern=r"^T-")] = Field(description="Title")',
        'title: Annotated[str, constr(pattern=r"^T-", max_length=9)] = Field(description="T")',
    ],
)
def test_a_pattern_in_any_other_form_is_refused_as_step_4_5_says(tmp_path, field):
    schemas = _schemas(tmp_path, _PATTERN_IMPORTS + f"class Ticket(BaseModel):\n    {field}\n")
    before = (schemas / "output_schema_model.json").read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="cannot be saved"):
        _script().refresh(schemas)

    assert (schemas / "output_schema_model.json").read_text(encoding="utf-8") == before


def test_step_4_5_names_the_pattern_form_the_refresh_keeps():
    skill = (Path(__file__).parents[1] / "SKILL.md").read_text(encoding="utf-8")
    assert '`Annotated[str, constr(pattern=r"...")]`' in skill
    assert "`Field(pattern=...)`" in skill
