"""Regression tests for Decimal field safety across all three wizard
schema-writing paths.

Background: gaik's create_extraction_model() wraps `decimal` fields in
Annotated[Decimal (| None), WithJsonSchema(...), BeforeValidator(...)] to
avoid a regex-lookaround JSON Schema some structured-output providers
reject, and a crash when the model writes "12.40 EUR" instead of a bare
number. field.annotation strips that wrapping, so any wizard code that
regenerates a .py file from field.annotation (or, worse, from
inspect.getsource() on a dynamically created class) silently loses the
safety net -- or, for run_poc.py.tmpl, cannot serialize the schema at all.

Three independent code paths were found to be affected, one per test class:
  - scripts/generate_schema.py       (_schema_to_py)      -- lost the wrapper
  - templates/.../run_poc.py.tmpl    (_save_output_schema) -- raised OSError
  - src/solution_wizard/schema_designer.py (build_pydantic_model) -- never
    used Decimal at all; "decimal" fell through _TYPE_MAP's default to str

Each test asserts, per the agreed wording: the saved/reloaded provider-facing
JSON Schema contains no regex pattern, and a value like "12.40 EUR" validates
as Decimal("12.40").
"""

from __future__ import annotations

import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gaik.software_components.extractor.schema import (
    ChildRequirements,
    CompositeExtractionRequirements,
    ExtractionRequirements,
    FieldSpec,
    _create_parent_with_nested_list_model,
    create_extraction_model,
)

WIZARD_ROOT = Path(__file__).parent.parent
_PIPELINE_MARKER = "# Pipeline"


def _make_requirements() -> ExtractionRequirements:
    return ExtractionRequirements(
        use_case_name="po",
        fields=[
            FieldSpec(field_name="name", field_type="str", description="Name"),
            FieldSpec(field_name="price", field_type="decimal", description="Price"),
            FieldSpec(
                field_name="fee",
                field_type="decimal",
                description="Fee",
                has_explicit_default=True,
                default="9.99",
            ),
        ],
    )


def _make_composite_requirements() -> CompositeExtractionRequirements:
    parent = ExtractionRequirements(
        use_case_name="purchase_order",
        fields=[FieldSpec(field_name="order_id", field_type="str", description="Order ID")],
    )
    child = ExtractionRequirements(
        use_case_name="purchase_order_item",
        fields=[FieldSpec(field_name="price", field_type="decimal", description="Price")],
    )
    return CompositeExtractionRequirements(
        parent_requirements=parent,
        children=[
            ChildRequirements(
                container_name="items",
                container_description="Purchase-order items",
                requirements=child,
            )
        ],
    )


def _assert_decimal_safe(loaded_cls: type, price_field: str = "price", fee_field: str = "fee"):
    schema = loaded_cls.model_json_schema()
    assert "pattern" not in json.dumps(schema), (
        f"reloaded schema still advertises a regex pattern: {schema}"
    )
    obj = loaded_cls(**{"name": "x", price_field: "12.40 EUR", fee_field: "9.99"})
    assert getattr(obj, price_field) == Decimal("12.40")


class TestGenerateSchemaPy:
    """scripts/generate_schema.py: _schema_to_py()."""

    @classmethod
    @pytest.fixture(scope="class")
    def module(cls):
        spec = importlib.util.spec_from_file_location(
            "_generate_schema", WIZARD_ROOT / "scripts" / "generate_schema.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_saved_and_reloaded_schema_is_decimal_safe(self, module, tmp_path):
        requirements = _make_requirements()
        model = create_extraction_model(requirements)

        src = module._schema_to_py(model, model.__name__)
        schema_path = tmp_path / "output_schema.py"
        schema_path.write_text(src, encoding="utf-8")

        spec = importlib.util.spec_from_file_location("_reloaded", schema_path)
        reloaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reloaded)
        loaded_cls = getattr(reloaded, model.__name__)

        _assert_decimal_safe(loaded_cls)

    def test_field_with_valid_default_stays_non_nullable(self, module, tmp_path):
        requirements = _make_requirements()
        model = create_extraction_model(requirements)
        src = module._schema_to_py(model, model.__name__)
        schema_path = tmp_path / "output_schema.py"
        schema_path.write_text(src, encoding="utf-8")

        spec = importlib.util.spec_from_file_location("_reloaded2", schema_path)
        reloaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reloaded)
        loaded_cls = getattr(reloaded, model.__name__)

        with pytest.raises(Exception):
            loaded_cls(name="x", price="1", fee=None)

    def test_no_decimal_field_emits_no_helper_block(self, module, tmp_path):
        requirements = ExtractionRequirements(
            use_case_name="plain",
            fields=[FieldSpec(field_name="name", field_type="str", description="Name")],
        )
        model = create_extraction_model(requirements)
        src = module._schema_to_py(model, model.__name__)
        assert "DecimalField" not in src
        assert "_clean_decimal_string" not in src

    def test_composite_requirements_payload_and_summary(self, module):
        requirements = _make_composite_requirements()
        model = _create_parent_with_nested_list_model(
            parent_requirements=requirements.parent_requirements,
            children=requirements.children,
        )

        payload = module._requirements_to_json(model, requirements)

        assert payload["requirements_type"] == "parent_with_nested_list"
        assert module._requirements_field_summary(requirements) == {
            "parent": ["order_id"],
            "items": ["price"],
        }


class TestRunPocTemplate:
    """templates/poc/_generic/run_poc.py.tmpl: _schema_to_py_source()
    (the fallback path formerly calling inspect.getsource() on a
    dynamically created class, which always raised OSError there)."""

    @classmethod
    @pytest.fixture(scope="class")
    def schema_to_py_source(cls):
        tmpl_path = WIZARD_ROOT / "templates" / "poc" / "_generic" / "run_poc.py.tmpl"
        text = tmpl_path.read_text(encoding="utf-8")
        start = text.index("def _schema_to_py_source")
        end = text.index("def _save_output_schema")
        func_src = text[start:end]
        ns: dict = {}
        exec(compile(func_src, "<run_poc_extract>", "exec"), ns)  # noqa: S102
        return ns["_schema_to_py_source"]

    def test_dynamic_model_no_longer_raises_oserror(self, schema_to_py_source):
        """The original inspect.getsource() call always raised OSError for a
        create_model()-built class -- confirm the replacement doesn't."""
        requirements = _make_requirements()
        model = create_extraction_model(requirements)
        src = schema_to_py_source(model)  # must not raise
        assert "class" in src

    def test_saved_and_reloaded_schema_is_decimal_safe(self, schema_to_py_source, tmp_path):
        requirements = _make_requirements()
        model = create_extraction_model(requirements)
        src = schema_to_py_source(model)

        schema_path = tmp_path / "output_schema.py"
        schema_path.write_text(src, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("_reloaded_tmpl", schema_path)
        reloaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reloaded)
        loaded_cls = getattr(reloaded, model.__name__)

        _assert_decimal_safe(loaded_cls)

    def test_composite_requirements_save_and_reload(self, tmp_path):
        tmpl_path = WIZARD_ROOT / "templates" / "poc" / "_generic" / "run_poc.py.tmpl"
        text = tmpl_path.read_text(encoding="utf-8")
        start = text.index("def _load_output_schema")
        end = text.index(_PIPELINE_MARKER, start)
        ns = {"Path": Path, "_requirements_hash": lambda: "test-hash"}
        exec(compile(text[start:end], "<run_poc_schema_helpers>", "exec"), ns)  # noqa: S102

        requirements = _make_composite_requirements()
        model = _create_parent_with_nested_list_model(
            parent_requirements=requirements.parent_requirements,
            children=requirements.children,
        )

        ns["_save_output_schema"](None, model, requirements, tmp_path)
        loaded_model, loaded_requirements = ns["_load_output_schema"](tmp_path)

        assert isinstance(loaded_requirements, CompositeExtractionRequirements)
        loaded = loaded_model.model_validate(
            {"order_id": "PO-1", "items": [{"price": "12.40 EUR"}]}
        )
        assert loaded.items[0].price == Decimal("12.40")

    def test_promoted_data_extractor_template_loads_composite_requirements(self, tmp_path):
        generic_path = WIZARD_ROOT / "templates" / "poc" / "_generic" / "run_poc.py.tmpl"
        generic_text = generic_path.read_text(encoding="utf-8")
        start = generic_text.index("def _load_output_schema")
        end = generic_text.index(_PIPELINE_MARKER, start)
        generic_ns = {"Path": Path, "_requirements_hash": lambda: "test-hash"}
        exec(compile(generic_text[start:end], "<generic_schema_helpers>", "exec"), generic_ns)  # noqa: S102

        requirements = _make_composite_requirements()
        model = _create_parent_with_nested_list_model(
            parent_requirements=requirements.parent_requirements,
            children=requirements.children,
        )
        generic_ns["_save_output_schema"](None, model, requirements, tmp_path)

        promoted_path = (
            WIZARD_ROOT
            / "templates"
            / "poc"
            / "hybrid_dataextractor_pymupdfparser_transcriber_831947a5"
            / "run_poc.py.tmpl"
        )
        promoted_text = promoted_path.read_text(encoding="utf-8")
        start = promoted_text.index("def _load_approved_schema")
        end = promoted_text.index(_PIPELINE_MARKER, start)
        promoted_ns = {"Path": Path, "importlib": importlib, "json": json}
        exec(compile(promoted_text[start:end], "<promoted_schema_loader>", "exec"), promoted_ns)  # noqa: S102

        loaded_model, loaded_requirements = promoted_ns["_load_approved_schema"](tmp_path)

        assert isinstance(loaded_requirements, CompositeExtractionRequirements)
        loaded = loaded_model.model_validate(
            {"order_id": "PO-1", "items": [{"price": "12.40 EUR"}]}
        )
        assert loaded.items[0].price == Decimal("12.40")


class TestSchemaDesigner:
    """src/solution_wizard/schema_designer.py: build_pydantic_model()."""

    def _spec(self) -> dict:
        return {
            "fields": ["name", "price", "fee"],
            "field_types": {"name": "string", "price": "decimal", "fee": "decimal"},
            "required_fields": ["name", "fee"],
            "field_descriptions": {"name": "Name", "price": "Price", "fee": "Fee"},
        }

    def test_decimal_field_type_no_longer_falls_back_to_str(self):
        from solution_wizard.schema_designer import _py_type

        assert _py_type("decimal") == "Decimal"

    def test_saved_and_reloaded_schema_is_decimal_safe(self, tmp_path):
        from solution_wizard.schema_designer import build_pydantic_model

        src = build_pydantic_model(self._spec(), schema_name="Test")
        schema_path = tmp_path / "output_schema.py"
        schema_path.write_text(src, encoding="utf-8")

        spec = importlib.util.spec_from_file_location("_reloaded_designer", schema_path)
        reloaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reloaded)
        loaded_cls = getattr(reloaded, "Test")

        _assert_decimal_safe(loaded_cls)

    def test_required_decimal_field_has_no_default(self):
        from solution_wizard.schema_designer import build_pydantic_model

        src = build_pydantic_model(self._spec(), schema_name="Test")
        ns: dict = {}
        exec(compile(src, "<schema>", "exec"), ns)  # noqa: S102
        model_cls = ns["Test"]
        info = model_cls.model_fields["fee"]
        assert info.is_required()

    def test_optional_decimal_field_is_nullable_not_double_wrapped(self):
        from solution_wizard.schema_designer import build_pydantic_model

        src = build_pydantic_model(self._spec(), schema_name="Test")
        ns: dict = {}
        exec(compile(src, "<schema>", "exec"), ns)  # noqa: S102
        model_cls = ns["Test"]
        info = model_cls.model_fields["price"]
        assert not info.is_required()
        assert info.default is None
        # A missing/blank value must resolve to None, not crash or double-wrap.
        assert model_cls(name="x", fee="1", price=None).price is None

    def test_no_decimal_field_emits_no_helper_block(self):
        from solution_wizard.schema_designer import build_pydantic_model

        spec = {
            "fields": ["name"],
            "field_types": {"name": "string"},
            "required_fields": ["name"],
            "field_descriptions": {"name": "Name"},
        }
        src = build_pydantic_model(spec, schema_name="Plain")
        assert "DecimalField" not in src
        assert "_clean_decimal_string" not in src
