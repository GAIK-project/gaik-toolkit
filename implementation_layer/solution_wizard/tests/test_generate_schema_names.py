"""Generated schema source: names only as Python names, the description as a literal."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("gaik")
from pydantic import create_model  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate_schema.py"


def _script():
    spec = importlib.util.spec_from_file_location("_schema_names_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_description_that_ends_a_docstring_stays_text() -> None:
    script = _script()
    model = create_model("Ticket", title=(str, ...))
    model.__doc__ = 'Ends here """ and then a line\nwith a backslash \\ too'
    source = script._schema_to_py(model, "Ticket")

    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    assert ast.get_docstring(cls) == model.__doc__
    # Nothing but the docstring, the config and the field in the class body.
    assert [type(n).__name__ for n in cls.body] == ["Expr", "Assign", "AnnAssign"]


@pytest.mark.parametrize("name", ["Ticket(BaseModel): pass\nclass X", "class", "a b"])
def test_a_class_name_that_is_not_a_python_name_is_refused(name) -> None:
    model = create_model("Ticket", title=(str, ...))
    model.__name__ = name
    with pytest.raises(ValueError, match="not a valid Python name"):
        _script()._schema_to_py(model, "Ticket")


@pytest.mark.parametrize("name", ["class", "a b", "x: int = 1\n    y"])
def test_a_field_name_that_is_not_a_python_name_is_refused(name) -> None:
    model = create_model("Ticket", title=(str, ...))
    model.model_fields[name] = model.model_fields.pop("title")
    with pytest.raises(ValueError, match="not a valid Python name"):
        _script()._schema_to_py(model, "Ticket")
