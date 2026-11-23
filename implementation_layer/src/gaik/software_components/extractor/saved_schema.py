"""Saved extraction schemas as data.

A generated extraction model is saved as a JSON description of its classes and
fields and rebuilt with :func:`pydantic.create_model` when it is loaded. Loading
never imports or runs a file from the schema folder: the ``.py`` file written
next to it is only there for people to read.

The description covers what :class:`~gaik.software_components.extractor.SchemaGenerator`
produces: ``str`` (optionally with a pattern), ``int``, ``float``, ``bool``,
``Decimal`` (rebuilt as :data:`DecimalField` / :data:`OptionalDecimalField`),
``dict``, ``list[...]``, ``Literal[...]``, str/int ``Enum`` classes, ``Optional[...]``
and nested models,
with descriptions and defaults. :func:`describe_model` refuses a model it cannot
describe faithfully, so a saved description always rebuilds the same model.

File format (``version`` 1)::

    {
      "format": "gaik-saved-schema",
      "version": 1,
      "root": "Invoice_Extraction",
      "models": [                      # nested models before the models using them
        {
          "name": "Invoice_Extraction",
          "doc": "Extraction model for invoice",
          "extra": "forbid",           # or null
          "fields": [
            {"name": "total", "type": {"type": "decimal"}, "description": "...",
             "default": {"$decimal": "0"}},          # no "default" key: required
            {"name": "tags", "type": {"type": "list", "items": {"type": "str"}},
             "description": "...", "default_factory": "list"}
          ]
        }
      ]
    }

Type nodes: ``{"type": "str", "pattern": "..."?}``, ``{"type": "int"}``,
``{"type": "float"}``, ``{"type": "bool"}``, ``{"type": "decimal"}``,
``{"type": "dict"}``, ``{"type": "list", "items": <node>}``,
``{"type": "literal", "values": [...]}``, ``{"type": "optional", "inner": <node>}``,
``{"type": "enum", "name": ..., "doc": ..., "mixin": "str" | "int" | null,
"members": [[name, value], ...]}``
and ``{"type": "model", "name": "<earlier model>"}``.

Older schema folders hold only the ``.py`` file and the requirements JSON. For
those, :func:`load_saved_model` rebuilds the model from the requirements when
they determine it (flat and parent-with-children structures) and writes the
JSON description next to them; for a nested-list structure the requirements do
not record the container field, so it raises :class:`SavedSchemaError` with the
folder and how to convert it, instead of letting the caller generate a new schema
over the saved one. The old ``.py`` file is never imported.
"""

from __future__ import annotations

import json
import keyword
import re
import types
import warnings
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Literal, Optional, Union, get_args, get_origin

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    WithJsonSchema,
    constr,
    create_model,
)
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from .schema import (
    CompositeExtractionRequirements,
    DecimalField,
    ExtractionRequirements,
    OptionalDecimalField,
    _create_parent_with_nested_list_model,
    create_extraction_model,
    decimal_field_repr,
)

FORMAT_NAME = "gaik-saved-schema"
FORMAT_VERSION = 1

_SCALARS = {"str": str, "int": int, "float": float, "bool": bool, "dict": dict}
_FIELD_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
# An enum member may also start with one underscore, as Python allows, but
# not with two (private and dunder names) or end in one too (_sunder_ names).
_ENUM_MEMBER_RE = re.compile(r"_?[A-Za-z0-9][A-Za-z0-9_]*|_")
_MAX_TYPE_DEPTH = 8
_EXTRA_VALUES = {"forbid", "ignore", "allow"}
_FIELD_OPTIONS = {"annotation", "default", "default_factory", "description"}
_PLAIN_FIELD = FieldInfo()  # a Field option set to its default value changes nothing
# Dunder methods that change how a model is built, validated or dumped; any
# other method a model class defines is refused as well.
_MODEL_DUNDERS = {
    "__init__",
    "__new__",
    "__setattr__",
    "__getattr__",
    "__getattribute__",
    "__iter__",
    "__eq__",
    "__copy__",
    "__deepcopy__",
    "__get_pydantic_core_schema__",
    "__get_pydantic_json_schema__",
    "__pydantic_init_subclass__",
}


class SavedSchemaError(ValueError):
    """A model cannot be saved as data, or a saved description is not valid."""


# ---------------------------------------------------------------------------
# model -> description
# ---------------------------------------------------------------------------


def _is_model(tp: Any) -> bool:
    return isinstance(tp, type) and issubclass(tp, BaseModel)


def _union_args(ann: Any) -> tuple | None:
    if get_origin(ann) is Union or isinstance(ann, types.UnionType):
        return get_args(ann)
    return None


def _describe_type(ann: Any, collect) -> dict:
    if decimal_field_repr(ann) == "DecimalField":
        return {"type": "decimal"}
    if decimal_field_repr(ann) == "OptionalDecimalField":
        return {"type": "optional", "inner": {"type": "decimal"}}

    union = _union_args(ann)
    if union is not None:
        non_none = [a for a in union if a is not type(None)]
        if len(non_none) == 1 and len(union) == 2:
            return {"type": "optional", "inner": _describe_type(non_none[0], collect)}
        raise SavedSchemaError(f"Union type {ann!r} cannot be saved as data")

    origin = get_origin(ann)
    if origin is Annotated:
        # Optional[...] keeps a pattern inside: Optional[Annotated[str, constr(...)]].
        base, *metadata = get_args(ann)
        pattern = _pattern_from_metadata(metadata, decimal_kind=None)
        if base is str and pattern is not None:
            return {"type": "str", "pattern": pattern}
        raise SavedSchemaError(f"Type {ann!r} cannot be saved as data")
    if origin is list:
        args = get_args(ann)
        if len(args) != 1:
            raise SavedSchemaError("A list field needs one item type to be saved as data")
        return {"type": "list", "items": _describe_type(args[0], collect)}
    if origin is Literal:
        values = list(get_args(ann))
        for value in values:
            if value is not None and type(value) not in (str, int, float, bool):
                raise SavedSchemaError(f"Literal value {value!r} cannot be saved as data")
        return {"type": "literal", "values": values}
    if _is_model(ann):
        collect(ann)
        return {"type": "model", "name": ann.__name__}
    if isinstance(ann, type) and issubclass(ann, Enum):
        return _describe_enum(ann)
    for name, tp in _SCALARS.items():
        if ann is tp:
            return {"type": name}
    raise SavedSchemaError(f"Type {ann!r} cannot be saved as data")


def _describe_enum(enum_cls: type[Enum]) -> dict:
    """A str- or int-valued Enum, as the Solution Wizard's schema designer writes."""
    mixin = next((m for m in ("str", "int") if issubclass(enum_cls, _SCALARS[m])), None)
    members = []
    for member in enum_cls:
        if type(member.value) not in (str, int):
            raise SavedSchemaError(f"Enum value {member.value!r} cannot be saved as data")
        members.append([member.name, member.value])
    return {
        "type": "enum",
        "name": enum_cls.__name__,
        "doc": enum_cls.__doc__,
        "mixin": mixin,
        "members": members,
    }


_DECIMAL_CLEANER_NAME = "_clean_decimal_string"
# A refusal that already names its field (from a nested model, or a model's own
# check), so the outer field is not added to it again.
_NAMES_A_FIELD = re.compile(r"(?:Field|Model) '")


def _check_decimal_metadata(metadata: list, decimal_kind: str) -> None:
    """A Decimal field holds what DecimalField / OptionalDecimalField carry, and nothing more.

    That is one ``WithJsonSchema`` with the alias's JSON schema and one
    ``BeforeValidator`` for the amount text; the rebuild restores both. Any
    other metadata (``ge``, ``max_digits``, more validators) is refused, since
    the rebuilt field would not have it. So is a cleaner that is not gaik's
    ``_clean_decimal_string`` (or a copy under that name, as a saved schema.py
    holds): the rebuild would replace it with gaik's, and a cleaner that refuses
    negative amounts, say, would be lost.
    """
    alias = OptionalDecimalField if decimal_kind == "OptionalDecimalField" else DecimalField
    expected_schema = next(m for m in get_args(alias)[1:] if isinstance(m, WithJsonSchema))
    schemas = [m for m in metadata if isinstance(m, WithJsonSchema)]
    cleaners = [
        m
        for m in metadata
        if isinstance(m, BeforeValidator) and m.json_schema_input_type is PydanticUndefined
    ]
    if len(metadata) == 2 and schemas == [expected_schema] and len(cleaners) == 1:
        name = getattr(cleaners[0].func, "__name__", None)
        if name != _DECIMAL_CLEANER_NAME:
            raise SavedSchemaError(
                f"Decimal field cleaner {name!r} cannot be saved as data: the rebuilt field "
                f"would use gaik's {_DECIMAL_CLEANER_NAME} instead"
            )
        return
    other = [m for m in metadata if not isinstance(m, (WithJsonSchema, BeforeValidator))]
    if other:
        raise SavedSchemaError(f"Decimal field constraint {other!r} cannot be saved as data")
    raise SavedSchemaError(
        "A Decimal field is saved as data only as DecimalField or OptionalDecimalField"
    )


def _pattern_from_metadata(metadata: list, decimal_kind: str | None) -> str | None:
    """The pattern the generator attaches to a ``str`` field, if any.

    ``create_extraction_model`` writes ``Annotated[str, constr(pattern=...)]``.
    Decimal fields carry the DecimalField metadata, which the rebuild restores;
    see :func:`_check_decimal_metadata`. Any other metadata (``ge``,
    ``max_length``, validators) is refused.
    """
    if decimal_kind is not None:
        _check_decimal_metadata(metadata, decimal_kind)
        return None
    pattern = None
    for item in metadata:
        inner = get_args(item)[1:] if get_origin(item) is Annotated else ()
        constraints = [c for c in inner if isinstance(c, StringConstraints)]
        if len(constraints) == 1 and constraints[0] == StringConstraints(
            pattern=constraints[0].pattern
        ):
            pattern = constraints[0].pattern
            continue
        raise SavedSchemaError(f"Field constraint {item!r} cannot be saved as data")
    return pattern


def _encode_default(value: Any) -> Any:
    if isinstance(value, Enum):
        # Stored as its value; pydantic shows and dumps an Enum default that way.
        value = value.value
    if isinstance(value, Decimal):
        return {"$decimal": str(value)}
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is float:
        if value != value or value in (float("inf"), float("-inf")):
            raise SavedSchemaError("A non-finite float default cannot be saved as data")
        return value
    raise SavedSchemaError(f"Default {value!r} cannot be saved as data")


def _own_methods(model: type[BaseModel]) -> list[str]:
    """Methods and properties the model or a base class between it and BaseModel defines."""
    found: list[str] = []
    for cls in model.__mro__:
        if cls is BaseModel or not issubclass(cls, BaseModel):
            continue
        for name, value in vars(cls).items():
            is_dunder = name.startswith("__") and name.endswith("__")
            if is_dunder and name not in _MODEL_DUNDERS:
                continue
            if callable(value) or isinstance(value, (classmethod, staticmethod, property)):
                found.append(name)
    return sorted(set(found))


def _describe_one(model: type[BaseModel], collect) -> dict:
    fields = []
    for name, info in model.model_fields.items():
        # Only what the description holds; any other Field option (alias,
        # frozen, exclude, exclude_if, ...) would be lost in the rebuild.
        options = {
            key
            for key, value in getattr(info, "_attributes_set", {}).items()
            if key not in _FIELD_OPTIONS and value != getattr(_PLAIN_FIELD, key, None)
        }
        if options:
            raise SavedSchemaError(
                f"Field {name!r} has options that cannot be saved as data: {sorted(options)}"
            )
        try:
            type_node = _describe_type(info.annotation, collect)
            decimal_kind = decimal_field_repr(info.annotation)
            pattern = _pattern_from_metadata(list(info.metadata), decimal_kind)
            default = (
                _encode_default(info.default)
                if info.default_factory is None and info.default is not PydanticUndefined
                else PydanticUndefined
            )
        except SavedSchemaError as exc:
            if _NAMES_A_FIELD.match(str(exc)):
                raise  # a nested model's field, already named
            # The refusal names the field, so the person can find it.
            raise SavedSchemaError(f"Field {name!r} of {model.__name__!r}: {exc}") from exc
        if pattern is not None:
            if type_node != {"type": "str"}:
                raise SavedSchemaError(f"Pattern on non-text field {name!r}")
            type_node = {"type": "str", "pattern": pattern}
        entry: dict[str, Any] = {
            "name": name,
            "type": type_node,
            "description": info.description,
        }
        if info.default_factory is not None:
            factory = getattr(info.default_factory, "__name__", None)
            if info.default_factory not in (list, dict):
                raise SavedSchemaError(f"Default factory of {name!r} cannot be saved as data")
            entry["default_factory"] = factory
        elif default is not PydanticUndefined:
            entry["default"] = default
        fields.append(entry)

    # Validators, serializers, computed fields, model_post_init and config
    # options other than "extra" change what the model gives back without
    # showing in its JSON schema, and the rebuilt model would not have them.
    decorators = model.__pydantic_decorators__
    if any(
        (
            decorators.validators,
            decorators.field_validators,
            decorators.root_validators,
            decorators.field_serializers,
            decorators.model_serializers,
            decorators.model_validators,
            decorators.computed_fields,
        )
    ):
        raise SavedSchemaError(
            f"Model {model.__name__!r} has validators or serializers that cannot be saved as data"
        )
    if model.__private_attributes__:
        raise SavedSchemaError(
            f"Model {model.__name__!r} has private attributes that cannot be saved as data: "
            f"{sorted(model.__private_attributes__)}"
        )
    methods = _own_methods(model)
    if methods:
        raise SavedSchemaError(
            f"Model {model.__name__!r} defines methods that cannot be saved as data: {methods}"
        )
    other_config = {k: v for k, v in model.model_config.items() if k not in ("extra", "title")}
    if other_config or model.model_config.get("title") not in (None, model.__name__):
        raise SavedSchemaError(
            f"Model {model.__name__!r} has config options that cannot be saved as data: "
            f"{sorted(model.model_config)}"
        )
    extra = model.model_config.get("extra")
    return {
        "name": model.__name__,
        "doc": model.__doc__,
        "extra": extra if extra in _EXTRA_VALUES else None,
        "fields": fields,
    }


def describe_model(model: type[BaseModel]) -> dict:
    """Return the JSON-ready description of ``model`` and its nested models.

    Raises :class:`SavedSchemaError` when the model uses something the
    description cannot hold, or when the rebuilt model's JSON schema differs
    from the original's.
    """
    if not _is_model(model):
        raise SavedSchemaError("Only a pydantic model can be saved as data")

    ordered: list[dict] = []
    seen: dict[str, type[BaseModel]] = {}

    def collect(m: type[BaseModel]) -> None:
        if m.__name__ in seen:
            if seen[m.__name__] is not m:
                raise SavedSchemaError(f"Two nested models are both named {m.__name__!r}")
            return
        seen[m.__name__] = m
        ordered.append(_describe_one(m, collect))

    # A nested model is described while its parent is, so it is appended first.
    collect(model)
    description = {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "root": model.__name__,
        "models": _dependency_order(ordered),
    }

    rebuilt = build_model(description)
    if rebuilt.model_json_schema() != model.model_json_schema():
        raise SavedSchemaError(f"Model {model.__name__!r} does not rebuild the same from data")
    return description


def _dependency_order(models: list[dict]) -> list[dict]:
    by_name = {m["name"]: m for m in models}
    out: list[dict] = []
    done: set[str] = set()

    def refs(node: dict) -> list[str]:
        if node["type"] == "model":
            return [node["name"]]
        for key in ("items", "inner"):
            if key in node:
                return refs(node[key])
        return []

    def visit(name: str) -> None:
        if name in done:
            return
        done.add(name)
        for field in by_name[name]["fields"]:
            for ref in refs(field["type"]):
                visit(ref)
        out.append(by_name[name])

    for m in models:
        visit(m["name"])
    return out


# ---------------------------------------------------------------------------
# description -> model
# ---------------------------------------------------------------------------


class _Built:
    """The models and enums rebuilt so far, kept apart so neither stands in for the other."""

    def __init__(self) -> None:
        self.models: dict[str, type[BaseModel]] = {}
        self.enums: dict[str, type[Enum]] = {}


def _expect_keys(node: dict, allowed: set[str], where: str) -> None:
    if not isinstance(node, dict):
        raise SavedSchemaError(f"{where} must be an object")
    unknown = set(node) - allowed
    if unknown:
        raise SavedSchemaError(f"{where} has unknown keys {sorted(unknown)}")


def _build_type(node: Any, built: _Built, depth: int = 0) -> Any:
    if depth > _MAX_TYPE_DEPTH:
        raise SavedSchemaError("Type is nested too deeply")
    if not isinstance(node, dict) or not isinstance(node.get("type"), str):
        raise SavedSchemaError("Each type must be an object with a 'type' name")
    kind = node["type"]

    if kind == "str" and "pattern" in node:
        _expect_keys(node, {"type", "pattern"}, "str type")
        if not isinstance(node["pattern"], str):
            raise SavedSchemaError("pattern must be text")
        # Same construct create_extraction_model uses, so the rebuilt field
        # behaves exactly like the generated one.
        return Annotated[str, constr(pattern=node["pattern"])]
    if kind in _SCALARS:
        _expect_keys(node, {"type"}, f"{kind} type")
        return _SCALARS[kind]
    if kind == "decimal":
        _expect_keys(node, {"type"}, "decimal type")
        return DecimalField
    if kind == "list":
        _expect_keys(node, {"type", "items"}, "list type")
        return list[_build_type(node.get("items"), built, depth + 1)]
    if kind == "literal":
        _expect_keys(node, {"type", "values"}, "literal type")
        values = node.get("values")
        if not isinstance(values, list) or not values:
            raise SavedSchemaError("literal values must be a non-empty list")
        for value in values:
            if value is not None and type(value) not in (str, int, float, bool):
                raise SavedSchemaError(f"literal value {value!r} is not allowed")
        return Literal[tuple(values)]  # type: ignore[valid-type]
    if kind == "optional":
        _expect_keys(node, {"type", "inner"}, "optional type")
        inner = node.get("inner")
        if isinstance(inner, dict) and inner == {"type": "decimal"}:
            return OptionalDecimalField
        return Optional[_build_type(inner, built, depth + 1)]  # noqa: UP045
    if kind == "enum":
        return _build_enum(node, built)
    if kind == "model":
        _expect_keys(node, {"type", "name"}, "model type")
        name = node.get("name")
        if not isinstance(name, str) or name not in built.models:
            raise SavedSchemaError(f"Model {name!r} is used before it is described")
        return built.models[name]
    raise SavedSchemaError(f"Unknown type {kind!r}")


def _build_enum(node: dict, built: _Built) -> type[Enum]:
    _expect_keys(node, {"type", "name", "doc", "mixin", "members"}, "enum type")
    name = _check_name(node.get("name"), "Enum name")
    doc = node.get("doc")
    if doc is not None and not isinstance(doc, str):
        raise SavedSchemaError("enum doc must be text")
    mixin = node.get("mixin")
    if mixin not in (None, "str", "int"):
        raise SavedSchemaError(f"enum mixin {mixin!r} is not allowed")
    members = node.get("members")
    if not isinstance(members, list) or not members:
        raise SavedSchemaError("enum members must be a non-empty list")
    pairs = []
    for member in members:
        if not (isinstance(member, list) and len(member) == 2):
            raise SavedSchemaError("each enum member must be a [name, value] pair")
        member_name = _check_enum_member(member[0])
        if type(member[1]) not in (str, int):
            raise SavedSchemaError(f"enum value {member[1]!r} is not allowed")
        pairs.append((member_name, member[1]))

    if name in built.enums:
        existing = built.enums[name]
        if [(m.name, m.value) for m in existing] != pairs:
            raise SavedSchemaError(f"Enum {name!r} is described twice with different members")
        return existing
    try:
        enum_cls = Enum(name, pairs, type=_SCALARS[mixin] if mixin else None)
    except Exception as exc:
        raise SavedSchemaError(f"Enum {name!r} could not be rebuilt: {exc}") from exc
    # Python's Enum leaves out or merges some members without an error (a
    # private name such as _Status__x, a value given twice); refuse that.
    if [(m.name, m.value) for m in enum_cls] != pairs:
        raise SavedSchemaError(f"Enum {name!r} does not rebuild with the members described")
    enum_cls.__doc__ = doc
    built.enums[name] = enum_cls
    return enum_cls


def _decode_default(value: Any) -> Any:
    if isinstance(value, dict):
        _expect_keys(value, {"$decimal"}, "default")
        raw = value.get("$decimal")
        if not isinstance(raw, str):
            raise SavedSchemaError("A decimal default must be text")
        try:
            number = Decimal(raw)
        except InvalidOperation as exc:
            raise SavedSchemaError(f"Decimal default {raw!r} is not a number") from exc
        if not number.is_finite():
            raise SavedSchemaError(f"Decimal default {raw!r} is not a finite number")
        return number
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise SavedSchemaError(f"Default {value!r} is not allowed")


def _enum_default(annotation: Any, value: Any, fname: str) -> Any:
    """An Enum field's saved default is its value; give back the member."""
    union = _union_args(annotation)
    candidates = [a for a in union if a is not type(None)] if union else [annotation]
    if value is None or len(candidates) != 1:
        return value
    enum_cls = candidates[0]
    if not (isinstance(enum_cls, type) and issubclass(enum_cls, Enum)):
        return value
    try:
        return enum_cls(value)
    except ValueError as exc:
        raise SavedSchemaError(
            f"Default of {fname!r} is not a member of {enum_cls.__name__}"
        ) from exc


def _check_name(name: Any, what: str) -> str:
    if not isinstance(name, str) or not _FIELD_NAME_RE.fullmatch(name):
        raise SavedSchemaError(f"{what} {name!r} is not a plain identifier")
    return name


def _check_enum_member(name: Any) -> str:
    if (
        not isinstance(name, str)
        or not _ENUM_MEMBER_RE.fullmatch(name)
        or name[0].isdigit()
        or (len(name) > 1 and name[0] == "_" and name[-1] == "_")
    ):
        raise SavedSchemaError(f"Enum member {name!r} is not a name Python's enum accepts")
    return name


def _build_one(spec: dict, built: _Built) -> type[BaseModel]:
    _expect_keys(spec, {"name", "doc", "extra", "fields"}, "model")
    name = _check_name(spec.get("name"), "Model name")
    if keyword.iskeyword(name):
        raise SavedSchemaError(f"Model name {name!r} is not allowed")
    doc = spec.get("doc")
    if doc is not None and not isinstance(doc, str):
        raise SavedSchemaError("doc must be text")
    extra = spec.get("extra")
    if extra is not None and extra not in _EXTRA_VALUES:
        raise SavedSchemaError(f"extra {extra!r} is not allowed")
    fields = spec.get("fields")
    if not isinstance(fields, list):
        raise SavedSchemaError("fields must be a list")

    definitions: dict[str, tuple[Any, Any]] = {}
    for field in fields:
        _expect_keys(field, {"name", "type", "description", "default", "default_factory"}, "field")
        fname = _check_name(field.get("name"), "Field name")
        if fname in definitions:
            raise SavedSchemaError(f"Field {fname!r} appears twice")
        annotation = _build_type(field.get("type"), built)
        description = field.get("description")
        if description is not None and not isinstance(description, str):
            raise SavedSchemaError("description must be text")
        if "default_factory" in field:
            if "default" in field:
                raise SavedSchemaError(f"Field {fname!r} has both default and default_factory")
            factory = {"list": list, "dict": dict}.get(field["default_factory"])
            if factory is None:
                raise SavedSchemaError(f"default_factory {field['default_factory']!r}")
            info = Field(default_factory=factory, description=description)
        elif "default" in field:
            default = _enum_default(annotation, _decode_default(field["default"]), fname)
            info = Field(default=default, description=description)
        else:
            info = Field(description=description)
        definitions[fname] = (annotation, info)

    config = ConfigDict(extra=extra) if extra else None
    try:
        return create_model(name, __config__=config, __doc__=doc, **definitions)
    except Exception as exc:  # pydantic raises several kinds for a bad definition
        raise SavedSchemaError(f"Model {name!r} could not be rebuilt: {exc}") from exc


def build_model(description: dict) -> type[BaseModel]:
    """Rebuild the model a :func:`describe_model` description holds."""
    _expect_keys(description, {"format", "version", "root", "models"}, "saved schema")
    if description.get("format") != FORMAT_NAME:
        raise SavedSchemaError("Not a gaik saved schema")
    if description.get("version") != FORMAT_VERSION:
        raise SavedSchemaError(f"Unsupported saved schema version {description.get('version')!r}")
    models = description.get("models")
    if not isinstance(models, list) or not models:
        raise SavedSchemaError("models must be a non-empty list")

    built = _Built()
    for spec in models:
        model = _build_one(spec, built)
        if model.__name__ in built.models:
            raise SavedSchemaError(f"Model {model.__name__!r} is described twice")
        built.models[model.__name__] = model
    root = description.get("root")
    if not isinstance(root, str) or root not in built.models:
        raise SavedSchemaError(f"Root model {root!r} is not described")
    return built.models[root]


# ---------------------------------------------------------------------------
# files
# ---------------------------------------------------------------------------


def write_model_file(model: type[BaseModel], path: Path) -> None:
    """Write the JSON description of ``model`` to ``path``."""
    description = describe_model(model)
    path.write_text(json.dumps(description, indent=2, ensure_ascii=False), encoding="utf-8")


def save_model_file(model: type[BaseModel], path: Path) -> bool:
    """Save ``model`` to ``path`` for a later load, or remove what is there.

    The schema-saving callers use this one rule: when ``model`` cannot be
    saved as data, an older file at ``path`` (from a previous model) is
    removed, so a later load does not rebuild that model next to the new
    requirements. A ``UserWarning`` says why and ``False`` is returned; the load
    then rebuilds the model from the requirements, or refuses.
    """
    path = Path(path)
    try:
        description = describe_model(model)
    except SavedSchemaError as exc:
        path.unlink(missing_ok=True)
        warnings.warn(
            f"Schema {model.__name__!r} not saved as data: {exc}", UserWarning, stacklevel=2
        )
        return False
    tmp_path = path.with_name(path.name + ".tmp")
    try:
        tmp_path.write_text(json.dumps(description, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(path)
    finally:
        tmp_path.unlink(missing_ok=True)
    return True


def read_model_file(path: Path) -> type[BaseModel]:
    """Rebuild a model from the JSON description at ``path``."""
    try:
        description = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SavedSchemaError(f"{Path(path).name} is not valid JSON: {exc}") from exc
    return build_model(description)


def rebuild_from_requirements(
    model_name: str,
    requirements: ExtractionRequirements | CompositeExtractionRequirements,
) -> type[BaseModel] | None:
    """Rebuild a model from its saved requirements alone, if they determine it.

    Flat and parent-with-children models are built from the requirements by
    the generator's own functions. A nested-list model (``*_Collection``) keeps
    its container field name and description only in the model, so it cannot
    be rebuilt: ``None``. ``None`` also when the rebuilt name differs from the
    saved one, which means the requirements describe a different model.
    """
    requirements = requirements.model_copy(deep=True)
    if isinstance(requirements, CompositeExtractionRequirements):
        model = _create_parent_with_nested_list_model(
            parent_requirements=requirements.parent_requirements,
            children=requirements.children,
        )
    elif model_name.endswith("_Collection"):
        return None
    else:
        model = create_extraction_model(requirements)
    return model if model.__name__ == model_name else None


def load_saved_model(
    model_path: Path,
    model_name: str,
    requirements: ExtractionRequirements | CompositeExtractionRequirements,
) -> type[BaseModel]:
    """Load a saved model from ``model_path`` without running any file.

    When ``model_path`` is missing (a folder saved by an older gaik that has
    only the ``.py`` file), the model is rebuilt from ``requirements`` and the
    description is written to ``model_path`` for the next load; a
    ``UserWarning`` says so, since edits made only in the ``.py`` file are not in
    the rebuilt model. When neither works, :class:`SavedSchemaError` names the
    folder and how to convert it: the schema is not generated again over the
    saved one.
    """
    model_path = Path(model_path)
    if model_path.exists():
        model = read_model_file(model_path)
        if model.__name__ != model_name:
            raise SavedSchemaError(
                f"{model_path.name} holds {model.__name__!r}, the requirements name {model_name!r}"
            )
        return model

    model = rebuild_from_requirements(model_name, requirements)
    if model is None:
        # Generating it again would replace a schema someone may have reviewed
        # with a new one, possibly with other field names, so it is refused.
        raise SavedSchemaError(
            f"Saved schema {model_name!r} in {model_path.parent} has no {model_path.name} "
            "and cannot be rebuilt from its requirements. To keep it, load its .py "
            "file once in a trusted environment and save the class with "
            f"gaik.software_components.extractor.saved_schema.write_model_file(Model, "
            f"{str(model_path)!r}); to generate a new schema, remove the folder's "
            "schema files."
        )
    try:
        write_model_file(model, model_path)
        saved = f"and saved it as {model_path.name}"
    except (OSError, SavedSchemaError) as exc:
        saved = f"but could not save it as {model_path.name} ({type(exc).__name__})"
    warnings.warn(
        f"Rebuilt saved schema {model_name!r} in {model_path.parent} from its requirements "
        f"{saved}; edits made only in the folder's .py file are not in it.",
        UserWarning,
        stacklevel=2,
    )
    return model


__all__ = [
    "FORMAT_NAME",
    "FORMAT_VERSION",
    "SavedSchemaError",
    "build_model",
    "describe_model",
    "load_saved_model",
    "read_model_file",
    "rebuild_from_requirements",
    "save_model_file",
    "write_model_file",
]
