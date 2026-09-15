"""Unit tests for field policy logic — no LLM calls required."""

from unittest import mock

import pytest
from gaik.software_components.extractor.extractor import DataExtractor
from gaik.software_components.extractor.schema import (
    ChildRequirements,
    CompositeExtractionRequirements,
    ExtractionRequirements,
    FieldSpec,
    apply_composite_field_policies,
    apply_field_policies,
    create_extraction_model,
    normalize_composite_extracted_data,
)


def _make_requirements(fields: list[FieldSpec]) -> ExtractionRequirements:
    return ExtractionRequirements(use_case_name="test", fields=fields)


# ---------------------------------------------------------------------------
# FieldSpec backward compatibility
# ---------------------------------------------------------------------------


class TestFieldSpecCompat:
    def test_default_required_true(self):
        f = FieldSpec(field_name="x", field_type="str", description="d")
        assert f.required is True
        assert f.nullable is False

    def test_required_false_sets_nullable(self):
        f = FieldSpec(field_name="x", field_type="str", description="d", required=False)
        assert f.nullable is True
        assert f.required is False

    def test_explicit_nullable_overrides_required(self):
        f = FieldSpec(
            field_name="x", field_type="str", description="d", nullable=True, required=True
        )
        assert f.nullable is True
        assert f.required is False

    def test_nullable_false_keeps_required(self):
        f = FieldSpec(field_name="x", field_type="str", description="d", nullable=False)
        assert f.required is True


# ---------------------------------------------------------------------------
# Test 1: Enum with explicit default
# ---------------------------------------------------------------------------


class TestEnumExplicitDefault:
    def test_model_field(self):
        reqs = _make_requirements(
            [
                FieldSpec(
                    field_name="status",
                    field_type="str",
                    description="status",
                    enum=["active", "inactive"],
                    has_explicit_default=True,
                    default="active",
                )
            ]
        )
        model = create_extraction_model(reqs)
        info = model.model_fields["status"]
        assert not info.is_required()
        assert info.default == "active"


# ---------------------------------------------------------------------------
# Test 2: Enum with "" as missing indicator
# ---------------------------------------------------------------------------


class TestEnumEmptyDefault:
    def test_model_field(self):
        reqs = _make_requirements(
            [
                FieldSpec(
                    field_name="color",
                    field_type="str",
                    description="color",
                    enum=["red", "blue"],
                )
            ]
        )
        model = create_extraction_model(reqs)
        info = model.model_fields["color"]
        assert not info.is_required()
        assert info.default == ""

    def test_empty_string_in_enum(self):
        reqs = _make_requirements(
            [
                FieldSpec(
                    field_name="color",
                    field_type="str",
                    description="color",
                    enum=["red", "blue"],
                )
            ]
        )
        model = create_extraction_model(reqs)
        obj = model(color="")
        assert obj.color == ""


# ---------------------------------------------------------------------------
# Test 3: String field — required (no explicit default)
# ---------------------------------------------------------------------------


class TestStringRequired:
    def test_str_no_default_is_required(self):
        reqs = _make_requirements(
            [FieldSpec(field_name="name", field_type="str", description="name")]
        )
        model = create_extraction_model(reqs)
        info = model.model_fields["name"]
        assert info.is_required()


# ---------------------------------------------------------------------------
# Regression: bool field with NO declared default at all (not merely an
# incompatible explicit ''). This is a deliberate, separately-approved public
# behavior decision, not a side effect of the has_explicit_default='' fix
# above -- see the comment above `uses_none_fallback` in create_extraction_model.
#
# Concretely: in VisionExtractor.extract(), _post_process() (which calls
# apply_field_policies) runs BEFORE the final _validate_result() against the
# original extraction_model. A vision response that genuinely omits a bool
# key gets patched to None by apply_field_policies's existing fallback (that
# part predates this fix), and previously failed that final validation
# because a plain, non-nullable `bool` field with no default built as
# Pydantic-required. bool now mirrors numeric: no usable default and not
# explicitly nullable widens the annotation to `bool | None` with a None
# fallback, so model construction and post-processing agree, and that final
# validation succeeds.
#
# (DataExtractor's OpenAI/.parse() path and ProviderClient.chat_parsed() both
# validate strictly before apply_field_policies ever runs, so they were never
# at risk of that specific crash -- but they still benefit from the same
# annotation change, since a missing key against an optional-with-default
# field is accepted by model_validate without the key needing to be present
# at all.)
# ---------------------------------------------------------------------------


class TestBoolNoDefaultAtAll:
    def test_becomes_nullable_not_required(self):
        reqs = _make_requirements(
            [FieldSpec(field_name="signed", field_type="bool", description="s")]
        )
        model = create_extraction_model(reqs)
        info = model.model_fields["signed"]
        assert not info.is_required()
        assert info.default is None

    def test_missing_boolean_key_becomes_none(self):
        reqs = _make_requirements(
            [FieldSpec(field_name="signed", field_type="bool", description="s")]
        )
        model = create_extraction_model(reqs)
        result = apply_field_policies({}, reqs)
        assert result["signed"] is None
        assert model.model_validate(result).signed is None

    def test_explicitly_false_value_stays_false(self):
        """A real False in the extracted data must not be reinterpreted as
        missing -- the whole point of widening to bool | None is to keep
        "unmentioned" (None) distinguishable from "explicitly false"."""
        reqs = _make_requirements(
            [FieldSpec(field_name="signed", field_type="bool", description="s")]
        )
        model = create_extraction_model(reqs)
        result = apply_field_policies({"signed": False}, reqs)
        assert result["signed"] is False
        assert model.model_validate(result).signed is False

    def test_valid_explicit_default_still_honored(self):
        """The widening only applies when there is no usable default; a real
        explicit bool default must still be built and honored as before."""
        reqs = _make_requirements(
            [
                FieldSpec(
                    field_name="signed",
                    field_type="bool",
                    description="s",
                    has_explicit_default=True,
                    default="true",
                )
            ]
        )
        model = create_extraction_model(reqs)
        info = model.model_fields["signed"]
        assert info.default is True
        assert apply_field_policies({}, reqs)["signed"] is True

    def test_explicit_nullable_bool_still_none(self):
        reqs = _make_requirements(
            [FieldSpec(field_name="signed", field_type="bool", description="s", nullable=True)]
        )
        model = create_extraction_model(reqs)
        info = model.model_fields["signed"]
        assert not info.is_required()
        assert info.default is None


# ---------------------------------------------------------------------------
# Test 4: Nullable string
# ---------------------------------------------------------------------------


class TestNullableString:
    def test_nullable_allows_none(self):
        reqs = _make_requirements(
            [FieldSpec(field_name="note", field_type="str", description="note", nullable=True)]
        )
        model = create_extraction_model(reqs)
        info = model.model_fields["note"]
        assert not info.is_required()
        assert info.default is None
        obj = model(note=None)
        assert obj.note is None


# ---------------------------------------------------------------------------
# Test 5: Optional key (not required in output)
# ---------------------------------------------------------------------------


class TestOptionalKey:
    def test_not_required_in_output(self):
        reqs = _make_requirements(
            [
                FieldSpec(
                    field_name="extra",
                    field_type="str",
                    description="extra",
                    required_in_output=False,
                    nullable=True,
                )
            ]
        )
        data = {}
        result = apply_field_policies(data, reqs)
        assert "extra" not in result


# ---------------------------------------------------------------------------
# Test 6: Required key with "" placeholder
# ---------------------------------------------------------------------------


class TestRequiredKeyEmptyPlaceholder:
    def test_missing_required_str_gets_empty(self):
        reqs = _make_requirements(
            [FieldSpec(field_name="title", field_type="str", description="title")]
        )
        data = {}
        result = apply_field_policies(data, reqs)
        assert result["title"] == ""


# ---------------------------------------------------------------------------
# Test 7: Boolean-like enum with default
# ---------------------------------------------------------------------------


class TestBooleanEnum:
    def test_yes_no_enum(self):
        reqs = _make_requirements(
            [
                FieldSpec(
                    field_name="flag",
                    field_type="str",
                    description="yes or no",
                    enum=["Kyllä", "Ei"],
                    has_explicit_default=True,
                    default="Ei",
                )
            ]
        )
        model = create_extraction_model(reqs)
        info = model.model_fields["flag"]
        assert info.default == "Ei"
        obj = model()
        assert obj.flag == "Ei"


# ---------------------------------------------------------------------------
# Test 8: apply_field_policies fixes None → "" for non-nullable str
# ---------------------------------------------------------------------------


class TestPolicyFixesNull:
    def test_null_to_empty(self):
        reqs = _make_requirements([FieldSpec(field_name="val", field_type="str", description="v")])
        data = {"val": None}
        result = apply_field_policies(data, reqs)
        assert result["val"] == ""

    def test_null_nullable_stays_none(self):
        reqs = _make_requirements(
            [FieldSpec(field_name="val", field_type="str", description="v", nullable=True)]
        )
        data = {"val": None}
        result = apply_field_policies(data, reqs)
        assert result["val"] is None

    def test_out_of_enum_fixed(self):
        reqs = _make_requirements(
            [
                FieldSpec(
                    field_name="s",
                    field_type="str",
                    description="s",
                    enum=["a", "b"],
                    has_explicit_default=True,
                    default="a",
                )
            ]
        )
        data = {"s": "INVALID"}
        result = apply_field_policies(data, reqs)
        assert result["s"] == "a"

    def test_preserves_extra_keys(self):
        reqs = _make_requirements([FieldSpec(field_name="x", field_type="str", description="x")])
        data = {"x": "ok", "extra_key": 42}
        result = apply_field_policies(data, reqs)
        assert result["extra_key"] == 42

    def test_blank_numeric_string_to_none(self):
        reqs = _make_requirements(
            [FieldSpec(field_name="price", field_type="decimal", description="price")]
        )
        data = {"price": ""}
        result = apply_field_policies(data, reqs)
        model = create_extraction_model(reqs)

        assert result["price"] is None
        assert model.model_validate(result).price is None


# ---------------------------------------------------------------------------
# Regression: explicit default='' misapplied to non-string field types.
#
# The requirements-parsing LLM can turn a general instruction such as "leave
# unmentioned fields empty" into has_explicit_default=True, default='' for
# EVERY field, regardless of field_type. An empty string is only a valid
# default for str/date; on int/float/decimal/bool/list[str]/list[dict] it
# must be normalized to the type's own empty value everywhere the default is
# consumed: model construction, missing-key post-processing, serialization,
# and JSON revalidation.
# ---------------------------------------------------------------------------


class TestIncompatibleEmptyStringDefaultMatrix:
    """FieldSpec(has_explicit_default=True, default='') for every declared type."""

    def _field(self, field_type: str) -> FieldSpec:
        return FieldSpec(
            field_name="val",
            field_type=field_type,
            description="v",
            has_explicit_default=True,
            default="",
        )

    def test_str_keeps_empty_string(self):
        reqs = _make_requirements([self._field("str")])
        model = create_extraction_model(reqs)
        info = model.model_fields["val"]
        assert not info.is_required()
        assert info.default == ""
        obj = model()
        assert obj.val == ""
        assert model.model_validate_json(obj.model_dump_json()).val == ""
        assert apply_field_policies({}, reqs)["val"] == ""

    def test_date_keeps_empty_string(self):
        reqs = _make_requirements([self._field("date")])
        model = create_extraction_model(reqs)
        info = model.model_fields["val"]
        assert not info.is_required()
        assert info.default == ""
        assert apply_field_policies({}, reqs)["val"] == ""

    def test_int_becomes_nullable_none(self):
        reqs = _make_requirements([self._field("int")])
        model = create_extraction_model(reqs)
        info = model.model_fields["val"]
        assert not info.is_required()
        assert info.default is None
        obj = model()
        assert obj.val is None
        dumped = obj.model_dump_json()
        assert '"val":null' in dumped
        assert model.model_validate_json(dumped).val is None
        assert apply_field_policies({}, reqs)["val"] is None

    def test_float_becomes_nullable_none(self):
        reqs = _make_requirements([self._field("float")])
        model = create_extraction_model(reqs)
        info = model.model_fields["val"]
        assert info.default is None
        assert model().val is None
        assert apply_field_policies({}, reqs)["val"] is None

    def test_decimal_becomes_nullable_none(self):
        reqs = _make_requirements([self._field("decimal")])
        model = create_extraction_model(reqs)
        info = model.model_fields["val"]
        assert info.default is None
        assert model().val is None
        assert apply_field_policies({}, reqs)["val"] is None

    def test_bool_becomes_nullable_none(self):
        reqs = _make_requirements([self._field("bool")])
        model = create_extraction_model(reqs)
        info = model.model_fields["val"]
        assert not info.is_required()
        assert info.default is None
        obj = model()
        assert obj.val is None
        assert model.model_validate_json(obj.model_dump_json()).val is None
        assert apply_field_policies({}, reqs)["val"] is None

    def test_list_str_becomes_empty_list(self):
        reqs = _make_requirements([self._field("list[str]")])
        model = create_extraction_model(reqs)
        info = model.model_fields["val"]
        assert not info.is_required()
        assert info.default_factory is not None
        assert info.default_factory() == []
        obj = model()
        assert obj.val == []
        assert model.model_validate_json(obj.model_dump_json()).val == []
        assert apply_field_policies({}, reqs)["val"] == []

    def test_list_dict_becomes_empty_list(self):
        reqs = _make_requirements([self._field("list[dict]")])
        model = create_extraction_model(reqs)
        info = model.model_fields["val"]
        assert not info.is_required()
        assert info.default_factory is not None
        assert info.default_factory() == []
        assert apply_field_policies({}, reqs)["val"] == []


class TestExplicitValidDefaultsStillHonored:
    """Legitimate, type-compatible explicit defaults must survive the fix."""

    def test_string_default_preserved(self):
        reqs = _make_requirements(
            [
                FieldSpec(
                    field_name="note",
                    field_type="str",
                    description="n",
                    has_explicit_default=True,
                    default="n/a",
                )
            ]
        )
        model = create_extraction_model(reqs)
        assert model.model_fields["note"].default == "n/a"
        assert apply_field_policies({}, reqs)["note"] == "n/a"

    def test_enum_default_preserved(self):
        reqs = _make_requirements(
            [
                FieldSpec(
                    field_name="status",
                    field_type="str",
                    description="s",
                    enum=["active", "inactive"],
                    has_explicit_default=True,
                    default="active",
                )
            ]
        )
        model = create_extraction_model(reqs)
        assert model.model_fields["status"].default == "active"

    def test_int_default_as_numeric_string_coerced(self):
        reqs = _make_requirements(
            [
                FieldSpec(
                    field_name="count",
                    field_type="int",
                    description="c",
                    has_explicit_default=True,
                    default="0",
                )
            ]
        )
        model = create_extraction_model(reqs)
        info = model.model_fields["count"]
        assert info.default == 0
        assert isinstance(info.default, int)
        assert apply_field_policies({}, reqs)["count"] == 0

    def test_decimal_default_as_numeric_string_coerced(self):
        from decimal import Decimal

        reqs = _make_requirements(
            [
                FieldSpec(
                    field_name="price",
                    field_type="decimal",
                    description="p",
                    has_explicit_default=True,
                    default="9.99",
                )
            ]
        )
        model = create_extraction_model(reqs)
        assert model.model_fields["price"].default == Decimal("9.99")

    def test_bool_default_true_false_coerced(self):
        reqs = _make_requirements(
            [
                FieldSpec(
                    field_name="flag",
                    field_type="bool",
                    description="f",
                    has_explicit_default=True,
                    default="true",
                )
            ]
        )
        model = create_extraction_model(reqs)
        info = model.model_fields["flag"]
        assert info.default is True
        assert apply_field_policies({}, reqs)["flag"] is True


class TestInvalidNonEmptyDefaultDiscarded:
    """An unparsable non-empty explicit default must not corrupt the model."""

    def test_unparsable_int_default_falls_back_to_none(self):
        reqs = _make_requirements(
            [
                FieldSpec(
                    field_name="count",
                    field_type="int",
                    description="c",
                    has_explicit_default=True,
                    default="unknown",
                )
            ]
        )
        model = create_extraction_model(reqs)
        info = model.model_fields["count"]
        assert info.default is None
        obj = model()
        assert model.model_validate_json(obj.model_dump_json()).count is None

    def test_ambiguous_bool_default_falls_back_to_none(self):
        reqs = _make_requirements(
            [
                FieldSpec(
                    field_name="flag",
                    field_type="bool",
                    description="f",
                    has_explicit_default=True,
                    default="maybe",
                )
            ]
        )
        model = create_extraction_model(reqs)
        info = model.model_fields["flag"]
        assert info.default is None

    def test_scalar_default_never_becomes_list(self):
        reqs = _make_requirements(
            [
                FieldSpec(
                    field_name="tags",
                    field_type="list[str]",
                    description="t",
                    has_explicit_default=True,
                    default="a,b,c",
                )
            ]
        )
        model = create_extraction_model(reqs)
        info = model.model_fields["tags"]
        assert info.default_factory() == []
        assert model().tags == []


# ---------------------------------------------------------------------------
# Regression: non-finite numeric defaults (nan/inf/-inf, Decimal NaN/Infinity)
# parse without raising via float()/Decimal(), so they slipped past the
# ValueError/ArithmeticError guard and were accepted as usable defaults --
# the same round-trip defect class this whole fix targets. A NaN float
# silently serializes to JSON `null` (indistinguishable from "unset" and
# losing the original default value), and Decimal("NaN")/Infinity fail
# model_validate_json outright with "Input should be a finite number".
# ---------------------------------------------------------------------------


class TestNonFiniteNumericDefaultDiscarded:
    def test_float_nan_default_falls_back_to_none(self):
        reqs = _make_requirements(
            [
                FieldSpec(
                    field_name="ratio",
                    field_type="float",
                    description="r",
                    has_explicit_default=True,
                    default="nan",
                )
            ]
        )
        model = create_extraction_model(reqs)
        info = model.model_fields["ratio"]
        assert info.default is None
        obj = model()
        assert model.model_validate_json(obj.model_dump_json()).ratio is None

    def test_float_inf_default_falls_back_to_none(self):
        reqs = _make_requirements(
            [
                FieldSpec(
                    field_name="ratio",
                    field_type="float",
                    description="r",
                    has_explicit_default=True,
                    default="inf",
                )
            ]
        )
        model = create_extraction_model(reqs)
        assert model.model_fields["ratio"].default is None

    def test_float_negative_inf_default_falls_back_to_none(self):
        reqs = _make_requirements(
            [
                FieldSpec(
                    field_name="ratio",
                    field_type="float",
                    description="r",
                    has_explicit_default=True,
                    default="-inf",
                )
            ]
        )
        model = create_extraction_model(reqs)
        assert model.model_fields["ratio"].default is None

    def test_decimal_nan_default_falls_back_to_none(self):
        reqs = _make_requirements(
            [
                FieldSpec(
                    field_name="price",
                    field_type="decimal",
                    description="p",
                    has_explicit_default=True,
                    default="NaN",
                )
            ]
        )
        model = create_extraction_model(reqs)
        info = model.model_fields["price"]
        assert info.default is None
        obj = model()
        assert model.model_validate_json(obj.model_dump_json()).price is None

    def test_decimal_infinity_default_falls_back_to_none(self):
        reqs = _make_requirements(
            [
                FieldSpec(
                    field_name="price",
                    field_type="decimal",
                    description="p",
                    has_explicit_default=True,
                    default="Infinity",
                )
            ]
        )
        model = create_extraction_model(reqs)
        assert model.model_fields["price"].default is None

    def test_finite_float_default_still_honored(self):
        """The finiteness guard must not reject ordinary finite defaults."""
        reqs = _make_requirements(
            [
                FieldSpec(
                    field_name="ratio",
                    field_type="float",
                    description="r",
                    has_explicit_default=True,
                    default="0.5",
                )
            ]
        )
        model = create_extraction_model(reqs)
        assert model.model_fields["ratio"].default == 0.5


# ---------------------------------------------------------------------------
# Integration: Finnish construction site diary (työmaapäiväkirja) — the case
# that surfaced the bug. The task's closing instruction "leave unmentioned
# fields empty" was parsed into has_explicit_default=True, default='' across
# all 20 fields, including the int, list[str], and bool ones.
# ---------------------------------------------------------------------------


class TestFinnishConstructionSiteDiary:
    @pytest.fixture()
    def requirements(self):
        def f(name, ftype):
            return FieldSpec(
                field_name=name,
                field_type=ftype,
                description=name,
                has_explicit_default=True,
                default="",
            )

        str_fields = [
            "kohde",
            "laatija",
            "saa",
            "paivamaara",
            "resurssit_henkilosto",
            "paivan_tapahtumat",
            "valvojan_huomiot",
            "paivan_poikkeamat",
            "pyydetyt_lisaajat",
            "valvojan_huomautukset",
        ]
        list_fields = [
            "paivan_tyot",
            "liitteet",
            "aloitetut_tyovaiheet",
            "kaynnissa_olevat_tyovai",
            "paattyneet_tyovai",
            "keskeytyneet_tyovai",
            "tehdyt_katselmukset",
        ]
        bool_fields = ["valvojan_allekirjoitus", "vastaavan_allekirjoitus"]

        fields = (
            [f(n, "str") for n in str_fields]
            + [f("tyoviikko", "int")]
            + [f(n, "list[str]") for n in list_fields]
            + [f(n, "bool") for n in bool_fields]
        )
        return _make_requirements(fields)

    def test_field_count(self, requirements):
        model = create_extraction_model(requirements)
        assert len(model.model_fields) == 20

    def test_tyoviikko_is_nullable_int_not_empty_string(self, requirements):
        model = create_extraction_model(requirements)
        info = model.model_fields["tyoviikko"]
        assert info.default is None
        assert not info.is_required()

    def test_list_fields_default_to_empty_list(self, requirements):
        model = create_extraction_model(requirements)
        for name in (
            "paivan_tyot",
            "liitteet",
            "aloitetut_tyovaiheet",
            "kaynnissa_olevat_tyovai",
            "paattyneet_tyovai",
            "keskeytyneet_tyovai",
            "tehdyt_katselmukset",
        ):
            info = model.model_fields[name]
            assert info.default_factory is not None
            assert info.default_factory() == [], f"{name} should default to []"

    def test_bool_fields_default_to_none(self, requirements):
        model = create_extraction_model(requirements)
        for name in ("valvojan_allekirjoitus", "vastaavan_allekirjoitus"):
            info = model.model_fields[name]
            assert info.default is None, f"{name} should default to None"

    def test_str_fields_default_to_empty_string(self, requirements):
        model = create_extraction_model(requirements)
        info = model.model_fields["kohde"]
        assert info.default == ""

    def test_model_round_trips_through_json(self, requirements):
        """The original bug: Pydantic doesn't validate defaults by default,
        so the broken model built without crashing -- it only failed on
        model_validate_json of its own serialized defaults."""
        model = create_extraction_model(requirements)
        obj = model()
        dumped = obj.model_dump_json()
        revalidated = model.model_validate_json(dumped)
        assert revalidated.tyoviikko is None
        assert revalidated.paivan_tyot == []
        assert revalidated.valvojan_allekirjoitus is None

    def test_apply_field_policies_matches_model_defaults(self, requirements):
        """Missing-key post-processing must agree with the model's own defaults."""
        result = apply_field_policies({}, requirements)
        assert result["tyoviikko"] is None
        assert result["paivan_tyot"] == []
        assert result["valvojan_allekirjoitus"] is None
        assert result["kohde"] == ""


# ---------------------------------------------------------------------------
# Test 9: Finnish incident report — 13-field integration
# ---------------------------------------------------------------------------


class TestFinnishIncidentReport:
    @pytest.fixture()
    def requirements(self):
        return _make_requirements(
            [
                FieldSpec(
                    field_name="raportin_tyyppi",
                    field_type="str",
                    description="Report type",
                    enum=["turvallisuus", "ympäristö", "laatu"],
                    has_explicit_default=True,
                    default="turvallisuus",
                ),
                FieldSpec(
                    field_name="tarkkailijan_organisaatio",
                    field_type="str",
                    description="Observer organization",
                    enum=["Skanska", "NCC", "YIT", "Fira", "Peab"],
                    nullable=True,
                ),
                FieldSpec(
                    field_name="tarkkailija_on_kesatyontekija",
                    field_type="str",
                    description="Observer is summer worker",
                    enum=["Kyllä", "Ei"],
                    has_explicit_default=True,
                    default="Ei",
                ),
                FieldSpec(
                    field_name="lahella_piti_tilanne",
                    field_type="str",
                    description="Near miss",
                    enum=["Kyllä", "Ei"],
                    has_explicit_default=True,
                    default="Ei",
                ),
                FieldSpec(
                    field_name="paivamaara",
                    field_type="str",
                    description="Date",
                    has_explicit_default=True,
                    default="",
                ),
                FieldSpec(
                    field_name="kellonaika",
                    field_type="str",
                    description="Time",
                    has_explicit_default=True,
                    default="",
                ),
                FieldSpec(
                    field_name="rakennus",
                    field_type="str",
                    description="Building",
                    enum=[
                        "Talo A1",
                        "Talo A2",
                        "Talo B1",
                        "Talo B2",
                        "Talo C1",
                        "Talo C2",
                        "Talo D1",
                        "Talo D2",
                        "Talo E1",
                        "Talo E2",
                        "Talo F1",
                        "Talo F2",
                        "Piha-alue",
                        "Pysäköintialue",
                        "Kellari",
                        "Katto",
                    ],
                ),
                FieldSpec(
                    field_name="tarkkailijan_nimi",
                    field_type="str",
                    description="Observer name",
                ),
                FieldSpec(
                    field_name="tapahtumapaikan_tarkenne",
                    field_type="str",
                    description="Location detail",
                ),
                FieldSpec(
                    field_name="mita_tapahtui",
                    field_type="str",
                    description="What happened",
                ),
                FieldSpec(
                    field_name="mahdolliset_seuraukset",
                    field_type="str",
                    description="Possible consequences",
                ),
                FieldSpec(
                    field_name="toteutetut_toimenpiteet",
                    field_type="str",
                    description="Actions taken",
                ),
                FieldSpec(
                    field_name="ehdotus",
                    field_type="str",
                    description="Suggestion",
                ),
            ]
        )

    def test_field_count(self, requirements):
        model = create_extraction_model(requirements)
        assert len(model.model_fields) == 13

    def test_raportin_tyyppi(self, requirements):
        model = create_extraction_model(requirements)
        info = model.model_fields["raportin_tyyppi"]
        assert not info.is_required()
        assert info.default == "turvallisuus"

    def test_tarkkailijan_organisaatio_nullable(self, requirements):
        model = create_extraction_model(requirements)
        info = model.model_fields["tarkkailijan_organisaatio"]
        assert not info.is_required()
        assert info.default is None

    def test_boolean_enums_default_ei(self, requirements):
        model = create_extraction_model(requirements)
        for name in ("tarkkailija_on_kesatyontekija", "lahella_piti_tilanne"):
            info = model.model_fields[name]
            assert info.default == "Ei", f"{name} should default to 'Ei'"

    def test_paivamaara_kellonaika_default_empty(self, requirements):
        model = create_extraction_model(requirements)
        for name in ("paivamaara", "kellonaika"):
            info = model.model_fields[name]
            assert info.default == "", f"{name} should default to ''"

    def test_rakennus_enum_with_empty(self, requirements):
        model = create_extraction_model(requirements)
        info = model.model_fields["rakennus"]
        assert not info.is_required()
        assert info.default == ""

    def test_required_str_fields(self, requirements):
        model = create_extraction_model(requirements)
        for name in (
            "tarkkailijan_nimi",
            "tapahtumapaikan_tarkenne",
            "mita_tapahtui",
            "mahdolliset_seuraukset",
            "toteutetut_toimenpiteet",
            "ehdotus",
        ):
            info = model.model_fields[name]
            assert info.is_required(), f"{name} should be required"

    def test_policy_fixes_null_in_required_str(self, requirements):
        data = {
            "raportin_tyyppi": "turvallisuus",
            "tarkkailijan_organisaatio": None,
            "tarkkailija_on_kesatyontekija": "Ei",
            "lahella_piti_tilanne": "Kyllä",
            "paivamaara": "2025-05-01",
            "kellonaika": None,
            "rakennus": "Talo A1",
            "tarkkailijan_nimi": "Matti",
            "tapahtumapaikan_tarkenne": None,
            "mita_tapahtui": "Putosi tiili",
            "mahdolliset_seuraukset": None,
            "toteutetut_toimenpiteet": "Alue eristetty",
            "ehdotus": None,
        }
        result = apply_field_policies(data, requirements)
        assert result["tarkkailijan_organisaatio"] is None
        assert result["kellonaika"] == ""
        assert result["tapahtumapaikan_tarkenne"] == ""
        assert result["mahdolliset_seuraukset"] == ""
        assert result["ehdotus"] == ""


# ---------------------------------------------------------------------------
# Composite (parent_with_nested_list) post-processing
# ---------------------------------------------------------------------------


class TestCompositeFieldPolicies:
    """A CompositeExtractionRequirements has no ``.fields``; the parent and each
    child collection carry their own specs and must be policed separately."""

    @pytest.fixture
    def composite(self):
        parent = _make_requirements(
            [
                FieldSpec(field_name="meeting_id", field_type="str", description="id"),
                FieldSpec(field_name="meeting_date", field_type="date", description="date"),
                FieldSpec(
                    field_name="review_status",
                    field_type="str",
                    description="status",
                    enum=["ok", "blocked"],
                ),
            ]
        )
        topics = _make_requirements(
            [
                FieldSpec(field_name="title", field_type="str", description="title"),
                FieldSpec(field_name="tags", field_type="list[str]", description="tags"),
            ]
        )
        decisions = _make_requirements(
            [FieldSpec(field_name="what", field_type="str", description="what")]
        )
        return CompositeExtractionRequirements(
            parent_requirements=parent,
            children=[
                ChildRequirements(
                    container_name="topics", container_description="t", requirements=topics
                ),
                ChildRequirements(
                    container_name="decisions", container_description="d", requirements=decisions
                ),
            ],
        )

    @pytest.fixture
    def record(self):
        return {
            "meeting_id": "M-1",
            "meeting_date": "2026-08-11",
            "review_status": "not-a-valid-status",
            "topics": [{"title": "Budget", "tags": "cost, q3"}, {"title": None}],
            "decisions": [{"what": "ship it"}],
        }

    def test_parent_fields_do_not_leak_into_children(self, composite, record):
        result = apply_composite_field_policies(record, composite)
        for item in result["topics"] + result["decisions"]:
            assert "meeting_id" not in item
            assert "meeting_date" not in item
            assert "review_status" not in item

    def test_parent_policies_still_apply(self, composite, record):
        result = apply_composite_field_policies(record, composite)
        assert result["meeting_id"] == "M-1"
        assert result["review_status"] == ""  # out-of-enum -> fallback

    def test_child_policies_apply_per_container(self, composite, record):
        result = apply_composite_field_policies(record, composite)
        assert result["topics"][1]["title"] == ""  # missing required str -> ""
        assert result["topics"][1]["tags"] == []  # missing required list -> []
        assert result["decisions"][0] == {"what": "ship it"}

    def test_normalization_runs_on_child_items(self, composite, record):
        result = normalize_composite_extracted_data(
            apply_composite_field_policies(record, composite), composite
        )
        assert result["topics"][0]["tags"] == ["cost", "q3"]

    def test_unknown_keys_pass_through(self, composite, record):
        result = apply_composite_field_policies({**record, "extra": 42}, composite)
        assert result["extra"] == 42

    def test_extractor_dispatches_composite(self, composite, record):
        """_extract_one must route composite requirements away from the flat path."""
        extractor = DataExtractor.__new__(DataExtractor)
        extractor.client = object()
        extractor.model = "test-model"
        extractor.temperature = 0.0
        extractor.reasoning_effort = None
        parsed = type("P", (), {"model_dump": lambda self: dict(record)})()
        resp = type(
            "R",
            (),
            {
                "choices": [type("C", (), {"message": type("M", (), {"parsed": parsed})()})()],
                "usage": None,
            },
        )()
        with mock.patch(
            "gaik.software_components.extractor.extractor._parse_with", return_value=resp
        ):
            result, _ = extractor._extract_one(
                doc="d", extraction_model=object, requirements=composite, user_requirements="u"
            )
        assert "meeting_id" not in result["topics"][0]
        assert result["topics"][0]["tags"] == ["cost", "q3"]
