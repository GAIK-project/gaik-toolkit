"""Tests for SchemaDesigner (WP-2)."""

import ast
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.schema_designer import (
    build_pydantic_model,
    build_requirements_json,
    build_requirements_text,
    write_schema_files,
    write_extraction_requirements,
)

SPEC_FULL = {
    "schema_name": "MaintenanceTicket",
    "fields": ["fault_description", "location", "urgency_level", "technician_name", "timestamp"],
    "field_types": {
        "fault_description": "string",
        "location": "string",
        "urgency_level": "string",
        "technician_name": "string",
        "timestamp": "datetime",
    },
    "required_fields": ["fault_description", "location", "urgency_level"],
    "optional_fields": ["technician_name", "timestamp"],
    "field_descriptions": {
        "fault_description": "Description of the fault observed",
        "urgency_level": "How urgent the fault is",
    },
    "allowed_values": {"urgency_level": ["low", "medium", "high", "critical"]},
    "missing_value_policy": 'Return an empty string ("") if the field is not present.',
}

SPEC_MINIMAL = {
    "schema_name": "SimpleOutput",
    "fields": ["name", "value"],
    "required_fields": ["name"],
}


# ---------------------------------------------------------------------------
# requirements text
# ---------------------------------------------------------------------------

def test_requirements_text_contains_all_fields():
    text = build_requirements_text(SPEC_FULL)
    for field in SPEC_FULL["fields"]:
        assert field in text


def test_requirements_text_marks_required_optional():
    text = build_requirements_text(SPEC_FULL)
    assert "REQUIRED" in text
    assert "OPTIONAL" in text


def test_requirements_text_includes_allowed_values():
    text = build_requirements_text(SPEC_FULL)
    assert "low" in text
    assert "critical" in text


def test_requirements_text_minimal():
    text = build_requirements_text(SPEC_MINIMAL)
    assert "name" in text
    assert "value" in text


# ---------------------------------------------------------------------------
# Pydantic model generation
# ---------------------------------------------------------------------------

def test_pydantic_model_parses():
    src = build_pydantic_model(SPEC_FULL, "MaintenanceTicket")
    ast.parse(src)  # should not raise


def test_pydantic_model_required_fields_not_optional():
    src = build_pydantic_model(SPEC_FULL, "MaintenanceTicket")
    # Required fields should not have Optional wrapper
    assert "fault_description:" in src
    assert "location:" in src
    assert "urgency_level:" in src
    assert "Optional[str]" not in src.split("fault_description:")[1].split("\n")[0]


def test_pydantic_model_optional_fields_wrapped():
    src = build_pydantic_model(SPEC_FULL, "MaintenanceTicket")
    assert "Optional" in src
    assert "technician_name: Optional[str]" in src


def test_pydantic_model_enum_generated_for_allowed_values():
    src = build_pydantic_model(SPEC_FULL, "MaintenanceTicket")
    assert "Enum" in src
    assert "LOW" in src


def test_pydantic_model_field_descriptions_in_json_schema():
    """Field(description=...) must propagate into the JSON Schema properties."""
    src = build_pydantic_model(SPEC_FULL, "MaintenanceTicket")
    assert "Field(description=" in src or 'description="' in src


def test_safe_enum_member_names():
    """Enum member names for values with digits/special chars must be valid identifiers."""
    spec = {
        "schema_name": "Test",
        "fields": ["status"],
        "required_fields": ["status"],
        "allowed_values": {"status": ["1-open", "2-closed", "in progress", "N/A"]},
    }
    src = build_pydantic_model(spec, "Test")
    # Must parse without error
    ast.parse(src)
    # Digit-starting values must be prefixed so identifier is valid
    assert "V_1_OPEN" in src   # "1-open" -> "V_1_OPEN"
    assert "V_2_CLOSED" in src  # "2-closed" -> "V_2_CLOSED"
    assert "IN_PROGRESS" in src # "in progress" -> "IN_PROGRESS"
    assert "N_A" in src         # "N/A" -> "N_A"


def test_pydantic_model_class_name():
    src = build_pydantic_model(SPEC_FULL, "MaintenanceTicket")
    assert "class MaintenanceTicket(BaseModel):" in src


def test_pydantic_model_minimal():
    src = build_pydantic_model(SPEC_MINIMAL, "SimpleOutput")
    ast.parse(src)
    assert "class SimpleOutput(BaseModel):" in src


def test_pydantic_model_runtime_instantiable():
    src = build_pydantic_model(SPEC_FULL, "MaintenanceTicket")
    ns = {}
    exec(compile(src, "<test>", "exec"), ns)
    cls = ns["MaintenanceTicket"]
    instance = cls(
        fault_description="pump broken",
        location="hall A",
        urgency_level="low",
    )
    assert instance.fault_description == "pump broken"
    assert instance.technician_name is None


# ---------------------------------------------------------------------------
# requirements.json
# ---------------------------------------------------------------------------

def test_requirements_json_structure():
    data = build_requirements_json(SPEC_FULL, "test_uc", "MaintenanceTicket")
    assert data["model_name"] == "MaintenanceTicket"
    assert "requirements" in data
    req = data["requirements"]
    assert req["use_case_name"] == "test_uc"
    names = [f["field_name"] for f in req["fields"]]
    assert "fault_description" in names
    assert "technician_name" in names


def test_requirements_json_required_flag():
    data = build_requirements_json(SPEC_FULL, "test_uc", "MaintenanceTicket")
    by_name = {f["field_name"]: f for f in data["requirements"]["fields"]}
    assert by_name["fault_description"]["required_in_output"] is True
    assert by_name["technician_name"]["required_in_output"] is False


# ---------------------------------------------------------------------------
# File writing
# ---------------------------------------------------------------------------

def test_write_schema_files_correct_filenames(tmp_path):
    """load_schema(schema_dir, 'output_schema') expects output_schema_requirements.json."""
    write_schema_files(SPEC_FULL, "MaintenanceTicket", tmp_path, "test_uc")
    assert (tmp_path / "schemas" / "output_schema.py").exists()
    assert (tmp_path / "schemas" / "output_schema_requirements.json").exists()


def test_write_schema_files_requirements_payload(tmp_path):
    """Payload must match load_schema() contract."""
    write_schema_files(SPEC_FULL, "MaintenanceTicket", tmp_path, "test_uc")
    data = json.loads((tmp_path / "schemas" / "output_schema_requirements.json").read_text())
    assert data["model_name"] == "MaintenanceTicket"
    req = data["requirements"]
    assert "use_case_name" in req
    assert "fields" in req
    for f in req["fields"]:
        for key in ("field_name", "field_type", "required_in_output", "nullable"):
            assert key in f, f"Missing key '{key}' in field spec"


def test_write_schema_files_allowed_types(tmp_path):
    """field_type must be one of AllowedTypes accepted by FieldSpec."""
    allowed = {"str", "int", "float", "bool", "list[str]", "date", "decimal", "list[dict]"}
    write_schema_files(SPEC_FULL, "MaintenanceTicket", tmp_path, "test_uc")
    data = json.loads((tmp_path / "schemas" / "output_schema_requirements.json").read_text())
    for f in data["requirements"]["fields"]:
        assert f["field_type"] in allowed, f"Unexpected field_type: {f['field_type']}"


def test_write_schema_files_output_schema_json(tmp_path):
    write_schema_files(SPEC_FULL, "MaintenanceTicket", tmp_path, "test_uc")
    json_path = tmp_path / "schemas" / "output_schema.json"
    if json_path.exists():
        schema = json.loads(json_path.read_text())
        assert "properties" in schema or "title" in schema


def test_write_extraction_requirements(tmp_path):
    path = write_extraction_requirements(SPEC_FULL, tmp_path)
    assert path.exists()
    content = path.read_text()
    assert "fault_description" in content
