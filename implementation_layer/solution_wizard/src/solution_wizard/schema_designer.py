"""SchemaDesigner -- generates schema artefacts from blueprint.target_output_spec.

Resolves the schema_ref / requirements_ref that V1 marked as 'to_be_generated'.

Generates three files into poc/schemas/:
  output_schema.py    -- typed Pydantic model (reference / documentation)
  output_schema.json  -- JSON Schema exported from that model
  requirements.json   -- field metadata consumed by the GAIK Extractor at runtime

Also generates poc/prompts/extraction_requirements.md -- the plain-text
requirements string passed to AudioToStructuredData / DocumentsToStructuredData
as user_requirements.

All generation is deterministic (no API calls).  The GAIK SchemaGenerator
remains the *runtime* component; these files are the design-time contract.
"""

from __future__ import annotations

import json
import keyword

# ---------------------------------------------------------------------------
# Python type mapping from JSON-style type names
# ---------------------------------------------------------------------------
import re
from pathlib import Path
from typing import Any

_TYPE_MAP: dict[str, str] = {
    "string": "str",
    "str": "str",
    "text": "str",
    "number": "float",
    "float": "float",
    "integer": "int",
    "int": "int",
    "boolean": "bool",
    "bool": "bool",
    "date": "str",  # dates as ISO strings; add a description note
    "datetime": "str",
    "list": "list[str]",
    "array": "list[str]",
    # "dict"/"object" intentionally omitted: bare Python dict produces
    # Optional[dict] which Azure OpenAI's structured-output API rejects
    # (requires additionalProperties:false on every object).
    # A list of records is described under the spec's `nested` key instead,
    # which gives a named row model (see NESTED_KEY). A field typed object or
    # dict without one is typed as str so the PoC at least parses.
    "object": "str",
    "dict": "str",
    "enum": "str",
    # "Decimal" is a marker _py_type() can return like any other type name;
    # build_pydantic_model() special-cases it below to emit the safe
    # DecimalField/OptionalDecimalField aliases instead of bare Decimal --
    # see _DECIMAL_HELPER_SOURCE for why a bare Decimal field is unsafe
    # (regex-lookaround JSON schema some providers reject, and a crash when
    # the model writes "12.40 EUR" instead of a bare number).
    "decimal": "Decimal",
    "money": "Decimal",
    "currency": "Decimal",
}

# This module is deliberately gaik-independent ("All generation is
# deterministic (no API calls)" -- see module docstring), so the Decimal
# safety net is inlined here rather than imported from
# gaik.software_components.extractor.schema.decimal_field_repr /
# DECIMAL_PERSISTED_HELPER_SOURCE, which this module's own callers cannot
# assume is installed. Keep this text in sync with schema.py's copy if that
# logic ever changes.
_DECIMAL_HELPER_SOURCE = r'''
import re as _re
from decimal import Decimal
from typing import Annotated

from pydantic import BeforeValidator, WithJsonSchema

_CURRENCY_NOISE_RE = _re.compile(
    r"(?i)\b(EUR|USD|GBP|JPY|CHF|SEK|NOK|DKK|CAD|AUD|INR)\b|[€$£¥₹]"
)
_CURRENCY_BETWEEN_DIGITS_RE = _re.compile(
    r"(?i)\d\s*(?:\b(?:EUR|USD|GBP|JPY|CHF|SEK|NOK|DKK|CAD|AUD|INR)\b|[€$£¥₹])\s*\d"
)
_SINGLE_AMOUNT_RE = _re.compile(r"^[-+]?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$")
_COMMA_DECIMAL_RE = _re.compile(
    r"^(?P<sign>[-+]?)(?P<int>\d{1,3}(?P<sep>[ \u00a0\u202f.])\d{3}(?:(?P=sep)\d{3})*|\d+)"
    r",(?P<frac>\d+)$"
)
_GROUP_SEPARATORS_RE = _re.compile(r"[ \u00a0\u202f.]")


def _clean_decimal_string(v):
    """Strip currency/unit noise before Decimal parsing and read a dot or
    comma decimal; reject (return None) ambiguous or multi-number input
    rather than fabricating a value. See
    gaik.software_components.extractor.schema._clean_decimal_string for the
    full policy this mirrors."""
    if not isinstance(v, str):
        return v
    s = v.strip()
    if not s:
        return None
    if _CURRENCY_BETWEEN_DIGITS_RE.search(s):
        return None
    s = _CURRENCY_NOISE_RE.sub("", s).strip()
    if not s:
        return None
    if _SINGLE_AMOUNT_RE.match(s):
        return s.replace(",", "")
    m = _COMMA_DECIMAL_RE.match(s)
    if m:
        return f"{m['sign']}{_GROUP_SEPARATORS_RE.sub('', m['int'])}.{m['frac']}"
    return None


DecimalField = Annotated[
    Decimal, WithJsonSchema({"type": "string"}), BeforeValidator(_clean_decimal_string)
]
OptionalDecimalField = Annotated[
    Decimal | None,
    WithJsonSchema({"anyOf": [{"type": "string"}, {"type": "null"}]}),
    BeforeValidator(_clean_decimal_string),
]
'''


def _py_type(type_name: str) -> str:
    return _TYPE_MAP.get(type_name.lower().strip(), "str")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_spec(target_output_spec: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of target_output_spec with fields normalised to List[str].

    For multi_source_report use cases, `fields` is a list of section dicts
    (id, title, instructions, depends_on).  All downstream builders expect a
    flat List[str] of field names.  This helper extracts field ids and merges
    section instructions into field_descriptions so the full prompt text is
    preserved.
    """
    raw_fields = target_output_spec.get("fields", [])
    if not raw_fields or not isinstance(raw_fields[0], dict):
        return target_output_spec  # already flat; nothing to do

    flat_fields: list[str] = []
    extra_descriptions: dict[str, str] = {}
    for item in raw_fields:
        fid = item.get("id") or item.get("title", "")
        flat_fields.append(fid)
        instr = item.get("instructions", "")
        if instr:
            extra_descriptions[fid] = instr

    # Merge: existing field_descriptions take precedence; fill gaps with instructions
    existing_descs = target_output_spec.get("field_descriptions", {})
    if not isinstance(existing_descs, dict):
        existing_descs = {}
    merged_descriptions = dict(extra_descriptions)
    merged_descriptions.update(existing_descs)

    # Build a normalised copy
    normalised = dict(target_output_spec)
    normalised["fields"] = flat_fields
    normalised["field_descriptions"] = merged_descriptions
    # required_fields: if list contains dicts, flatten them too
    raw_required = normalised.get("required_fields", [])
    if raw_required and isinstance(raw_required[0], dict):
        normalised["required_fields"] = [r.get("id", r.get("title", "")) for r in raw_required]
    return normalised


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_requirements_text(target_output_spec: dict[str, Any]) -> str:
    """Build a plain-text user requirements string from target_output_spec.

    This is passed to AudioToStructuredData / DocumentsToStructuredData as
    user_requirements.  It mirrors the format used in the official examples.
    """
    target_output_spec = _normalize_spec(target_output_spec)
    fields: list[str] = target_output_spec.get("fields", [])
    required_fields: list[str] = target_output_spec.get("required_fields", [])
    missing_value_policy: str = target_output_spec.get(
        "missing_value_policy", 'Return an empty string ("") if the value is not present.'
    )

    lines = [
        "Extract the following fields from the provided content.\n",
        f"If a field cannot be determined, apply this policy: {missing_value_policy}\n",
    ]

    nested = _nested_specs(target_output_spec)
    for i, field in enumerate(fields, 1):
        req_marker = "REQUIRED" if field in required_fields else "OPTIONAL"
        if field in nested:
            # A list of rows: its type is the rows', and each row field is listed.
            row = _normalize_spec(nested[field])
            desc = _container_description(target_output_spec, field).rstrip(". ")
            line = f"{i}. {field} (list of rows, {req_marker})"
            lines.append(line + (f": {desc}" if desc else "") + ". Each row has:")
            lines += [f"   {item}" for item in _field_lines(row, "-")]
            continue
        lines += [f"{i}. {item}" for item in _field_lines(target_output_spec, None, [field])]

    return "\n".join(lines)


def _field_lines(
    spec: dict[str, Any], marker: str | None, only: list[str] | None = None
) -> list[str]:
    """One requirements line per field: name, type, REQUIRED or OPTIONAL, description,
    allowed values. ``marker`` starts each line (a list bullet), ``only`` picks fields."""
    field_types: dict[str, str] = spec.get("field_types", {})
    required_fields: list[str] = spec.get("required_fields", [])
    field_descriptions: dict[str, str] = spec.get("field_descriptions", {})
    allowed_values: dict[str, list[str]] = spec.get("allowed_values", {})
    lines = []
    for field in only if only is not None else spec.get("fields", []):
        req_marker = "REQUIRED" if field in required_fields else "OPTIONAL"
        type_str = field_types.get(field, "string")
        desc = field_descriptions.get(field, "")
        allowed = allowed_values.get(field, [])

        line = f"{marker} " if marker else ""
        line += f"{field} ({type_str}, {req_marker})"
        if desc:
            line += f": {desc}"
        if allowed:
            line += f" -- allowed values: {', '.join(str(v) for v in allowed)}"
        lines.append(line)
    return lines


#: Key under which a spec describes the rows of a repeated child collection.
#: The rest of the spec is flat -- `fields` is a list of names -- so a field whose
#: value is a list of records had nowhere to say what a record contains, and
#: `_TYPE_MAP` typed it `str` "so the PoC at least parses". That is what turned
#: a purchase order's line items into one text field.
NESTED_KEY = "nested"


def _nested_specs(target_output_spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The child collections this spec describes, keyed by container field name.

    Only containers that are also listed in ``fields`` count: a nested block for
    a field the output does not have is a spec error we ignore rather than
    generate a model nobody references.
    """
    nested = target_output_spec.get(NESTED_KEY)
    if not isinstance(nested, dict):
        return {}
    fields = target_output_spec.get("fields", [])
    return {
        name: spec
        for name, spec in nested.items()
        if name in fields and isinstance(spec, dict) and spec.get("fields")
    }


def _container_description(target_output_spec: dict[str, Any], container: str) -> str:
    """What one list of rows holds: the field's description, else the row block's own."""
    descriptions = target_output_spec.get("field_descriptions") or {}
    row = _nested_specs(target_output_spec).get(container) or {}
    return str(descriptions.get(container) or row.get("description") or "")


def nested_row_fields(target_output_spec: dict[str, Any]) -> dict[str, list[str]]:
    """The field names of each nested collection's rows, keyed by container field.

    They become the attributes of a generated row model, so a caller that checks
    names before generating reads them here instead of the spec's own layout.
    """
    return {
        name: [field for field in spec.get("fields", []) if isinstance(field, str)]
        for name, spec in _nested_specs(target_output_spec).items()
    }


#: Words that end like a plural but are not one, or whose singular is themselves.
_NOT_PLURAL_ENDINGS = ("ss", "us", "is")
_SAME_SINGULAR = {"series", "species", "news", "data"}


def _child_model_name(container: str) -> str:
    """``line_items`` -> ``LineItem``. Singular, because the class is one row."""
    words = [w for w in container.split("_") if w]
    if words:
        last = words[-1]
        if last.lower() in _SAME_SINGULAR or last.lower().endswith(_NOT_PLURAL_ENDINGS):
            pass  # status, analysis, address and series stay as they are
        elif len(last) > 3 and last.endswith("ies"):
            words[-1] = last[:-3] + "y"  # entries -> entry
        elif len(last) > 2 and last.endswith("s"):
            words[-1] = last[:-1]  # items -> item
    return "".join(w.title() for w in words) or "Item"


#: Names the generated module imports or defines besides its models and Enums,
#: and the capitalised keywords: a generated class takes none of them.
_MODULE_NAMES = frozenset(
    {
        "Annotated",
        "BaseModel",
        "BeforeValidator",
        "ConfigDict",
        "Decimal",
        "DecimalField",
        "Enum",
        "False",
        "Field",
        "List",
        "None",
        "Optional",
        "OptionalDecimalField",
        "True",
        "WithJsonSchema",
    }
)


def _claim(base: str, taken: set[str]) -> str:
    """``base``, or ``base`` with a number when the module already has that name."""
    name, n = base, 2
    while name in taken:
        name, n = f"{base}{n}", n + 1
    taken.add(name)
    return name


def _model_plan(target_output_spec: dict[str, Any], name: str) -> list[dict[str, Any]]:
    """Every model class the spec defines and its class names, row models first.

    One walk names all classes of the generated module, so the source
    (build_pydantic_model) and the model built from data (_model_from_spec) use
    the same names, and no two classes share one: a parent field and a row field
    both called ``status`` get ``StatusEnum`` and ``LineItemStatusEnum``. Rows
    are one level deep, as gaik's CompositeExtractionRequirements are.
    """
    taken = set(_MODULE_NAMES) | {name}
    plans: list[dict[str, Any]] = []

    def walk(spec: dict[str, Any], model_name: str, prefix: str, row: bool) -> None:
        spec = _normalize_spec(spec)
        fields: list[str] = spec.get("fields", [])
        # Names go into the source as written; descriptions and allowed values go in
        # as string literals (repr), so no text from the spec can end one.
        _source_name(model_name, "class name")
        for field in fields:
            _source_name(field, "field name")
        nested = _nested_specs(spec)
        # A container is a list of rows: allowed values on it name no Enum.
        enums = _enum_names(
            [f for f in fields if f not in nested], spec.get("allowed_values", {}), prefix, taken
        )
        if nested and row:
            raise ValueError(
                f"the rows of {model_name} have rows of their own ({', '.join(nested)}); "
                "only one level of nested rows is supported"
            )
        children: dict[str, str] = {}
        for container, child_spec in nested.items():
            child = _claim(_child_model_name(container), taken)
            walk(child_spec, child, child, True)
            children[container] = child
        plans.append(
            {"name": model_name, "spec": spec, "enums": enums, "children": children, "row": row}
        )

    walk(target_output_spec, name, "", False)
    return plans


def check_schema_names(target_output_spec: dict[str, Any], name: str) -> None:
    """Raise ValueError when the spec cannot become a schema module: a class or field
    name the source cannot carry, or rows inside rows. The scaffolder runs it before it
    writes any file."""
    _model_plan(target_output_spec, name)


def _safe_enum_member(v: str) -> str:
    """Convert an allowed value to a valid Python identifier for an Enum member."""
    s = re.sub(r"[^a-zA-Z0-9_]", "_", str(v))
    # Enum members must not start with a digit. A leading underscore gets the
    # prefix too: Python's Enum reserves _sunder_ names (a value "-x-" would give
    # "_X_") and does not make a member of a __dunder__ name.
    if s and (s[0].isdigit() or s[0] == "_"):
        s = f"V_{s}"
    return s.upper() or "UNKNOWN"


def _enum_members(values: list[str]) -> list[tuple[str, str]]:
    """(member name, value) per distinct allowed value, each name used once.

    Two values can give the same name ("a b" and "a-b" both give A_B); the later
    one gets a number, so neither value is lost from the Enum.
    """
    members: list[tuple[str, str]] = []
    used: set[str] = set()
    for value in dict.fromkeys(values):
        base = _safe_enum_member(value)
        name, n = base, 2
        while name in used:
            name, n = f"{base}_{n}", n + 1
        used.add(name)
        members.append((name, value))
    return members


def _enum_name(field: str) -> str:
    return "".join(w.title() for w in field.split("_")) + "Enum"


def _enum_names(
    fields: list[str],
    allowed_values: dict[str, Any],
    prefix: str = "",
    taken: set[str] | None = None,
) -> dict[str, str]:
    """The Enum class name per field with allowed values, each name used once.

    Two fields can give the same name ("a_b" and "a__b" both give ABEnum); the
    later one gets a number, so neither Enum replaces the other. ``taken`` holds
    the module's other class names, and gets these added; ``prefix`` is a row
    model's name, so its Enums say whose they are.
    """
    used = taken if taken is not None else set()
    names: dict[str, str] = {}
    for field in fields:
        vals = allowed_values.get(field, [])
        if not (vals and all(isinstance(v, str) for v in vals)):
            continue
        base = prefix + _enum_name(field)
        name, n = base, 2
        while name in names.values() or name in used:
            name, n = f"{base[: -len('Enum')]}{n}Enum", n + 1
        names[field] = name
        used.add(name)
    return names


def _source_name(value: Any, what: str) -> str:
    """A name the schema source can carry as written: an identifier, not a keyword."""
    if not (isinstance(value, str) and value.isidentifier() and not keyword.iskeyword(value)):
        raise ValueError(f"the output schema's {what} {value!r} is not a valid Python name")
    return value


def _model_source(plan: dict[str, Any]) -> tuple[list[str], bool]:
    """The Enum classes and the model class of one planned model, and whether the
    model needs the Decimal helper."""
    spec = plan["spec"]
    fields: list[str] = spec.get("fields", [])
    field_types: dict[str, str] = spec.get("field_types", {})
    required_fields: list[str] = spec.get("required_fields", [])
    field_descriptions: dict[str, str] = spec.get("field_descriptions", {})
    allowed_values: dict[str, Any] = spec.get("allowed_values", {})
    enum_names: dict[str, str] = plan["enums"]
    children: dict[str, str] = plan["children"]

    blocks = []
    for field in fields:
        vals = allowed_values.get(field, [])
        if field in enum_names:
            enum_name = enum_names[field]
            members = "\n".join(f"    {m} = {v!r}" for m, v in _enum_members(vals))
            blocks.append(f"class {enum_name}(str, Enum):\n{members}\n")

    field_lines = []
    needs_decimal_helper = False
    for field in fields:
        desc = str(field_descriptions.get(field) or "")
        if field in children:
            # A list of rows, never None: an output without rows has an empty list.
            child = children[field]
            desc = _container_description(spec, field)
            if field in required_fields:
                arg = f"Field(description={desc!r})" if desc else "..."
            else:
                arg = (
                    f"Field(default_factory=list, description={desc!r})"
                    if desc
                    else "Field(default_factory=list)"
                )
            field_lines.append(f"    {field}: List[{child}] = {arg}")
            continue
        py_type = _py_type(field_types.get(field, "string"))
        if field in enum_names:
            py_type = enum_names[field]

        # Use Field(description=...) so the description propagates into JSON Schema
        field_arg = f"Field(description={desc!r})" if desc else "..."
        is_decimal = py_type == "Decimal"

        if field in required_fields:
            if is_decimal:
                needs_decimal_helper = True
                field_lines.append(f"    {field}: DecimalField = {field_arg}")
            else:
                field_lines.append(f"    {field}: {py_type} = {field_arg}")
        elif is_decimal:
            # OptionalDecimalField already includes `| None` -- wrapping it
            # again in Optional[...] would double-wrap into
            # Optional[Annotated[Decimal | None, ...]], which pydantic still
            # validates correctly but which introspection-based schema
            # writers (generate_schema.py, run_poc.py.tmpl) cannot unwrap.
            needs_decimal_helper = True
            default_arg = f"Field(default=None, description={desc!r})" if desc else "None"
            field_lines.append(f"    {field}: OptionalDecimalField = {default_arg}")
        else:
            default_arg = f"Field(default=None, description={desc!r})" if desc else "None"
            field_lines.append(f"    {field}: Optional[{py_type}] = {default_arg}")

    body = "\n".join(field_lines) if field_lines else "    pass"
    lines = [f"class {plan['name']}(BaseModel):"]
    if plan["row"]:
        # A row is a named model that forbids other keys, as SKILL.md asks for every
        # nested object (a bare dict is rejected by Azure's structured output).
        lines += ["    model_config = ConfigDict(extra='forbid')", ""]
    lines.append(body)
    blocks.append("\n".join(lines) + "\n")
    # Pydantic v2 requires model_rebuild() when the model references
    # types (e.g. Enums, or the Decimal safety aliases) defined in the same
    # module -- a caller that runs this source into a bare dict namespace
    # otherwise gets "class is not fully defined" for DecimalField /
    # OptionalDecimalField.
    if enum_names or needs_decimal_helper or children:
        blocks.append(f"{plan['name']}.model_rebuild()\n")
    return blocks, needs_decimal_helper


def build_pydantic_model(target_output_spec: dict[str, Any], schema_name: str | None = None) -> str:
    """Generate output_schema.py content -- a typed Pydantic model.

    This is a documentation/reference artefact.  The runtime uses it as a
    schema hint; the GAIK module generates its own internal schema from the
    user_requirements string. A spec with a ``nested`` block also gets one row
    model per repeated collection, defined before the model that lists it.
    """
    target_output_spec = _normalize_spec(target_output_spec)
    name = schema_name or target_output_spec.get("schema_name") or "OutputSchema"
    plans = _model_plan(target_output_spec, name)
    rows = [plan for plan in plans if plan["row"]]

    # Do NOT include `from __future__ import annotations` (PEP 563).
    # That import defers all annotation evaluation, turning Optional[str] into
    # the string "Optional[str]". Pydantic v2 cannot resolve deferred strings
    # back to real types and raises "not fully defined". Eager evaluation (the
    # default without that import) is required for Pydantic v2 to build the
    # model correctly. The imports cover every model in the file, rows included.
    imports = [f"from pydantic import BaseModel, {'ConfigDict, ' if rows else ''}Field"]
    typing_names = []
    if rows:
        typing_names.append("List")
    if any(
        f not in plan["spec"].get("required_fields", [])
        for plan in plans
        for f in plan["spec"].get("fields", [])
    ):
        typing_names.append("Optional")
    if typing_names:
        imports.append(f"from typing import {', '.join(typing_names)}")
    if any(
        f in plan["spec"].get("allowed_values", {})
        for plan in plans
        for f in plan["spec"].get("fields", [])
    ):
        imports.append("from enum import Enum")

    sources = [_model_source(plan) for plan in plans]
    root_blocks, _ = sources[-1]
    parts = [
        (
            '"""Generated output schema.\n\nGenerated by GAIK Solution Configuration Wizard V2.'
            '\nDo not hand-edit -- regenerate via scaffold_poc.py.\n"""'
        ),
        "",
        "\n".join(imports),
        "",
    ]
    if any(needs for _, needs in sources):
        parts += ["", _DECIMAL_HELPER_SOURCE.strip(), ""]
    # Enum definitions must come before the model class so Pydantic can resolve them,
    # and a row model before the model that lists it.
    root_enums = root_blocks[: len(plans[-1]["enums"])]
    if root_enums:
        parts += [""] + root_enums
    for blocks, _ in sources[:-1]:
        parts += [""] + blocks
    parts += ["", *root_blocks[len(root_enums) :]]
    return "\n".join(parts).rstrip("\n") + "\n"


# Maps our field_types vocabulary to the AllowedTypes Literal expected by
# ExtractionRequirements / FieldSpec in gaik.software_components.extractor.schema
_ALLOWED_TYPES_MAP: dict[str, str] = {
    "string": "str",
    "str": "str",
    "text": "str",
    "integer": "int",
    "int": "int",
    "number": "float",
    "float": "float",
    "decimal": "decimal",
    "boolean": "bool",
    "bool": "bool",
    "list": "list[str]",
    "array": "list[str]",
    "date": "date",
    "datetime": "date",
    "object": "list[dict]",
    "dict": "list[dict]",
}
_DEFAULT_ALLOWED_TYPE = "str"


def _to_allowed_type(raw_type: str) -> str:
    return _ALLOWED_TYPES_MAP.get(raw_type.lower().strip(), _DEFAULT_ALLOWED_TYPE)


def build_requirements_json(
    target_output_spec: dict[str, Any],
    use_case_name: str = "",
    schema_class_name: str | None = None,
) -> dict[str, Any]:
    """Generate the requirements JSON in the format expected by load_schema().

    save_schema() / load_schema() contract (gaik audio_to_structured_data pipeline):
        {
            "model_name": "<PydanticClassName>",
            "requirements": {
                "use_case_name": "...",
                "fields": [
                    {
                        "field_name": "<snake_case>",
                        "field_type": "<AllowedTypes>",
                        "description": "...",
                        "required_in_output": true/false,
                        "nullable": true/false,
                        "enum": [...] | null,
                        "default": null,
                        "has_explicit_default": false,
                        "required": true/false,
                        "pattern": null,
                        "format": null
                    }
                ]
            }
        }
    """
    target_output_spec = _normalize_spec(target_output_spec)
    fields: list[str] = target_output_spec.get("fields", [])
    field_types: dict[str, str] = target_output_spec.get("field_types", {})
    required_fields: list[str] = target_output_spec.get("required_fields", [])
    field_descriptions: dict[str, str] = target_output_spec.get("field_descriptions", {})
    allowed_values: dict[str, Any] = target_output_spec.get("allowed_values", {})
    class_name = schema_class_name or target_output_spec.get("schema_name") or "OutputSchema"

    field_specs = []
    for f in fields:
        is_required = f in required_fields
        raw_type = field_types.get(f, "string")
        allowed = allowed_values.get(f, [])
        enum_vals = [str(v) for v in allowed] if allowed else None
        field_specs.append(
            {
                "field_name": f,
                "field_type": _to_allowed_type(raw_type),
                "description": field_descriptions.get(f, f.replace("_", " ").capitalize()),
                "required_in_output": is_required,
                "nullable": not is_required,
                "enum": enum_vals,
                "default": None,
                "has_explicit_default": False,
                "required": is_required,
                "pattern": None,
                "format": None,
            }
        )

    name = use_case_name or class_name
    nested = _nested_specs(target_output_spec)
    if not nested:
        return {
            "model_name": class_name,
            "requirements": {"use_case_name": name, "fields": field_specs},
        }

    # CompositeExtractionRequirements: the parent record plus one entry per
    # repeated child collection. gaik's load_schema() already recognises this
    # shape -- it switches on structure_type. The container itself is not a
    # parent field: it is the list the children go into.
    parent_specs = [fs for fs in field_specs if fs["field_name"] not in nested]
    children = []
    for container, child_spec in nested.items():
        if _nested_specs(_normalize_spec(child_spec)):
            raise ValueError(
                f"the {container} rows have rows of their own; only one level of nested "
                "rows is supported"
            )
        child = build_requirements_json(child_spec, use_case_name=container)
        children.append(
            {
                "container_name": container,
                "container_description": (
                    _container_description(target_output_spec, container)
                    or f"One entry per {container.replace('_', ' ').rstrip('s')}"
                ),
                "requirements": child["requirements"],
            }
        )

    return {
        "model_name": class_name,
        "requirements_type": "parent_with_nested_list",
        "requirements": {
            "structure_type": "parent_with_nested_list",
            "parent_requirements": {"use_case_name": name, "fields": parent_specs},
            "children": children,
        },
    }


def _model_from_spec(target_output_spec: dict[str, Any], name: str) -> Any:
    """The model that build_pydantic_model()'s source defines, built from the spec as data.

    write_schema_files() needs the model for its JSON Schema and its saved
    description (output_schema_model.json). Building it
    with pydantic.create_model keeps the spec's text as values: no source code
    is assembled from it and nothing is executed. Field for field it follows
    build_pydantic_model(), so the JSON Schema is the same.
    """
    from decimal import Decimal
    from enum import Enum
    from typing import Annotated

    from pydantic import BeforeValidator, ConfigDict, Field, WithJsonSchema, create_model

    noise = re.compile(r"(?i)\b(EUR|USD|GBP|JPY|CHF|SEK|NOK|DKK|CAD|AUD|INR)\b|[€$£¥₹]")
    single = re.compile(r"^[-+]?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$")

    # Named like gaik's cleaner: saved_schema refuses a Decimal cleaner under
    # another name, since the rebuilt field uses gaik's.
    def _clean_decimal_string(v: Any) -> Any:
        if not isinstance(v, str):
            return v
        text = noise.sub("", v.strip()).strip()
        if not text or not single.match(text):
            return None
        return text.replace(",", "")

    decimal_field = Annotated[
        Decimal, WithJsonSchema({"type": "string"}), BeforeValidator(_clean_decimal_string)
    ]
    optional_decimal_field = Annotated[
        Decimal | None,
        WithJsonSchema({"anyOf": [{"type": "string"}, {"type": "null"}]}),
        BeforeValidator(_clean_decimal_string),
    ]
    simple = {"str": str, "int": int, "float": float, "bool": bool, "list[str]": list[str]}

    models: dict[str, Any] = {}
    for plan in _model_plan(target_output_spec, name):
        spec = plan["spec"]
        fields: list[str] = spec.get("fields", [])
        field_types: dict[str, str] = spec.get("field_types", {})
        required_fields: list[str] = spec.get("required_fields", [])
        descriptions: dict[str, str] = spec.get("field_descriptions", {})
        allowed_values: dict[str, Any] = spec.get("allowed_values", {})
        enum_names: dict[str, str] = plan["enums"]

        definitions: dict[str, Any] = {}
        for field in fields:
            desc = descriptions.get(field, "")
            if field in plan["children"]:
                desc = _container_description(spec, field)
            required = field in required_fields
            described = {"description": desc} if desc else {}
            if field in plan["children"]:
                row = models[plan["children"][field]]
                if required:
                    definitions[field] = (list[row], Field(**described) if desc else ...)
                else:
                    definitions[field] = (list[row], Field(default_factory=list, **described))
                continue
            py_type = _py_type(field_types.get(field, "string"))
            vals = allowed_values.get(field, [])
            if field in enum_names:
                kind: Any = Enum(enum_names[field], _enum_members(vals), type=str)
            elif py_type == "Decimal":
                kind = decimal_field if required else optional_decimal_field
            else:
                kind = simple.get(py_type, str)
            if required:
                definitions[field] = (kind, Field(**described) if desc else ...)
            elif py_type == "Decimal" and kind is optional_decimal_field:
                definitions[field] = (kind, Field(default=None, **described) if desc else None)
            else:
                definitions[field] = (
                    kind | None,
                    Field(default=None, **described) if desc else None,
                )

        config = {"__config__": ConfigDict(extra="forbid")} if plan["row"] else {}
        models[plan["name"]] = create_model(plan["name"], **config, **definitions)
    return models[name]


def write_schema_files(
    target_output_spec: dict[str, Any],
    schema_name: str | None,
    output_dir: Path,
    use_case_name: str = "",
) -> dict[str, Path]:
    """Write all schema artefacts into output_dir/schemas/.

    File layout that load_schema(schema_dir, "output_schema") expects:
        schemas/output_schema_model.json          <- the model as data (what is loaded)
        schemas/output_schema.py                  <- Pydantic model; class name = schema_name
        schemas/output_schema_requirements.json   <- {"model_name": ..., "requirements": ...}

    The class name (schema_name) in output_schema.py MUST match "model_name" in the
    requirements JSON so that load_schema() can do getattr(module, model_name).

    Returns a dict of {artefact_name: path}.
    """
    schemas_dir = output_dir / "schemas"
    schemas_dir.mkdir(parents=True, exist_ok=True)

    class_name = schema_name or target_output_spec.get("schema_name") or "OutputSchema"
    results: dict[str, Path] = {}

    # The model is built from the spec as data, never by running output_schema.py.
    model_cls = _model_from_spec(target_output_spec, class_name)

    # output_schema_model.json -- what load_schema() rebuilds the model from in
    # gaik releases that load saved schemas as data (output_schema.py is then
    # never imported). Older gaik has no saved_schema module and reads the .py.
    # It is described before any file is written, so a model the saved format
    # refuses leaves the folder as it was instead of half-written.
    try:
        from gaik.software_components.extractor.saved_schema import describe_model
    except ImportError:
        describe_model = None
    model_description = describe_model(model_cls) if describe_model is not None else None

    # output_schema.py -- class must be named class_name so load_schema can find it
    py_content = build_pydantic_model(target_output_spec, class_name)
    py_path = schemas_dir / "output_schema.py"
    py_path.write_text(py_content, encoding="utf-8")
    results["output_schema.py"] = py_path

    # output_schema.json (human-readable JSON Schema; best-effort).
    try:
        json_schema = model_cls.model_json_schema()
        json_path = schemas_dir / "output_schema.json"
        json_path.write_text(json.dumps(json_schema, indent=2), encoding="utf-8")
        results["output_schema.json"] = json_path
    except Exception:
        pass

    model_path = schemas_dir / "output_schema_model.json"
    if model_description is not None:
        model_path.write_text(
            json.dumps(model_description, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        results["output_schema_model.json"] = model_path
    else:
        # A model file from an earlier run would no longer match the new files.
        model_path.unlink(missing_ok=True)

    # output_schema_requirements.json -- the file load_schema() reads:
    #   load_schema(schema_dir, "output_schema") => schema_dir / "output_schema_requirements.json"
    # Payload: {"model_name": class_name, "requirements": <ExtractionRequirements.model_dump()>}
    req_data = build_requirements_json(target_output_spec, use_case_name, class_name)
    req_path = schemas_dir / "output_schema_requirements.json"
    req_path.write_text(json.dumps(req_data, indent=2), encoding="utf-8")
    results["output_schema_requirements.json"] = req_path

    return results


def write_extraction_requirements(target_output_spec: dict[str, Any], output_dir: Path) -> Path:
    """Write prompts/extraction_requirements.md -- passed as user_requirements at runtime."""
    prompts_dir = output_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    req_text = build_requirements_text(target_output_spec)
    path = prompts_dir / "extraction_requirements.md"
    path.write_text(req_text, encoding="utf-8")
    return path
