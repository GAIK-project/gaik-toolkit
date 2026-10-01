"""The field table of a generated schema."""

import datetime
import decimal
from typing import Annotated, Literal

from api.utils.schema_view import describe_fields, readable_format, specs_by_name
from pydantic import BaseModel, Field


class Line(BaseModel):
    description: str = Field(description="What was bought")
    quantity: int | None = Field(default=None, description="How many")
    price: decimal.Decimal | None = Field(default=None, description="Unit price")


class Invoice(BaseModel):
    number: str = Field(description="Invoice number")
    date: datetime.date | None = Field(default=None, description="Invoice date")
    priority: Literal["low", "medium", "high"] | None = Field(default=None, description="Urgency")
    status: Literal["", "open", "closed"] = Field(default="", description="Status")
    tags: list[str] = Field(default_factory=list, description="Labels")
    paid: bool | None = Field(default=None, description="Paid or not")
    lines: list[Line] = Field(default_factory=list, description="Invoice lines")
    amount: Annotated[float, Field(description="Total")] = 0.0


def _by_name(fields):
    return {field["name"]: field for field in fields}


def test_plain_types_and_requirements():
    fields = _by_name(describe_fields(Invoice))

    assert fields["number"]["type"] == "text"
    assert fields["number"]["required"] is True
    assert fields["date"]["type"] == "date"
    assert fields["date"]["required"] is False
    assert fields["paid"]["type"] == "true or false"
    assert fields["tags"]["type"] == "list of text"


def test_choices_list_their_allowed_values():
    fields = _by_name(describe_fields(Invoice))

    assert fields["priority"]["type"] == "choice"
    assert fields["priority"]["allowed"] == ["low", "medium", "high"]
    # An empty string among the values means "not stated": it is not offered as a value.
    assert fields["status"]["allowed"] == ["open", "closed"]
    assert fields["status"]["nullable"] is True


def test_nested_records_come_with_their_fields():
    fields = _by_name(describe_fields(Invoice))

    assert fields["lines"]["type"] == "list of records"
    children = _by_name(fields["lines"]["children"])
    assert children["price"]["type"] == "decimal number"
    assert children["quantity"]["type"] == "whole number"
    assert children["description"]["required"] is True


def test_annotated_fields_are_read_through_their_wrapper():
    assert _by_name(describe_fields(Invoice))["amount"]["type"] == "number"


def test_a_date_held_as_text_is_shown_as_a_date_with_its_format():
    class Doc(BaseModel):
        when: str | None = Field(default=None, description="Invoice date")

    requirements = {"fields": [{"field_name": "when", "field_type": "date", "format": "%d/%m/%Y"}]}

    field = describe_fields(Doc, specs_by_name(requirements))[0]

    assert field["type"] == "date"
    assert field["format"] == "DD/MM/YYYY"


def test_specs_are_found_in_nested_requirements():
    requirements = {
        "parent_requirements": {"fields": [{"field_name": "a", "field_type": "str"}]},
        "children": [{"fields": [{"field_name": "b", "field_type": "int"}]}],
    }

    assert set(specs_by_name(requirements)) == {"a", "b"}


def test_formats_are_written_as_people_write_them():
    assert readable_format("%d.%m.%Y %H:%M") == "DD.MM.YYYY HH:mm"
