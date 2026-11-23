"""The wizard's schema writers define the row class of a collection that may be null.

gaik's ``ChildRequirements.nullable`` makes a child collection ``list[Row] | None``.
The writers followed only a plain ``list[...]`` to find the row model, so the
generated output_schema.py named ``Row`` without defining it and failed with
``NameError`` when imported (second review of #317). Both writers are checked by
importing the source they write.
"""

from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path

import pytest
from gaik.software_components.extractor.schema import (
    ChildRequirements,
    ExtractionRequirements,
    FieldSpec,
    _create_parent_with_nested_list_model,
)

WIZARD_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def invoice_model():
    parent = ExtractionRequirements(
        use_case_name="Invoice",
        fields=[FieldSpec(field_name="invoice_number", field_type="str", description="Number")],
    )
    rows = ExtractionRequirements(
        use_case_name="Line items",
        fields=[
            FieldSpec(field_name="description", field_type="str", description="Item"),
            FieldSpec(field_name="amount", field_type="decimal", description="Amount"),
        ],
    )
    children = [
        ChildRequirements(
            container_name="line_items",
            container_description="Rows of the invoice",
            requirements=rows,
            nullable=True,
        )
    ]
    return _create_parent_with_nested_list_model(parent_requirements=parent, children=children)


def _generate_schema_writer():
    spec = importlib.util.spec_from_file_location(
        "_generate_schema_nullable", WIZARD_ROOT / "scripts" / "generate_schema.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return lambda model: module._schema_to_py(model, model.__name__)


def _run_poc_writer():
    text = (WIZARD_ROOT / "templates" / "poc" / "_generic" / "run_poc.py.tmpl").read_text(
        encoding="utf-8"
    )
    func_src = text[text.index("def _schema_to_py_source") : text.index("def _save_output_schema")]
    namespace: dict = {}
    exec(compile(func_src, "<run_poc_extract>", "exec"), namespace)  # noqa: S102
    return namespace["_schema_to_py_source"]


@pytest.mark.parametrize("writer", [_generate_schema_writer, _run_poc_writer])
def test_the_written_schema_defines_and_validates_a_nullable_collection(
    writer, invoice_model, tmp_path
):
    source = writer()(invoice_model)
    path = tmp_path / "output_schema.py"
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("_nullable_output_schema", path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)  # NameError before the fix

    model = getattr(loaded, invoice_model.__name__)
    assert model.model_json_schema() == invoice_model.model_json_schema()
    assert model.model_validate({"invoice_number": "1"}).line_items is None
    rows = model.model_validate(
        {"invoice_number": "1", "line_items": [{"description": "Bolt", "amount": "12.40 EUR"}]}
    ).line_items
    assert rows[0].amount == Decimal("12.40")
