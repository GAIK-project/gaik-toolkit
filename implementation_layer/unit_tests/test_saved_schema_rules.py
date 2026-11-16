"""Saved schemas: what a save refuses, what a load gives back, and old folders."""

from __future__ import annotations

import json
from decimal import Decimal
from enum import Enum
from typing import Annotated

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
    DecimalField,
    ExtractionRequirements,
    FieldSpec,
    OptionalDecimalField,
    create_extraction_model,
)
from pydantic import AfterValidator, BaseModel, Field, ValidationError


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


class _BoundedTotal(BaseModel):
    total: DecimalField = Field(ge=0)


class _BoundedOptionalTotal(BaseModel):
    total: OptionalDecimalField = Field(default=None, max_digits=5)


class _CheckedTotal(BaseModel):
    total: Annotated[DecimalField, AfterValidator(lambda v: v)]


@pytest.mark.parametrize("model", [_BoundedTotal, _BoundedOptionalTotal, _CheckedTotal])
def test_a_decimal_field_with_more_than_the_decimal_field_carries_is_refused(model):
    with pytest.raises(SavedSchemaError, match="Decimal field"):
        describe_model(model)


def test_a_refused_decimal_limit_is_one_the_original_model_enforces():
    with pytest.raises(ValidationError):
        _BoundedTotal(total="-12.50")
    with pytest.raises(SavedSchemaError):
        describe_model(_BoundedTotal)


def test_a_bare_decimal_field_is_refused():
    class Plain(BaseModel):
        total: Decimal

    with pytest.raises(SavedSchemaError, match="DecimalField or OptionalDecimalField"):
        describe_model(Plain)


def test_decimal_fields_as_the_generator_writes_them_are_saved():
    class Invoice(BaseModel):
        total: DecimalField = Field(description="Total")
        fee: OptionalDecimalField = Field(default=None, description="Fee")

    rebuilt = build_model(describe_model(Invoice))
    assert rebuilt(total="12.40 EUR", fee=None).total == Decimal("12.40")


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


def _validated_title():
    from pydantic import field_validator

    class Ticket(BaseModel):
        title: str

        @field_validator("title")
        @classmethod
        def upper(cls, value: str) -> str:
            return value.upper()

    return Ticket


def _checked_model():
    from pydantic import model_validator

    class Ticket(BaseModel):
        title: str

        @model_validator(mode="after")
        def check(self):
            return self

    return Ticket


def _serialized_title():
    from pydantic import field_serializer

    class Ticket(BaseModel):
        title: str

        @field_serializer("title")
        def lower(self, value: str) -> str:
            return value.lower()

    return Ticket


def _computed_field():
    from pydantic import computed_field

    class Ticket(BaseModel):
        title: str

        @computed_field
        @property
        def size(self) -> int:
            return len(self.title)

    return Ticket


@pytest.mark.parametrize(
    "make", [_validated_title, _checked_model, _serialized_title, _computed_field]
)
def test_a_model_with_validators_serializers_or_computed_fields_is_not_saved(make):
    with pytest.raises(SavedSchemaError, match="validators or serializers"):
        describe_model(make())


def test_a_model_with_a_config_option_other_than_extra_is_not_saved_as_data():
    from pydantic import ConfigDict

    class Ticket(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True)
        title: str

    with pytest.raises(SavedSchemaError, match="config options"):
        describe_model(Ticket)


def test_a_model_with_a_private_attribute_is_not_saved_as_data():
    from pydantic import PrivateAttr

    class Ticket(BaseModel):
        title: str
        _seen: int = PrivateAttr(0)

    with pytest.raises(SavedSchemaError, match="private attributes.*_seen"):
        describe_model(Ticket)


def _post_init():
    class Ticket(BaseModel):
        title: str

        def model_post_init(self, context) -> None:
            self.title = self.title.strip()

    return Ticket


def _own_init():
    class Ticket(BaseModel):
        title: str

        def __init__(self, **data):
            data["title"] = str(data.get("title", "")).strip()
            super().__init__(**data)

    return Ticket


def _own_dump():
    class Base(BaseModel):
        def model_dump(self, **kwargs):
            return {}

    class Ticket(Base):
        title: str

    return Ticket


@pytest.mark.parametrize(
    "make,method",
    [(_post_init, "model_post_init"), (_own_init, "__init__"), (_own_dump, "model_dump")],
)
def test_a_model_that_defines_its_own_methods_is_not_saved_as_data(make, method):
    with pytest.raises(SavedSchemaError, match=f"defines methods.*{method}"):
        describe_model(make())


@pytest.mark.parametrize(
    "option,field",
    [
        ("frozen", Field(default="", frozen=True)),
        ("exclude", Field(default="", exclude=True)),
        ("exclude_if", Field(default="", exclude_if=lambda v: v == "")),
        ("validate_default", Field(default="", validate_default=True)),
        ("validation_alias", Field(default="", validation_alias="name")),
        ("serialization_alias", Field(default="", serialization_alias="name")),
    ],
)
def test_a_field_option_the_description_cannot_hold_is_not_saved(option, field):
    from pydantic import create_model

    ticket = create_model("Ticket", title=(str, field))

    with pytest.raises(SavedSchemaError, match=f"Field 'title' has options.*'{option}'"):
        describe_model(ticket)


def test_a_rebuild_that_cannot_be_saved_does_not_say_it_was_saved(tmp_path, monkeypatch, capsys):
    import gaik.software_components.extractor.saved_schema as saved_schema

    requirements = ExtractionRequirements(
        use_case_name="ticket",
        fields=[FieldSpec(field_name="title", field_type="str", description="Title")],
    )
    model_name = create_extraction_model(requirements).__name__

    def cannot_write(model, path):
        raise OSError("read-only folder")

    monkeypatch.setattr(saved_schema, "write_model_file", cannot_write)
    model = load_saved_model(tmp_path / "m_model.json", model_name, requirements)

    assert list(model.model_fields) == ["title"]
    out = capsys.readouterr().out
    assert "could not save it as m_model.json" in out
    assert "and saved it" not in out


_STATUS_ENUM = {
    "type": "enum",
    "name": "Status",
    "doc": None,
    "mixin": "str",
    "members": [["OPEN", "open"]],
}


@pytest.mark.parametrize("ref", ["Status", "enum:Status"])
def test_a_model_reference_that_names_an_enum_is_refused(ref):
    description = _one_model(
        [
            {"name": "status", "type": _STATUS_ENUM, "description": None},
            {"name": "other", "type": {"type": "model", "name": ref}, "description": None},
        ]
    )

    with pytest.raises(SavedSchemaError, match="used before it is described"):
        build_model(description)


@pytest.mark.parametrize(
    "members",
    [
        [["_Status__x", "x"], ["OPEN", "open"]],  # a private name is not a member
        [["OPEN", "open"], ["ALSO_OPEN", "open"]],  # a repeated value is an alias
    ],
)
def test_an_enum_python_would_rebuild_with_fewer_members_is_refused(members):
    node = {**_STATUS_ENUM, "members": members}

    with pytest.raises(SavedSchemaError, match="members described"):
        build_model(_one_model([{"name": "status", "type": node, "description": None}]))
