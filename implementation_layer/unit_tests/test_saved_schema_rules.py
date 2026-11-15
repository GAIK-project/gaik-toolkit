"""Saved schemas: what a save refuses, what a load gives back, and old folders."""

from __future__ import annotations

import json
from enum import Enum

import pytest
from gaik.software_components.extractor.saved_schema import (
    FORMAT_NAME,
    FORMAT_VERSION,
    SavedSchemaError,
    build_model,
    describe_model,
    load_saved_model,
    read_model_file,
    save_model_file,
    write_model_file,
)
from gaik.software_components.extractor.schema import (
    ExtractionRequirements,
    FieldSpec,
    create_extraction_model,
)
from pydantic import BaseModel, Field


def _one_model(fields: list[dict], name: str = "Ticket") -> dict:
    return {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "root": name,
        "models": [{"name": name, "doc": None, "extra": None, "fields": fields}],
    }


def test_a_refused_save_removes_the_previous_model_file(tmp_path, capsys):
    class Ticket(BaseModel):
        title: str = Field(description="Title")

    path = tmp_path / "schema_model.json"
    write_model_file(Ticket, path)

    class Ticket(BaseModel):  # noqa: F811 - same name, a model the format refuses
        count: int = Field(ge=0)

    assert save_model_file(Ticket, path) is False
    assert not path.exists()
    assert "not saved as data" in capsys.readouterr().out


def test_a_saved_model_replaces_the_previous_file(tmp_path):
    class Ticket(BaseModel):
        title: str

    path = tmp_path / "schema_model.json"
    path.write_text("old", encoding="utf-8")

    assert save_model_file(Ticket, path) is True
    assert list(read_model_file(path).model_fields) == ["title"]
    assert [p.name for p in tmp_path.iterdir()] == ["schema_model.json"]


@pytest.mark.parametrize("which", ["documents", "audio"])
def test_a_pipeline_save_of_a_refused_model_does_not_leave_the_old_one_loaded(which, tmp_path):
    if which == "documents":
        pytest.importorskip("fitz")
        from gaik.software_modules.documents_to_structured_data.pipeline import (
            DocumentsToStructuredData as Pipeline,
        )
    else:
        from gaik.software_modules.audio_to_structured_data.pipeline import (
            AudioToStructuredData as Pipeline,
        )
    pipeline = object.__new__(Pipeline)
    first = ExtractionRequirements(
        use_case_name="ticket",
        fields=[FieldSpec(field_name="title", field_type="str", description="Title")],
    )
    pipeline.save_schema(create_extraction_model(first), first, tmp_path, "ticket")

    second = ExtractionRequirements(
        use_case_name="ticket",
        fields=[FieldSpec(field_name="count", field_type="int", description="Count")],
    )
    model = create_extraction_model(second)

    class Refused(model):
        extra_field: int = Field(default=0, ge=0)

    Refused.__name__ = model.__name__
    pipeline.save_schema(Refused, second, tmp_path, "ticket")

    loaded, _ = pipeline.load_schema(tmp_path, "ticket")
    # Rebuilt from the new requirements, not the first model's file.
    assert list(loaded.model_fields) == ["count"]


def test_a_nullable_text_field_with_a_pattern_is_saved_and_rebuilt():
    requirements = ExtractionRequirements(
        use_case_name="code",
        fields=[
            FieldSpec(
                field_name="code",
                field_type="str",
                description="Code",
                pattern=r"^[A-Z]{3}$",
                required=False,
            )
        ],
    )
    model = create_extraction_model(requirements)

    rebuilt = build_model(describe_model(model))

    assert rebuilt.model_json_schema() == model.model_json_schema()
    assert rebuilt(code=None).code is None
    for value in ("ABC", "abc"):
        assert rebuilt.model_validate({"code": value}).model_dump() == (
            model.model_validate({"code": value}).model_dump()
        )


@pytest.mark.parametrize("member", ["_", "_x", "A_1"])
def test_an_enum_member_python_accepts_is_saved(member):
    status_enum = Enum("Status", {member: "v"}, type=str)

    class Ticket(BaseModel):
        status: status_enum

    rebuilt = build_model(describe_model(Ticket))
    assert [m.name for m in rebuilt.model_fields["status"].annotation] == [member]


@pytest.mark.parametrize("member", ["__x", "_x_", "1a", "a-b", "A\n"])
def test_an_enum_member_python_reserves_or_refuses_is_not_read(member):
    node = {
        "type": "enum",
        "name": "Status",
        "doc": None,
        "mixin": "str",
        "members": [[member, "v"]],
    }
    with pytest.raises(SavedSchemaError):
        build_model(_one_model([{"name": "status", "type": node, "description": None}]))


def test_an_enum_default_comes_back_as_its_member():
    class Urgency(str, Enum):
        LOW = "low"
        HIGH = "high"

    class Ticket(BaseModel):
        priority: Urgency = Urgency.LOW
        maybe: Urgency | None = Urgency.HIGH

    rebuilt = build_model(describe_model(Ticket))

    assert rebuilt().priority is rebuilt.model_fields["priority"].annotation.LOW
    assert isinstance(rebuilt.model_fields["priority"].default, Enum)
    assert rebuilt.model_fields["maybe"].default.name == "HIGH"


def test_an_enum_default_that_is_not_a_member_is_refused():
    node = {"type": "enum", "name": "U", "doc": None, "mixin": "str", "members": [["LOW", "low"]]}
    field = {"name": "p", "type": node, "description": None, "default": "urgent"}
    with pytest.raises(SavedSchemaError, match="not a member"):
        build_model(_one_model([field]))


@pytest.mark.parametrize("raw", ["abc", "", "NaN", "Infinity"])
def test_a_decimal_default_that_is_not_a_finite_number_is_refused(raw):
    field = {
        "name": "total",
        "type": {"type": "decimal"},
        "description": None,
        "default": {"$decimal": raw},
    }
    with pytest.raises(SavedSchemaError):
        build_model(_one_model([field]))


@pytest.mark.parametrize("name", ["Ticket\n", "Ticket "])
def test_a_name_with_a_trailing_line_break_or_space_is_refused(name):
    with pytest.raises(SavedSchemaError, match="plain identifier"):
        build_model(_one_model([], name=name))
    with pytest.raises(SavedSchemaError, match="plain identifier"):
        build_model(_one_model([{"name": name, "type": {"type": "str"}, "description": None}]))


def test_the_vision_extractor_refuses_an_older_nested_folder_instead_of_generating(tmp_path):
    pytest.importorskip("fitz")
    from gaik.software_components.vision_extractor import vision_extractor as ve

    (tmp_path / "schema.py").write_text("raise SystemExit('ran')\n", encoding="utf-8")
    requirements = ExtractionRequirements(
        use_case_name="line item",
        fields=[FieldSpec(field_name="name", field_type="str", description="Name")],
    )
    (tmp_path / "requirements.json").write_text(
        json.dumps(
            {
                "model_name": "line_item_Collection",
                "requirements_type": "extraction",
                "requirements": requirements.model_dump(),
            }
        ),
        encoding="utf-8",
    )
    extractor = object.__new__(ve.VisionExtractor)

    with pytest.raises(SavedSchemaError, match="cannot be rebuilt"):
        extractor._resolve_schema("unused", tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["requirements.json", "schema.py"]


def test_load_saved_model_reads_an_existing_file_without_the_requirements(tmp_path):
    class Ticket(BaseModel):
        title: str

    write_model_file(Ticket, tmp_path / "m.json")
    assert list(load_saved_model(tmp_path / "m.json", "Ticket", None).model_fields) == ["title"]


def test_a_root_that_names_an_enum_instead_of_a_model_is_refused():
    description = _one_model(
        [
            {
                "name": "status",
                "type": {
                    "type": "enum",
                    "name": "Status",
                    "doc": None,
                    "mixin": "str",
                    "members": [["OPEN", "open"]],
                },
                "description": None,
            }
        ]
    )
    description["root"] = "enum:Status"

    with pytest.raises(SavedSchemaError, match="Root model"):
        build_model(description)
