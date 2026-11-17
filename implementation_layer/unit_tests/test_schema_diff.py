"""A generated schema is compared with the approved one before it replaces it (G8)."""

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
    assert str(diff) == "No changes to the approved schema."


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


def test_policy_enum_and_description_changes_count():
    new = _reqs(
        _field("invoice_number", nullable=True),
        _field("amount", "decimal", description="Total"),
        _field("due_date", "date", enum=["x"]),
    )

    diff = compare_requirements(APPROVED, new)

    by_name = {c.field_name: c.changes for c in diff.changed}
    assert "nullable" in by_name["invoice_number"]
    assert "description" in by_name["amount"]
    assert by_name["due_date"]["enum"] == (None, ["x"])


def test_nested_fields_are_compared_by_container():
    def composite(child_fields):
        return CompositeExtractionRequirements(
            parent_requirements=_reqs(_field("order_number")),
            children=[
                ChildRequirements(
                    container_name="items",
                    container_description="Order lines",
                    requirements=ExtractionRequirements(
                        use_case_name="items", fields=list(child_fields)
                    ),
                )
            ],
        )

    diff = compare_requirements(
        composite([_field("sku"), _field("qty", "int")]), composite([_field("sku")])
    )

    assert diff.removed == ["items.qty"]
    assert diff.added == [] and diff.changed == []


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
