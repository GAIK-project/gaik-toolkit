"""A generated schema is compared with the approved one before it replaces it."""

from __future__ import annotations

from gaik.software_components.extractor import (
    ChildRequirements,
    CompositeExtractionRequirements,
    ExtractionRequirements,
    FieldSpec,
    SchemaGenerationResult,
    SchemaGenerator,
    compare_requirements,
)


def _field(name, field_type="str", **kwargs):
    kwargs.setdefault("description", f"The {name}")
    return FieldSpec(field_name=name, field_type=field_type, **kwargs)


def _reqs(*fields):
    return ExtractionRequirements(use_case_name="invoice", fields=list(fields))


APPROVED = _reqs(_field("invoice_number"), _field("amount", "decimal"), _field("due_date", "date"))


def test_the_same_schema_has_no_changes():
    diff = compare_requirements(APPROVED, APPROVED.model_copy(deep=True))

    assert diff.is_empty
    assert str(diff).startswith("No changes to the approved schema.")


def test_a_dropped_an_added_and_a_changed_field_are_named():
    new = _reqs(
        _field("invoice_number"),
        _field("amount", "str"),
        _field("vat_number"),
    )

    diff = compare_requirements(APPROVED, new)

    assert diff.removed == ["due_date"]
    assert diff.added == ["vat_number"]
    ((change),) = diff.changed
    assert change.field_name == "amount"
    assert change.changes == {"field_type": ("decimal", "str")}
    assert "- due_date" in str(diff) and "+ vat_number" in str(diff)
    assert "~ amount (field_type: 'decimal' -> 'str')" in str(diff)


def test_policy_and_enum_changes_count_and_wording_is_apart():
    new = _reqs(
        _field("invoice_number", nullable=True),
        _field("amount", "decimal", description="Total"),
        _field("due_date", "date", enum=["x"]),
    )

    diff = compare_requirements(APPROVED, new)

    by_name = {c.field_name: c.changes for c in diff.changed}
    assert "nullable" in by_name["invoice_number"]
    assert by_name["due_date"]["enum"] == (None, ["x"])
    assert "amount" not in by_name  # only reworded
    assert [c.field_name for c in diff.wording] == ["amount"]
    assert "reworded: amount" in str(diff)


def test_a_reworded_description_alone_leaves_the_diff_empty():
    new = _reqs(
        _field("invoice_number", description="Invoice id"),
        _field("amount", "decimal"),
        _field("due_date", "date"),
    )

    diff = compare_requirements(APPROVED, new)

    assert diff.is_empty
    assert [c.field_name for c in diff.wording] == ["invoice_number"]


def test_a_switched_off_explicit_default_is_a_change():
    approved = _reqs(_field("currency", has_explicit_default=True, default="EUR"))
    new = _reqs(_field("currency", has_explicit_default=False, default="EUR"))

    diff = compare_requirements(approved, new)

    assert [(c.field_name, c.changes) for c in diff.changed] == [
        ("currency", {"default": ("EUR", None)})
    ]


def test_an_unused_empty_default_and_enum_order_are_no_change():
    approved = _reqs(_field("count", "int", default=""), _field("kind", enum=["a", "b"]))
    new = _reqs(_field("count", "int", default=None), _field("kind", enum=["b", "a"]))

    assert compare_requirements(approved, new).is_empty


def test_a_flat_to_nested_list_change_shows_when_the_structures_are_given():
    diff = compare_requirements(
        APPROVED, APPROVED, approved_structure="flat", new_structure="nested_list"
    )

    assert not diff.is_empty
    assert diff.structure == ("flat", "nested_list")
    assert "! structure: flat -> nested_list" in str(diff)


def test_without_the_structures_the_diff_says_it_cannot_tell():
    diff = compare_requirements(APPROVED, APPROVED)

    assert diff.is_empty and diff.structure is None
    assert any("structure" in note for note in diff.notes)


def test_saved_requirements_dicts_are_read_and_other_types_refused():
    import pytest

    diff = compare_requirements(APPROVED.model_dump(), APPROVED)
    assert diff.is_empty

    with pytest.raises(TypeError, match="approved"):
        compare_requirements(["invoice_number"], APPROVED)


def _composite(children):
    return CompositeExtractionRequirements(
        parent_requirements=_reqs(_field("order_number")),
        children=[
            ChildRequirements(
                container_name=name,
                container_description=description,
                requirements=ExtractionRequirements(use_case_name=name, fields=list(fields)),
            )
            for name, description, fields in children
        ],
    )


def test_nested_fields_are_compared_by_container():
    approved = _composite(
        [
            ("items", "Order lines", [_field("sku"), _field("qty", "int")]),
            ("notes", "Notes", [_field("sku")]),
        ]
    )
    new = _composite(
        [("items", "Order lines", [_field("sku")]), ("notes", "Notes", [_field("sku", "int")])]
    )

    diff = compare_requirements(approved, new)

    assert diff.removed == ["items.qty"]
    # the same field name in two containers is told apart
    assert [(c.field_name, c.changes) for c in diff.changed] == [
        ("notes.sku", {"field_type": ("str", "int")})
    ]


def test_a_container_rename_and_a_changed_container_description_are_shown():
    approved = _composite([("items", "Order lines", [_field("sku")])])
    renamed = _composite([("lines", "Order lines", [_field("sku")])])
    redescribed = _composite([("items", "Shipping notes", [_field("sku")])])

    diff = compare_requirements(approved, renamed)
    assert "items[]" in diff.removed and "lines[]" in diff.added

    diff = compare_requirements(approved, redescribed)
    assert [(c.field_name, c.changes) for c in diff.changed] == [
        ("items[]", {"container_description": ("Order lines", "Shipping notes")})
    ]


def test_generate_schema_with_usage_reports_the_diff(monkeypatch):
    new = _reqs(_field("invoice_number"), _field("amount", "decimal"))
    generator = SchemaGenerator.__new__(SchemaGenerator)
    generator.model = "m"
    generator.item_requirements = None
    generator.structure_analysis = None

    def inner(self, text):
        self.item_requirements = new
        self.extraction_model = object
        return object, None, 0.1

    monkeypatch.setattr(SchemaGenerator, "_generate_schema_inner", inner)
    monkeypatch.setattr(
        "gaik.software_components.extractor.schema.print_pydantic_schema", lambda *a, **k: None
    )

    with_diff = generator.generate_schema_with_usage("x", approved_requirements=APPROVED)
    without = generator.generate_schema_with_usage("x")

    assert isinstance(with_diff, SchemaGenerationResult)
    assert with_diff.diff is not None and with_diff.diff.removed == ["due_date"]
    assert without.diff is None


def test_a_wrong_approved_type_fails_before_any_model_call(monkeypatch):
    import pytest

    generator = SchemaGenerator.__new__(SchemaGenerator)
    calls = []
    monkeypatch.setattr(SchemaGenerator, "_generate_schema_inner", lambda self, t: calls.append(t))

    with pytest.raises(TypeError, match="approved_requirements"):
        generator.generate_schema_with_usage("x", approved_requirements="invoice_number")
    assert calls == []
