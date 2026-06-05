"""
Tests for schema generator improvements: nested_list and parent_with_nested_list.

Verifies that all three structure types produce correct field types when the task
contains explicit representation instructions (text string, Choose from, else null).

Requires a valid API key (Azure OpenAI or OpenAI) in the environment.
Run with:  pytest unit_tests/test_schema_nested.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import get_args, get_origin

import pytest
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gaik.software_components.extractor.schema import parse_nested_requirements

# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------


def _field_map(model: type[BaseModel]) -> dict:
    """Return {field_name: FieldInfo} for a Pydantic model."""
    return model.model_fields


def _is_optional(annotation) -> bool:
    """True if annotation is X | None or Optional[X]."""
    origin = get_origin(annotation)
    if origin is type(None):
        return True
    args = get_args(annotation)
    return type(None) in args


def _inner_type(annotation):
    """Return the non-None type from an Optional[X] annotation."""
    for arg in get_args(annotation):
        if arg is not type(None):
            return arg
    return annotation


# ---------------------------------------------------------------------------
# Task 1 (provided) — parent_with_nested_list, English PO task with rich qualifiers
# ---------------------------------------------------------------------------

TASK_PO_PARENT_NESTED = """
Extract purchase order data from the document.

Top-level fields:
- Purchase order number
- Delivery date (format: DD-MM-YYYY)
- Delivery_address (Format: company name + street + postal code + city + country)
- Vendor number

For each line item, extract:
- Item number (e.g. 0100, 0200)
- Article code (internal supplier code)
- Dimensions (cross-section as stated, e.g. "25x8mm")
- Product form (Choose from: Flat, round, or rectangular bar)
- Material grade (e.g. "6061 Aluminum", "316 Stainless", "C260 Brass")
- Standard designation (alloy/standard code, e.g. "CW024A", "ASTM B221")
- Cut length (text string including the unit, e.g. "2000mm")
- Temper or condition (e.g. "Cold drawn, bright finish", "T6")
- Hardness HV (numeric, if stated, else null)
- Min bend radius (numeric, if stated, else null)
- Delivery length note (e.g. "in lengths of 3000mm", if stated, else null)
- Applicable standard (e.g. "ASTM B221", "EN 755-2", if stated, else null)
- Special flags (any remaining codes, e.g. "XK", "chamfered edges", else null)
- Quantity (text string including the unit, e.g. "4.200 kg")
"""

# ---------------------------------------------------------------------------
# Task 2 (provided) — nested_list, simple PO line items
# ---------------------------------------------------------------------------

TASK_PO_NESTED_LIST = """
For each line item in the purchase order, extract these scalar fields:
- item number (e.g., 0100, 0200)
- complete description
- quantity (text string with the unit, e.g., "400 kg")
- price (text string with the currency symbol, e.g., "400 USD")
- material number
"""

# ---------------------------------------------------------------------------
# Task 3 (provided) — flat, Finnish incident report
# ---------------------------------------------------------------------------

TASK_INCIDENT_FLAT = """
TEHTÄVÄ:
Poimi seuraavat kentät tapahtumaraportista.

POIMITTAVAT KENTÄT:

- Raportin tyyppi
  Valitse VAIN YKSI seuraavista:
  - "turvallisuus"
  - "ympäristösuojelu"
  - "energiatehokkuus"
  Jos tyyppiä ei voida päätellä, palauta "turvallisuus".

- Tarkkailijan nimi
  Henkilön koko nimi. Jos ei mainittu, palauta "".

- Päivämäärä
  Tapahtuman päivämäärä täsmälleen siinä muodossa kuin se on kirjoitettu lähteessä.
  Jos ei mainittu, palauta "".

- Mitä tapahtui
  Yksi lause, enintään 12 sanaa. Jos ei mainittu, palauta "".

- Lähellä piti tilanne
  Palauta "Kyllä" tai "Ei".

- Ehdotus
  Lähteessä suoraan ilmaistu jatkotoimenpide. Jos ei mainittu, palauta "".
"""

# ---------------------------------------------------------------------------
# Task 4 (custom) — nested_list, medical lab results
# ---------------------------------------------------------------------------

TASK_LAB_NESTED_LIST = """
For each test result in the lab report, extract:
- test name
- measured value (text string including the unit, e.g. "5.2 mmol/L")
- reference range (text string as stated, e.g. "3.5-5.0 mmol/L")
- status (Choose from: Normal, High, Low, Critical)
- flag (any abnormality note, if stated, else null)
"""

# ---------------------------------------------------------------------------
# Task 5 (custom) — parent_with_nested_list, invoice with line items
# ---------------------------------------------------------------------------

TASK_INVOICE_PARENT_NESTED = """
Extract invoice data.

Header fields:
- Invoice number
- Invoice date (format: DD-MM-YYYY)
- Vendor name
- Payment terms (e.g. "Net 30", if stated, else null)
- Currency (Choose from: USD, EUR, GBP)

For each line item, extract:
- Line number
- Product description
- Unit price (text string with the currency symbol, e.g. "12.50 USD")
- Quantity (numeric)
- Discount percentage (numeric, if stated, else null)
"""

# ---------------------------------------------------------------------------
# Task 6 (custom) — flat, employee record
# ---------------------------------------------------------------------------

TASK_EMPLOYEE_FLAT = """
Extract the following fields from an employee profile.

- Full name
- Employee ID (text string, e.g. "EMP-1042")
- Department (Choose from: Engineering, Sales, HR, Finance, Operations)
- Start date (format: YYYY-MM-DD)
- Employment type (Choose from: Full-time, Part-time, Contractor)
- Annual salary (text string with the currency symbol, e.g. "65000 USD")
- Manager name (if stated, else null)
"""


# ===========================================================================
# Tests — parent_with_nested_list
# ===========================================================================


class TestParentWithNestedListPO:
    """Task 1: English PO with rich type qualifiers."""

    @pytest.fixture(scope="class")
    def schema(self):
        model, requirements, analysis = parse_nested_requirements(TASK_PO_PARENT_NESTED)
        return model, requirements, analysis

    def test_structure_type(self, schema):
        _, _, analysis = schema
        assert analysis.structure_type == "parent_with_nested_list"

    def test_parent_has_no_list_dict(self, schema):
        _, requirements, _ = schema
        from gaik.software_components.extractor.schema import CompositeExtractionRequirements

        assert isinstance(requirements, CompositeExtractionRequirements)
        bad = [
            f.field_name
            for f in requirements.parent_requirements.fields
            if f.field_type == "list[dict]"
        ]
        assert bad == [], f"Parent has list[dict] fields: {bad}"

    def test_child_has_no_list_dict(self, schema):
        _, requirements, _ = schema
        from gaik.software_components.extractor.schema import CompositeExtractionRequirements

        assert isinstance(requirements, CompositeExtractionRequirements)
        bad = [
            f.field_name
            for f in requirements.child_requirements.fields
            if f.field_type == "list[dict]"
        ]
        assert bad == [], f"Child has list[dict] fields: {bad}"

    def test_parent_fields_are_header_only(self, schema):
        _, requirements, _ = schema
        from gaik.software_components.extractor.schema import CompositeExtractionRequirements

        parent_names = {f.field_name for f in requirements.parent_requirements.fields}
        # Must not contain child/item fields
        assert "cut_length" not in parent_names
        assert "quantity" not in parent_names
        assert "item_number" not in parent_names

    def test_child_fields_do_not_include_parent_fields(self, schema):
        _, requirements, _ = schema
        from gaik.software_components.extractor.schema import CompositeExtractionRequirements

        child_names = {f.field_name for f in requirements.child_requirements.fields}
        assert "purchase_order_number" not in child_names
        assert "delivery_date" not in child_names
        assert "vendor_number" not in child_names

    def test_cut_length_is_str(self, schema):
        _, requirements, _ = schema
        from gaik.software_components.extractor.schema import CompositeExtractionRequirements

        child_fields = {f.field_name: f for f in requirements.child_requirements.fields}
        assert "cut_length" in child_fields, "cut_length field missing"
        assert child_fields["cut_length"].field_type == "str", (
            f"cut_length should be str, got {child_fields['cut_length'].field_type}"
        )

    def test_quantity_is_str(self, schema):
        _, requirements, _ = schema
        from gaik.software_components.extractor.schema import CompositeExtractionRequirements

        child_fields = {f.field_name: f for f in requirements.child_requirements.fields}
        assert "quantity" in child_fields, "quantity field missing"
        assert child_fields["quantity"].field_type == "str", (
            f"quantity should be str, got {child_fields['quantity'].field_type}"
        )

    def test_product_form_has_enum(self, schema):
        _, requirements, _ = schema
        from gaik.software_components.extractor.schema import CompositeExtractionRequirements

        child_fields = {f.field_name: f for f in requirements.child_requirements.fields}
        assert "product_form" in child_fields, "product_form field missing"
        assert child_fields["product_form"].enum, (
            "product_form should have an enum (Choose from: Flat, round, rectangular bar)"
        )

    def test_hardness_hv_is_nullable_numeric(self, schema):
        _, requirements, _ = schema
        from gaik.software_components.extractor.schema import CompositeExtractionRequirements

        child_fields = {f.field_name: f for f in requirements.child_requirements.fields}
        assert "hardness_hv" in child_fields, "hardness_hv field missing"
        f = child_fields["hardness_hv"]
        assert f.field_type in ("float", "int"), (
            f"hardness_hv should be numeric, got {f.field_type}"
        )
        assert f.nullable is True, "hardness_hv should be nullable (if stated, else null)"

    def test_delivery_length_note_is_nullable(self, schema):
        _, requirements, _ = schema
        from gaik.software_components.extractor.schema import CompositeExtractionRequirements

        child_fields = {f.field_name: f for f in requirements.child_requirements.fields}
        assert "delivery_length_note" in child_fields, "delivery_length_note field missing"
        assert child_fields["delivery_length_note"].nullable is True, (
            "delivery_length_note should be nullable (if stated, else null)"
        )


class TestParentWithNestedListInvoice:
    """Task 5 (custom): Invoice header + line items."""

    @pytest.fixture(scope="class")
    def schema(self):
        model, requirements, analysis = parse_nested_requirements(TASK_INVOICE_PARENT_NESTED)
        return model, requirements, analysis

    def test_structure_type(self, schema):
        _, _, analysis = schema
        assert analysis.structure_type == "parent_with_nested_list"

    def test_child_has_no_list_dict(self, schema):
        _, requirements, _ = schema
        from gaik.software_components.extractor.schema import CompositeExtractionRequirements

        bad = [
            f.field_name
            for f in requirements.child_requirements.fields
            if f.field_type == "list[dict]"
        ]
        assert bad == [], f"Child has list[dict] fields: {bad}"

    def test_currency_has_enum(self, schema):
        _, requirements, _ = schema
        from gaik.software_components.extractor.schema import CompositeExtractionRequirements

        parent_fields = {f.field_name: f for f in requirements.parent_requirements.fields}
        assert "currency" in parent_fields, "currency field missing from parent"
        assert parent_fields["currency"].enum, "currency should have enum (USD, EUR, GBP)"

    def test_unit_price_is_str(self, schema):
        _, requirements, _ = schema
        from gaik.software_components.extractor.schema import CompositeExtractionRequirements

        child_fields = {f.field_name: f for f in requirements.child_requirements.fields}
        assert "unit_price" in child_fields, "unit_price field missing"
        assert child_fields["unit_price"].field_type == "str", (
            f"unit_price should be str (text string with currency symbol), "
            f"got {child_fields['unit_price'].field_type}"
        )

    def test_discount_is_nullable_numeric(self, schema):
        _, requirements, _ = schema
        from gaik.software_components.extractor.schema import CompositeExtractionRequirements

        child_fields = {f.field_name: f for f in requirements.child_requirements.fields}
        assert "discount_percentage" in child_fields, "discount_percentage field missing"
        f = child_fields["discount_percentage"]
        assert f.field_type in ("float", "int"), (
            f"discount_percentage should be numeric, got {f.field_type}"
        )
        assert f.nullable is True, "discount_percentage should be nullable (if stated, else null)"


# ===========================================================================
# Tests — nested_list
# ===========================================================================


class TestNestedListPO:
    """Task 2 (provided): Simple PO line items."""

    @pytest.fixture(scope="class")
    def schema(self):
        model, requirements, analysis = parse_nested_requirements(TASK_PO_NESTED_LIST)
        return model, requirements, analysis

    def test_structure_type(self, schema):
        _, _, analysis = schema
        assert analysis.structure_type == "nested_list"

    def test_no_list_dict_in_item(self, schema):
        _, requirements, _ = schema
        bad = [f.field_name for f in requirements.fields if f.field_type == "list[dict]"]
        assert bad == [], f"Item model has list[dict] fields: {bad}"

    def test_expected_scalar_fields_present(self, schema):
        _, requirements, _ = schema
        names = {f.field_name for f in requirements.fields}
        for expected in ("quantity", "price"):
            assert expected in names, f"Expected field '{expected}' not found. Got: {names}"

    def test_quantity_is_str(self, schema):
        _, requirements, _ = schema
        field_map = {f.field_name: f for f in requirements.fields}
        assert "quantity" in field_map, "quantity field missing"
        assert field_map["quantity"].field_type == "str", (
            f"quantity should be str (text string with unit), "
            f"got {field_map['quantity'].field_type}"
        )

    def test_price_is_str(self, schema):
        _, requirements, _ = schema
        field_map = {f.field_name: f for f in requirements.fields}
        assert "price" in field_map, "price field missing"
        assert field_map["price"].field_type == "str", (
            f"price should be str (text string with currency symbol), "
            f"got {field_map['price'].field_type}"
        )


class TestNestedListLabResults:
    """Task 4 (custom): Medical lab results."""

    @pytest.fixture(scope="class")
    def schema(self):
        model, requirements, analysis = parse_nested_requirements(TASK_LAB_NESTED_LIST)
        return model, requirements, analysis

    def test_structure_type(self, schema):
        _, _, analysis = schema
        assert analysis.structure_type == "nested_list"

    def test_no_list_dict_in_item(self, schema):
        _, requirements, _ = schema
        bad = [f.field_name for f in requirements.fields if f.field_type == "list[dict]"]
        assert bad == [], f"Item model has list[dict] fields: {bad}"

    def test_measured_value_is_str(self, schema):
        _, requirements, _ = schema
        field_map = {f.field_name: f for f in requirements.fields}
        assert "measured_value" in field_map, "measured_value field missing"
        assert field_map["measured_value"].field_type == "str", (
            f"measured_value should be str (text string including unit), "
            f"got {field_map['measured_value'].field_type}"
        )

    def test_status_has_enum(self, schema):
        _, requirements, _ = schema
        field_map = {f.field_name: f for f in requirements.fields}
        assert "status" in field_map, "status field missing"
        assert field_map["status"].enum, (
            "status should have enum (Choose from: Normal, High, Low, Critical)"
        )
        enum_values = set(field_map["status"].enum)
        for v in ("Normal", "High", "Low", "Critical"):
            assert v in enum_values, f"Expected '{v}' in status enum, got {enum_values}"

    def test_flag_is_nullable(self, schema):
        _, requirements, _ = schema
        field_map = {f.field_name: f for f in requirements.fields}
        assert "flag" in field_map, "flag field missing"
        assert field_map["flag"].nullable is True, "flag should be nullable (if stated, else null)"


# ===========================================================================
# Tests — flat
# ===========================================================================


class TestFlatIncident:
    """Task 3 (provided): Finnish incident report — verifies flat path unchanged."""

    @pytest.fixture(scope="class")
    def schema(self):
        model, requirements, analysis = parse_nested_requirements(TASK_INCIDENT_FLAT)
        return model, requirements, analysis

    def test_structure_type(self, schema):
        _, _, analysis = schema
        assert analysis.structure_type == "flat"

    def test_report_type_has_enum(self, schema):
        _, requirements, _ = schema
        field_map = {f.field_name: f for f in requirements.fields}
        assert "raportin_tyyppi" in field_map or any(
            "tyyppi" in n or "type" in n for n in field_map
        ), f"Report type field not found. Fields: {list(field_map.keys())}"
        # Find the report type field regardless of exact name
        rt_field = next(
            (f for f in requirements.fields if "tyyppi" in f.field_name or "type" in f.field_name),
            None,
        )
        assert rt_field is not None, "Report type field not found"
        assert rt_field.enum, f"Report type should have enum, got field_type={rt_field.field_type}"

    def test_no_list_dict(self, schema):
        _, requirements, _ = schema
        bad = [f.field_name for f in requirements.fields if f.field_type == "list[dict]"]
        assert bad == [], f"Flat model has list[dict] fields: {bad}"


class TestFlatEmployee:
    """Task 6 (custom): Employee record — flat with enums and text-string salary."""

    @pytest.fixture(scope="class")
    def schema(self):
        model, requirements, analysis = parse_nested_requirements(TASK_EMPLOYEE_FLAT)
        return model, requirements, analysis

    def test_structure_type(self, schema):
        _, _, analysis = schema
        assert analysis.structure_type == "flat"

    def test_department_has_enum(self, schema):
        _, requirements, _ = schema
        field_map = {f.field_name: f for f in requirements.fields}
        assert "department" in field_map, "department field missing"
        assert field_map["department"].enum, "department should have enum"
        assert "Engineering" in field_map["department"].enum

    def test_employment_type_has_enum(self, schema):
        _, requirements, _ = schema
        field_map = {f.field_name: f for f in requirements.fields}
        assert "employment_type" in field_map, "employment_type field missing"
        assert field_map["employment_type"].enum, "employment_type should have enum"

    def test_annual_salary_is_str(self, schema):
        _, requirements, _ = schema
        field_map = {f.field_name: f for f in requirements.fields}
        assert "annual_salary" in field_map, "annual_salary field missing"
        assert field_map["annual_salary"].field_type == "str", (
            f"annual_salary should be str (text string with currency symbol), "
            f"got {field_map['annual_salary'].field_type}"
        )

    def test_manager_name_is_nullable(self, schema):
        _, requirements, _ = schema
        field_map = {f.field_name: f for f in requirements.fields}
        assert "manager_name" in field_map, "manager_name field missing"
        assert field_map["manager_name"].nullable is True, (
            "manager_name should be nullable (if stated, else null)"
        )

    def test_employee_id_is_str(self, schema):
        _, requirements, _ = schema
        field_map = {f.field_name: f for f in requirements.fields}
        assert "employee_id" in field_map, "employee_id field missing"
        assert field_map["employee_id"].field_type == "str", (
            f"employee_id should be str (text string), got {field_map['employee_id'].field_type}"
        )


# ---------------------------------------------------------------------------
# Task 7 (provided) — parent_with_nested_list, construction blueprint
# Taken from schema_generation_example.py (active task)
# ---------------------------------------------------------------------------

TASK_BLUEPRINT = """
Extract compliance-relevant information from the construction blueprint.

Top-level fields:
- Project address
- Drawing title
- Drawing number
- Sheet number
- Project number
- Scale
- Drawing date
- Owner
- Architect
- General contractor
- Surveyor

For each compliance-relevant item visible in the blueprint, extract:
- Item type (General note, Revision, Dimension, Elevation reference, Legend/material reference, Drawing view, Grid line, Section callout, Other)
- Label or number
- Exact text or value
- Related drawing element or location
- Compliance relevance (Dimensions, Structural reference, Utilities/fixtures, Survey/benchmarks, Specifications, Safety/compliance, Revision control, Material reference, Other)

Rules:
- Extract only explicitly visible information.
- Preserve original wording, dimensions, dates, and labels.
"""


@pytest.fixture(scope="module")
def blueprint_schema():
    return parse_nested_requirements(TASK_BLUEPRINT)


class TestParentWithNestedListBlueprint:
    """Construction blueprint — single child list under a large header."""

    def test_structure_type(self, blueprint_schema):
        _, _, analysis = blueprint_schema
        assert analysis.structure_type == "parent_with_nested_list", (
            f"Expected parent_with_nested_list, got {analysis.structure_type}"
        )

    def test_parent_has_header_fields(self, blueprint_schema):
        _, composite, _ = blueprint_schema
        parent_names = {f.field_name for f in composite.parent_requirements.fields}
        expected = {"project_address", "drawing_title", "drawing_number"}
        missing = expected - parent_names
        assert not missing, f"Parent missing header fields: {missing}"

    def test_parent_has_no_list_dict(self, blueprint_schema):
        _, composite, _ = blueprint_schema
        bad = [
            f.field_name
            for f in composite.parent_requirements.fields
            if f.field_type == "list[dict]"
        ]
        assert not bad, f"Parent should have no list[dict] fields: {bad}"

    def test_child_has_no_list_dict(self, blueprint_schema):
        _, composite, _ = blueprint_schema
        for child in composite.children:
            bad = [f.field_name for f in child.requirements.fields if f.field_type == "list[dict]"]
            assert not bad, f"Child '{child.container_name}' has list[dict] fields: {bad}"

    def test_item_type_has_enum(self, blueprint_schema):
        _, composite, _ = blueprint_schema
        for child in composite.children:
            field_map = {f.field_name: f for f in child.requirements.fields}
            if "item_type" in field_map:
                assert field_map["item_type"].enum, "item_type should have enum values"
                assert "General note" in field_map["item_type"].enum or any(
                    "note" in v.lower() for v in field_map["item_type"].enum
                ), f"item_type enum missing 'General note', got: {field_map['item_type'].enum}"
                return
        pytest.fail("item_type field not found in any child model")

    def test_compliance_relevance_has_enum(self, blueprint_schema):
        _, composite, _ = blueprint_schema
        for child in composite.children:
            field_map = {f.field_name: f for f in child.requirements.fields}
            for fname, fspec in field_map.items():
                if "compliance" in fname and fspec.enum:
                    assert len(fspec.enum) >= 2, (
                        "compliance_relevance enum should have multiple values"
                    )
                    return
        pytest.fail("No enum field for compliance relevance found in any child model")


# ---------------------------------------------------------------------------
# Task 8 (custom) — parent_with_nested_list, multiple child collections
# Tests the new multi-child capability
# ---------------------------------------------------------------------------

TASK_MULTI_CHILD = """
Extract information from the project status report.

Header fields:
- Report title
- Report date (DD/MM/YYYY)
- Project name
- Project manager

For each action item:
- Action description
- Owner
- Due date (DD/MM/YYYY)
- Status (Open, In Progress, Completed, Cancelled)

For each identified risk:
- Risk description
- Likelihood (Low, Medium, High)
- Impact (Low, Medium, High)
- Mitigation
"""


@pytest.fixture(scope="module")
def multi_child_schema():
    return parse_nested_requirements(TASK_MULTI_CHILD)


class TestParentWithMultipleNestedLists:
    """Project status report — two distinct child collections under one parent."""

    def test_structure_type(self, multi_child_schema):
        _, _, analysis = multi_child_schema
        assert analysis.structure_type == "parent_with_nested_list", (
            f"Expected parent_with_nested_list, got {analysis.structure_type}"
        )

    def test_has_multiple_child_containers(self, multi_child_schema):
        _, composite, _ = multi_child_schema
        assert len(composite.children) >= 2, (
            f"Expected at least 2 child containers, got {len(composite.children)}: "
            f"{[c.container_name for c in composite.children]}"
        )

    def test_parent_has_header_fields_only(self, multi_child_schema):
        _, composite, _ = multi_child_schema
        parent_names = {f.field_name for f in composite.parent_requirements.fields}
        child_all_names = {
            f.field_name for child in composite.children for f in child.requirements.fields
        }
        overlap = parent_names & child_all_names
        assert not overlap, f"Parent and child share fields: {overlap}"

    def test_parent_has_no_list_dict(self, multi_child_schema):
        _, composite, _ = multi_child_schema
        bad = [
            f.field_name
            for f in composite.parent_requirements.fields
            if f.field_type == "list[dict]"
        ]
        assert not bad, f"Parent should have no list[dict] fields: {bad}"

    def test_no_child_has_list_dict(self, multi_child_schema):
        _, composite, _ = multi_child_schema
        for child in composite.children:
            bad = [f.field_name for f in child.requirements.fields if f.field_type == "list[dict]"]
            assert not bad, f"Child '{child.container_name}' has list[dict] fields: {bad}"

    def test_child_fields_do_not_cross_contaminate(self, multi_child_schema):
        """Fields from one child section must not appear in another child model."""
        _, composite, _ = multi_child_schema
        if len(composite.children) < 2:
            pytest.skip("Needs at least 2 children")
        all_field_sets = [
            {f.field_name for f in child.requirements.fields} for child in composite.children
        ]
        for i, names_i in enumerate(all_field_sets):
            for j, names_j in enumerate(all_field_sets):
                if i >= j:
                    continue
                overlap = names_i & names_j
                assert not overlap, (
                    f"Child '{composite.children[i].container_name}' and "
                    f"'{composite.children[j].container_name}' share fields: {overlap}"
                )

    def test_action_item_status_has_enum(self, multi_child_schema):
        _, composite, _ = multi_child_schema
        for child in composite.children:
            field_map = {f.field_name: f for f in child.requirements.fields}
            if "status" in field_map and field_map["status"].enum:
                enum_vals = field_map["status"].enum
                assert any("Open" in v or "open" in v.lower() for v in enum_vals), (
                    f"status enum missing 'Open', got: {enum_vals}"
                )
                return
        pytest.fail("No status enum field found in any child model")

    def test_risk_likelihood_has_enum(self, multi_child_schema):
        _, composite, _ = multi_child_schema
        for child in composite.children:
            field_map = {f.field_name: f for f in child.requirements.fields}
            if "likelihood" in field_map:
                assert field_map["likelihood"].enum, "likelihood should have enum values"
                assert any(
                    "Low" in v or "low" in v.lower() for v in field_map["likelihood"].enum
                ), f"likelihood enum missing 'Low', got: {field_map['likelihood'].enum}"
                return
        pytest.fail("likelihood field not found in any child model")

    def test_pydantic_model_has_multiple_list_fields(self, multi_child_schema):
        extraction_model, composite, _ = multi_child_schema
        list_fields = [
            name
            for name, finfo in extraction_model.model_fields.items()
            if get_origin(finfo.annotation) is list
        ]
        assert len(list_fields) >= 2, (
            f"Parent model should have at least 2 list fields, got: {list_fields}"
        )
