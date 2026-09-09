"""Tests for Decimal field safety in the extraction model builder.

Background: Pydantic's default JSON Schema for a Decimal field is
``anyOf: [number, string(pattern=<negative-lookahead regex>), null]``. Some
structured-output providers reject the whole request over that unsupported
regex feature; others accept the request but then crash when the model
writes something like "12.40 EUR" into the field, since Decimal parsing
rejects it. create_extraction_model() replaces the advertised schema with a
plain string and cleans common currency/unit noise before Decimal parsing
runs (see gaik.software_components.extractor.schema: DECIMAL_JSON_SCHEMA,
DECIMAL_JSON_SCHEMA_OR_NULL, _clean_decimal_string, decimal_field_repr,
DECIMAL_PERSISTED_HELPER_SOURCE).

Covers: direct model construction, nested/composite fields, the cleaner's
edge cases, and saved-schema reload for both schema-persistence writers
(schema_generation_example.py and vision_extractor.py each regenerate Python
source from field.annotation, which strips the Annotated/WithJsonSchema/
BeforeValidator metadata -- so a persisted-then-reloaded schema needs its own
proof that safety survives the round trip, not just the in-memory model).
"""

from __future__ import annotations

import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import pytest
from gaik.software_components.extractor.schema import (
    ChildRequirements,
    CompositeExtractionRequirements,
    ExtractionRequirements,
    FieldSpec,
    _clean_decimal_string,
    apply_composite_field_policies,
    apply_field_policies,
    create_extraction_model,
)
from gaik.software_components.vision_extractor.vision_extractor import (
    _load_saved_schema,
    _save_schema_to_python,
    _wrap_model_for_verification,
)

EXAMPLE_SCRIPT = (
    Path(__file__).parents[1]
    / "examples"
    / "software_components"
    / "schema-generator"
    / "schema_generation_example.py"
)
EXTRACTOR_EXAMPLE_3 = (
    Path(__file__).parents[1]
    / "examples"
    / "software_components"
    / "extractor"
    / "extraction_example_3.py"
)
EXTRACTOR_EXAMPLE_4 = EXTRACTOR_EXAMPLE_3.with_name("extraction_example_4.py")


def _make_requirements(fields: list[FieldSpec]) -> ExtractionRequirements:
    return ExtractionRequirements(use_case_name="test", fields=fields)


# ---------------------------------------------------------------------------
# Direct extraction: model construction, schema shape, nullability decision
# ---------------------------------------------------------------------------


class TestDirectDecimalModel:
    def test_no_default_is_nullable_no_pattern(self):
        reqs = _make_requirements(
            [FieldSpec(field_name="price", field_type="decimal", description="p")]
        )
        model = create_extraction_model(reqs)
        info = model.model_fields["price"]
        assert not info.is_required()
        assert info.default is None
        schema = model.model_json_schema()["properties"]["price"]
        assert "pattern" not in json.dumps(schema)
        assert schema == {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "default": None,
            "description": "p",
            "title": "Price",
        }

    def test_valid_explicit_default_stays_non_nullable(self):
        """A field with a real stated default must not be forced nullable --
        only fields with no usable default get the None-fallback widening."""
        reqs = _make_requirements(
            [
                FieldSpec(
                    field_name="fee",
                    field_type="decimal",
                    description="f",
                    has_explicit_default=True,
                    default="9.99",
                )
            ]
        )
        model = create_extraction_model(reqs)
        info = model.model_fields["fee"]
        assert info.annotation is Decimal
        assert info.default == Decimal("9.99")
        schema = model.model_json_schema()["properties"]["fee"]
        assert "pattern" not in json.dumps(schema)
        assert schema["type"] == "string"
        # A non-nullable Decimal field must still reject None.
        with pytest.raises(Exception):
            model(fee=None)

    def test_messy_value_cleaned_not_crashed(self):
        reqs = _make_requirements(
            [FieldSpec(field_name="price", field_type="decimal", description="p")]
        )
        model = create_extraction_model(reqs)
        assert model(price="12.40 EUR").price == Decimal("12.40")

    def test_round_trips_through_json(self):
        reqs = _make_requirements(
            [FieldSpec(field_name="price", field_type="decimal", description="p")]
        )
        model = create_extraction_model(reqs)
        obj = model(price="12.40 EUR")
        dumped = obj.model_dump_json()
        assert dumped == '{"price":"12.40"}'
        assert model.model_validate_json(dumped).price == Decimal("12.40")

    def test_apply_field_policies_matches_model_default(self):
        reqs = _make_requirements(
            [FieldSpec(field_name="price", field_type="decimal", description="p")]
        )
        model = create_extraction_model(reqs)
        result = apply_field_policies({}, reqs)
        assert result["price"] is None
        assert model.model_validate(result).price is None


# ---------------------------------------------------------------------------
# Nested / composite fields: a Decimal inside a repeated child collection
# ---------------------------------------------------------------------------


class TestNestedDecimalField:
    @pytest.fixture
    def composite(self):
        parent = _make_requirements(
            [FieldSpec(field_name="po_number", field_type="str", description="po")]
        )
        line_items = _make_requirements(
            [
                FieldSpec(field_name="item", field_type="str", description="item"),
                FieldSpec(field_name="price", field_type="decimal", description="price"),
            ]
        )
        return CompositeExtractionRequirements(
            parent_requirements=parent,
            children=[
                ChildRequirements(
                    container_name="line_items",
                    container_description="items",
                    requirements=line_items,
                )
            ],
        )

    def test_child_row_decimal_field_is_safe(self, composite):
        from gaik.software_components.extractor.schema import (
            _create_parent_with_nested_list_model,
        )

        model = _create_parent_with_nested_list_model(
            parent_requirements=composite.parent_requirements,
            children=composite.children,
        )
        line_item_model = model.model_fields["line_items"].annotation.__args__[0]
        schema = line_item_model.model_json_schema()["properties"]["price"]
        assert "pattern" not in json.dumps(schema)

        record = model.model_validate(
            {"po_number": "PO-1", "line_items": [{"item": "bolt", "price": "12.40 EUR"}]}
        )
        assert record.line_items[0].price == Decimal("12.40")

    def test_composite_field_policies_null_for_missing_price(self, composite):
        result = apply_composite_field_policies(
            {"po_number": "PO-1", "line_items": [{"item": "bolt"}]}, composite
        )
        assert result["line_items"][0]["price"] is None


# ---------------------------------------------------------------------------
# Verification wrapping must retain Decimal's Annotated metadata.
# ---------------------------------------------------------------------------


class TestVerifiedDecimalField:
    def test_schema_has_no_pattern(self):
        reqs = _make_requirements(
            [FieldSpec(field_name="price", field_type="decimal", description="price")]
        )
        wrapped = _wrap_model_for_verification(create_extraction_model(reqs))
        payload = {
            "price": {
                "value": "12.40 EUR",
                "confidence_score": 0.95,
                "confidence_reason": "Explicitly stated.",
            }
        }
        assert wrapped.model_validate(payload).price.value == Decimal("12.40")
        assert "pattern" not in json.dumps(wrapped.model_json_schema())


# ---------------------------------------------------------------------------
# Cleaner edge cases -- conservative policy: accept exactly one clearly
# delimited amount, reject (None) anything ambiguous or multi-number rather
# than fabricating a value.
# ---------------------------------------------------------------------------


class TestCleanDecimalStringEdgeCases:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("12.40 EUR", "12.40"),
            ("0.85 EUR", "0.85"),
            ("EUR 1,234.56", "1234.56"),
            ("USD 42", "42"),
            ("9.99", "9.99"),
            ("0", "0"),
            ("-12.40", "-12.40"),
            ("+12.40", "+12.40"),
            ("123456789", "123456789"),
            ("1,234,567.89", "1234567.89"),
            ("  42  ", "42"),
            ("", None),
            ("   ", None),
            (None, None),
            ("1 234,56 EUR", None),  # European space+comma formatting -- ambiguous, rejected
            ("abc1def2", None),  # multiple embedded numbers -- ambiguous, rejected
            ("not a number", None),
            ("42 dollars", None),  # "dollars" is not a recognized currency token
            ("1,23.56", None),  # malformed thousands grouping
            ("3.14.15", None),  # multiple decimal points
        ],
    )
    def test_cleaner(self, raw, expected):
        assert _clean_decimal_string(raw) == expected

    def test_non_string_passthrough(self):
        assert _clean_decimal_string(Decimal("1.5")) == Decimal("1.5")
        assert _clean_decimal_string(None) is None

    def test_cleaned_values_actually_parse_as_decimal(self):
        for raw, expected in [
            ("12.40 EUR", "12.40"),
            ("EUR 1,234.56", "1234.56"),
            ("1,234,567.89", "1234567.89"),
        ]:
            cleaned = _clean_decimal_string(raw)
            assert Decimal(cleaned) == Decimal(expected)


# ---------------------------------------------------------------------------
# Saved-schema reload -- both persistence writers regenerate Python source
# from field.annotation, which strips the Annotated/WithJsonSchema/
# BeforeValidator metadata create_extraction_model applies. Each must
# reconstruct the same safety net so the fix survives save + reload, not
# just the in-memory model.
# ---------------------------------------------------------------------------


class TestSavedSchemaReload:
    @pytest.fixture
    def requirements(self):
        return _make_requirements(
            [
                FieldSpec(field_name="price", field_type="decimal", description="price"),
                FieldSpec(
                    field_name="fee",
                    field_type="decimal",
                    description="fee",
                    has_explicit_default=True,
                    default="9.99",
                ),
            ]
        )

    def test_vision_extractor_persistence_round_trip(self, requirements, tmp_path):
        model = create_extraction_model(requirements)
        schema_path = tmp_path / "schema.py"
        _save_schema_to_python(model, schema_path)

        loaded = _load_saved_schema(schema_path, model.__name__)
        schema = loaded.model_json_schema()
        assert "pattern" not in json.dumps(schema)

        assert loaded(price="12.40 EUR", fee="9.99").price == Decimal("12.40")
        assert loaded(price="", fee="9.99").price is None
        assert loaded(price="abc1def2", fee="9.99").price is None

        # fee has a valid default -- must stay non-nullable after reload too.
        fee_info = loaded.model_fields["fee"]
        assert fee_info.annotation is Decimal
        assert fee_info.default == Decimal("9.99")
        with pytest.raises(Exception):
            loaded(price="1", fee=None)

    def test_example_script_persistence_round_trip(self, requirements, tmp_path):
        spec = importlib.util.spec_from_file_location("_schema_generation_example", EXAMPLE_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        model = create_extraction_model(requirements)
        schema_path = tmp_path / "schema.py"
        mod.save_schema_to_python(model, schema_path)

        spec2 = importlib.util.spec_from_file_location("_reloaded_schema", schema_path)
        reloaded = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(reloaded)
        loaded = getattr(reloaded, model.__name__)

        schema = loaded.model_json_schema()
        assert "pattern" not in json.dumps(schema)
        assert loaded(price="EUR 1,234.56", fee="9.99").price == Decimal("1234.56")
        assert loaded(price="1 234,56 EUR", fee="9.99").price is None

        fee_info = loaded.model_fields["fee"]
        assert fee_info.annotation is Decimal
        assert fee_info.default == Decimal("9.99")

    def test_no_decimal_helper_emitted_when_no_decimal_field(self, tmp_path):
        """Schemas without a decimal field should not gain the extra header
        block -- keep persisted output minimal for the common case."""
        reqs = _make_requirements([FieldSpec(field_name="name", field_type="str", description="n")])
        model = create_extraction_model(reqs)
        schema_path = tmp_path / "schema.py"
        _save_schema_to_python(model, schema_path)
        source = schema_path.read_text(encoding="utf-8")
        assert "DecimalField" not in source
        assert "_clean_decimal_string" not in source


class TestExtractorExampleDecimalSchemas:
    def test_manual_schema_is_provider_safe(self):
        spec = importlib.util.spec_from_file_location("_extraction_example_3", EXTRACTOR_EXAMPLE_3)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        schema = module.ProjectInfo.model_json_schema()
        assert "pattern" not in json.dumps(schema)
        record = module.ProjectInfo.model_validate(
            {
                "project_title": "Example",
                "project_acronym": "EX",
                "lead_institution": "University",
                "total_funding_eur": "2500000 EUR",
                "start_date": "2024-01-15",
                "project_status": "ongoing",
            }
        )
        assert record.total_funding_eur == Decimal("2500000")

    def test_persisted_example_schema_is_provider_safe(self, tmp_path):
        spec = importlib.util.spec_from_file_location("_extraction_example_4", EXTRACTOR_EXAMPLE_4)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        requirements = _make_requirements(
            [FieldSpec(field_name="price", field_type="decimal", description="price")]
        )
        model = create_extraction_model(requirements)
        schema_path = tmp_path / "schema.py"
        module.save_schema_to_python(model, schema_path)
        loaded = module.load_saved_schema(schema_path, model.__name__)

        assert "pattern" not in json.dumps(loaded.model_json_schema())
        assert loaded(price="12.40 EUR").price == Decimal("12.40")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
