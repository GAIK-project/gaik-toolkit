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


def _cmp(approved, new, **kwargs):
    """compare_requirements for two flat schemas whose structure is known."""
    kwargs.setdefault("approved_structure", "flat")
    kwargs.setdefault("new_structure", "flat")
    return compare_requirements(approved, new, **kwargs)


APPROVED = _reqs(_field("invoice_number"), _field("amount", "decimal"), _field("due_date", "date"))


def test_the_same_schema_has_no_changes():
    diff = _cmp(APPROVED, APPROVED.model_copy(deep=True))

    assert diff.is_empty
    assert str(diff).startswith("No changes to the approved schema.")


def test_a_dropped_an_added_and_a_changed_field_are_named():
    new = _reqs(
        _field("invoice_number"),
        _field("amount", "str"),
        _field("vat_number"),
    )

    diff = _cmp(APPROVED, new)

    assert diff.removed == ["due_date"]
    assert diff.added == ["vat_number"]
    ((change),) = diff.changed
    assert change.field_name == "amount"
    assert change.changes == {"field_type": ("decimal", "str")}
    assert "- 'due_date'" in str(diff) and "+ 'vat_number'" in str(diff)
    assert "~ 'amount' (field_type: 'decimal' -> 'str')" in str(diff)


def test_policy_and_enum_changes_count_and_wording_is_apart():
    new = _reqs(
        _field("invoice_number", nullable=True),
        _field("amount", "decimal", description="Total"),
        _field("due_date", "date", enum=["x"]),
    )

    diff = _cmp(APPROVED, new)

    by_name = {c.field_name: c.changes for c in diff.changed}
    assert "nullable" in by_name["invoice_number"]
    assert by_name["due_date"]["enum"] == (None, ["x"])
    assert "amount" not in by_name  # only reworded
    assert [c.field_name for c in diff.wording] == ["amount"]
    assert "~ 'amount' (description: 'The amount' -> 'Total')" in str(diff)


def test_a_reworded_description_is_shown_with_both_texts_and_is_not_empty():
    # the description is what the extraction model reads: "net" becoming "gross" matters
    approved = _reqs(_field("amount", "decimal", description="Net amount excl. VAT"))
    new = _reqs(_field("amount", "decimal", description="Gross amount incl. VAT"))

    diff = _cmp(approved, new)

    assert not diff.is_empty and not diff.changes_output
    assert "No changes" not in str(diff)
    assert "'Net amount excl. VAT' -> 'Gross amount incl. VAT'" in str(diff)


def test_a_switched_off_explicit_default_is_a_change():
    approved = _reqs(_field("currency", has_explicit_default=True, default="EUR"))
    new = _reqs(_field("currency", has_explicit_default=False, default="EUR"))

    diff = _cmp(approved, new)

    assert [(c.field_name, c.changes) for c in diff.changed] == [
        ("currency", {"default": ("EUR", None)})
    ]


def test_an_unused_empty_default_and_enum_order_are_no_change():
    approved = _reqs(_field("count", "int", default=""), _field("kind", enum=["a", "b"]))
    new = _reqs(_field("count", "int", default=None), _field("kind", enum=["b", "a"]))

    assert _cmp(approved, new).is_empty


def test_a_flat_to_nested_list_change_shows_when_the_structures_are_given():
    diff = compare_requirements(
        APPROVED, APPROVED, approved_structure="flat", new_structure="nested_list"
    )

    assert not diff.is_empty
    assert diff.structure == ("flat", "nested_list")
    assert "! structure: 'flat' -> 'nested_list'" in str(diff)


def test_without_the_structures_the_diff_says_it_cannot_tell():
    diff = compare_requirements(APPROVED, APPROVED)

    # unknown is not "no change": the diff is not empty and says why
    assert not diff.is_empty and diff.structure is None
    assert any("structure" in note for note in diff.notes)
    assert "No changes" not in str(diff)


def test_saved_requirements_dicts_are_read_and_other_types_refused():
    import pytest

    diff = _cmp(APPROVED.model_dump(), APPROVED)
    assert diff.is_empty

    with pytest.raises(TypeError, match="approved"):
        _cmp(["invoice_number"], APPROVED)


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

    diff = _cmp(approved, new)

    assert diff.removed == ["items.qty"]
    # the same field name in two containers is told apart
    assert [(c.field_name, c.changes) for c in diff.changed] == [
        ("notes.sku", {"field_type": ("str", "int")})
    ]


def test_a_container_rename_and_a_changed_container_description_are_shown():
    approved = _composite([("items", "Order lines", [_field("sku")])])
    renamed = _composite([("lines", "Order lines", [_field("sku")])])
    redescribed = _composite([("items", "Shipping notes", [_field("sku")])])

    diff = _cmp(approved, renamed)
    assert "items[]" in diff.removed and "lines[]" in diff.added

    diff = _cmp(approved, redescribed)
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


def _nested(container="items", description="d"):
    from gaik.software_components.extractor import StructureAnalysis

    return StructureAnalysis(
        structure_type="nested_list",
        parent_container_name=container,
        parent_description=description,
        item_description="d",
        reasoning="r",
    )


def test_a_container_named_on_one_side_only_leaves_a_note_and_is_not_empty():
    diff = compare_requirements(
        APPROVED, APPROVED, approved_structure="nested_list", new_structure=_nested("line_items")
    )

    assert diff.structure is None
    assert not diff.is_empty
    assert any("container" in note for note in diff.notes)
    assert "No changes to the approved schema" not in str(diff)


def test_a_renamed_nested_list_container_is_a_structure_change():
    diff = compare_requirements(
        APPROVED,
        APPROVED,
        approved_structure=_nested("records"),
        new_structure=_nested("line_items"),
    )

    assert diff.structure == ("nested_list in records", "nested_list in line_items")
    assert diff.changes_output


def test_a_saved_structure_dict_is_read_like_the_analysis():
    saved = _nested("records").model_dump()

    renamed = compare_requirements(
        APPROVED, APPROVED, approved_structure=saved, new_structure=_nested("line_items")
    )
    same = compare_requirements(
        APPROVED, APPROVED, approved_structure=saved, new_structure=_nested("records")
    )

    assert renamed.structure == ("nested_list in records", "nested_list in line_items")
    assert same.is_empty
    assert saved["parent_container_name"] == "records"


def test_a_reworded_nested_list_container_description_is_a_change():
    diff = compare_requirements(
        APPROVED,
        APPROVED,
        approved_structure=_nested("items", "Order lines"),
        new_structure=_nested("items", "Shipping notes"),
    )

    assert [(c.field_name, c.changes) for c in diff.changed] == [
        ("items[]", {"container_description": ("Order lines", "Shipping notes")})
    ]


def test_a_wrong_approved_structure_fails_before_any_model_call(monkeypatch):
    import pytest

    generator = SchemaGenerator.__new__(SchemaGenerator)
    calls = []
    monkeypatch.setattr(SchemaGenerator, "_generate_schema_inner", lambda self, t: calls.append(t))

    for wrong in ("nested", {"structure_type": "nested_list"}, 3):
        with pytest.raises(ValueError, match="approved_structure"):
            generator.generate_schema_with_usage(
                "x", approved_requirements=APPROVED, approved_structure=wrong
            )
    assert calls == []


def test_generate_schema_with_usage_reads_a_saved_structure_dict(monkeypatch):
    generator = SchemaGenerator.__new__(SchemaGenerator)
    generator.model = "m"

    def inner(self, text):
        self.item_requirements = APPROVED
        self.structure_analysis = _nested("line_items")
        self.extraction_model = object
        return object, None, 0.1

    monkeypatch.setattr(SchemaGenerator, "_generate_schema_inner", inner)
    monkeypatch.setattr(
        "gaik.software_components.extractor.schema.print_pydantic_schema", lambda *a, **k: None
    )

    result = generator.generate_schema_with_usage(
        "x",
        approved_requirements=APPROVED.model_dump(),
        approved_structure=_nested("records").model_dump(),
    )

    assert result.diff.structure == ("nested_list in records", "nested_list in line_items")


def test_an_unknown_structure_string_is_refused():
    import pytest

    with pytest.raises(ValueError, match="structure"):
        compare_requirements(APPROVED, APPROVED, approved_structure="Flat\nNo changes")


def test_names_and_long_values_cannot_forge_or_flood_the_diff():
    approved = CompositeExtractionRequirements(
        parent_requirements=_reqs(_field("order_number")),
        children=[
            ChildRequirements(
                container_name="items\nNo changes to the approved schema.\x1b[2J",
                container_description="x",
                requirements=ExtractionRequirements(use_case_name="i", fields=[_field("sku")]),
            )
        ],
    )
    new = _reqs(_field("order_number", pattern="a" * 100_000))

    text = str(compare_requirements(approved, new))

    assert "\x1b" not in text  # escaped, not a terminal code
    assert all(not line.startswith("No changes") for line in text.splitlines())
    assert max(len(line) for line in text.splitlines()) < 600


def test_a_saved_dict_is_not_changed_by_the_comparison():
    saved = APPROVED.model_dump()
    for field in saved["fields"]:
        field.pop("nullable", None)
    before = repr(saved)

    _cmp(saved, APPROVED)

    assert repr(saved) == before
