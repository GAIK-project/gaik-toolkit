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
not record the container field, so it returns ``None`` and the caller generates
the schema again. The old ``.py`` file is never imported.
"""

from __future__ import annotations

import json
import keyword
import re
import types
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Literal, Optional, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, constr, create_model
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
_FIELD_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_MAX_TYPE_DEPTH = 8
_EXTRA_VALUES = {"forbid", "ignore", "allow"}


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


def _pattern_from_metadata(metadata: list, is_decimal: bool) -> str | None:
    """The pattern the generator attaches to a ``str`` field, if any.

    ``create_extraction_model`` writes ``Annotated[str, constr(pattern=...)]``.
    Decimal fields carry the DecimalField metadata, which the rebuild restores.
    Any other metadata (``ge``, ``max_length``, validators) is refused.
    """
    if is_decimal:
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


def _describe_one(model: type[BaseModel], collect) -> dict:
    fields = []
    for name, info in model.model_fields.items():
        if info.alias or info.title or info.examples or info.json_schema_extra:
            raise SavedSchemaError(f"Field {name!r} has options that cannot be saved as data")
        type_node = _describe_type(info.annotation, collect)
        is_decimal = decimal_field_repr(info.annotation) is not None
        pattern = _pattern_from_metadata(list(info.metadata), is_decimal)
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
        elif info.default is not PydanticUndefined:
            entry["default"] = _encode_default(info.default)
        fields.append(entry)

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


def _expect_keys(node: dict, allowed: set[str], where: str) -> None:
    if not isinstance(node, dict):
        raise SavedSchemaError(f"{where} must be an object")
    unknown = set(node) - allowed
    if unknown:
        raise SavedSchemaError(f"{where} has unknown keys {sorted(unknown)}")


def _build_type(node: Any, built: dict[str, type[BaseModel]], depth: int = 0) -> Any:
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
        if name not in built:
            raise SavedSchemaError(f"Model {name!r} is used before it is described")
        return built[name]
    raise SavedSchemaError(f"Unknown type {kind!r}")


def _build_enum(node: dict, built: dict[str, Any]) -> type[Enum]:
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
        member_name = _check_name(member[0], "Enum member")
        if type(member[1]) not in (str, int):
            raise SavedSchemaError(f"enum value {member[1]!r} is not allowed")
        pairs.append((member_name, member[1]))

    key = f"enum:{name}"  # ':' cannot appear in a model name, so no clash
    if key in built:
        existing = built[key]
        if [(m.name, m.value) for m in existing] != pairs:
            raise SavedSchemaError(f"Enum {name!r} is described twice with different members")
        return existing
    try:
        enum_cls = Enum(name, pairs, type=_SCALARS[mixin] if mixin else None)
    except Exception as exc:
        raise SavedSchemaError(f"Enum {name!r} could not be rebuilt: {exc}") from exc
    enum_cls.__doc__ = doc
    built[key] = enum_cls
    return enum_cls


def _decode_default(value: Any) -> Any:
    if isinstance(value, dict):
        _expect_keys(value, {"$decimal"}, "default")
        raw = value.get("$decimal")
        if not isinstance(raw, str):
            raise SavedSchemaError("A decimal default must be text")
        return Decimal(raw)
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise SavedSchemaError(f"Default {value!r} is not allowed")


def _check_name(name: Any, what: str) -> str:
    if not isinstance(name, str) or not _FIELD_NAME_RE.match(name):
        raise SavedSchemaError(f"{what} {name!r} is not a plain identifier")
    return name


def _build_one(spec: dict, built: dict[str, type[BaseModel]]) -> type[BaseModel]:
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
            info = Field(default=_decode_default(field["default"]), description=description)
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

    built: dict[str, type[BaseModel]] = {}
    for spec in models:
        model = _build_one(spec, built)
        if model.__name__ in built:
            raise SavedSchemaError(f"Model {model.__name__!r} is described twice")
        built[model.__name__] = model
    root = description.get("root")
    if root not in built:
        raise SavedSchemaError(f"Root model {root!r} is not described")
    return built[root]


# ---------------------------------------------------------------------------
# files
# ---------------------------------------------------------------------------


def write_model_file(model: type[BaseModel], path: Path) -> None:
    """Write the JSON description of ``model`` to ``path``."""
    description = describe_model(model)
    path.write_text(json.dumps(description, indent=2, ensure_ascii=False), encoding="utf-8")


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
) -> type[BaseModel] | None:
    """Load a saved model from ``model_path`` without running any file.

    When ``model_path`` is missing (a folder saved by an older gaik that has
    only the ``.py`` file), the model is rebuilt from ``requirements`` and the
    description is written to ``model_path`` for the next load. Returns
    ``None`` when neither works; the caller then generates the schema again.
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
        print(
            f"Saved schema {model_name!r} has no {model_path.name} and cannot be rebuilt "
            "from its requirements; it will be generated again."
        )
        return None
    try:
        write_model_file(model, model_path)
    except (OSError, SavedSchemaError):
        pass
    print(f"Rebuilt saved schema {model_name!r} from its requirements")
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
    "write_model_file",
]
