"""Unit tests for field policy logic — no LLM calls required."""

import pytest
from gaik.software_components.extractor.schema import (
    ExtractionRequirements,
    FieldSpec,
    apply_field_policies,
    create_extraction_model,
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
