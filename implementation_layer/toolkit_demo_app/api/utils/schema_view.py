"""A generated schema as a field table for people: names, plain types, rules and nested records."""

import datetime
import decimal
from types import NoneType, UnionType
from typing import Annotated, Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel

_PLAIN = {
    str: "text",
    int: "whole number",
    float: "number",
    bool: "true or false",
    decimal.Decimal: "decimal number",
    datetime.date: "date",
    datetime.datetime: "date and time",
    datetime.time: "time",
}


def _strip(annotation: Any) -> tuple[Any, bool]:
    """The annotation without Annotated wrappers and ``| None``, and whether None was allowed."""
    nullable = False
    while True:
        origin = get_origin(annotation)
        if origin is Annotated:
            annotation = get_args(annotation)[0]
            continue
        if origin in (Union, UnionType):
            args = [arg for arg in get_args(annotation) if arg is not NoneType]
            if len(args) != len(get_args(annotation)):
                nullable = True
            if len(args) == 1:
                annotation = args[0]
                continue
        return annotation, nullable


def _is_model(annotation: Any) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


def _plain_name(annotation: Any) -> str:
    if annotation in _PLAIN:
        return _PLAIN[annotation]
    name = getattr(annotation, "__name__", str(annotation))
    # Decimal types wrapped by the demo keep their own names; read them as numbers.
    return "decimal number" if "decimal" in name.lower() else name


def describe_type(annotation: Any) -> dict[str, Any]:
    """Plain type, allowed values and nested record of one annotation."""
    inner, nullable = _strip(annotation)
    allowed: list[str] | None = None
    child: type[BaseModel] | None = None

    if get_origin(inner) is Literal:
        values = [value for value in get_args(inner)]
        allowed = [str(value) for value in values if value != ""]
        label = "choice"
        if "" in values:
            nullable = True
    elif get_origin(inner) is list:
        item, _ = _strip((get_args(inner) or (str,))[0])
        if _is_model(item):
            label, child = "list of records", item
        elif get_origin(item) is Literal:
            label = "list of choices"
            allowed = [str(value) for value in get_args(item) if value != ""]
        else:
            label = f"list of {_plain_name(item)}"
    elif _is_model(inner):
        label, child = "record", inner
    else:
        label = _plain_name(inner)
    return {"type": label, "nullable": nullable, "allowed": allowed, "child": child}


_FORMAT_WORDS = (
    ("%Y", "YYYY"),
    ("%y", "YY"),
    ("%m", "MM"),
    ("%d", "DD"),
    ("%H", "HH"),
    ("%M", "mm"),
    ("%S", "SS"),
)


def readable_format(pattern: str) -> str:
    """A date format as people write it: ``%d/%m/%Y`` -> ``DD/MM/YYYY``."""
    for code, word in _FORMAT_WORDS:
        pattern = pattern.replace(code, word)
    return pattern


def specs_by_name(requirements: Any) -> dict[str, dict[str, Any]]:
    """The extraction requirements' field specs by field name, wherever they are nested."""
    found: dict[str, dict[str, Any]] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("field_name"), str):
                found.setdefault(node["field_name"], node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(requirements)
    return found


def structure_of(fields: list[dict[str, Any]]) -> str:
    """The structure the generator found, read from the field table of its schema.

    Only a list of records: ``nested_list``. Fields plus a list of records:
    ``parent_with_nested_list``. Otherwise ``flat``.
    """
    lists = [f for f in fields if f["type"] == "list of records"]
    if not lists:
        return "flat"
    return "nested_list" if len(lists) == len(fields) else "parent_with_nested_list"


def describe_fields(
    model: type[BaseModel], specs: dict[str, dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Every field of the model, with the fields of nested records under ``children``.

    ``specs`` (see :func:`specs_by_name`) adds what the Python type cannot say: a date that
    the model holds as text, and the format it is written in.
    """
    specs = specs or {}
    fields = []
    for name, info in model.model_fields.items():
        details = describe_type(info.annotation)
        child = details.pop("child")
        spec = specs.get(name, {})
        if details["type"] == "text" and spec.get("field_type") in ("date", "datetime"):
            details["type"] = "date" if spec["field_type"] == "date" else "date and time"
        entry: dict[str, Any] = {
            "name": name,
            "description": info.description or "",
            "required": info.is_required() and not details["nullable"],
            **details,
        }
        if spec.get("format"):
            entry["format"] = readable_format(str(spec["format"]))
        if child is not None:
            entry["children"] = describe_fields(child, specs)
        fields.append(entry)
    return fields
