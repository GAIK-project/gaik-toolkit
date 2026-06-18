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
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Python type mapping from JSON-style type names
# ---------------------------------------------------------------------------

import re


_TYPE_MAP: Dict[str, str] = {
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
    # The wizard must define a named Pydantic sub-model with
    # model_config = ConfigDict(extra='forbid') for each nested object field.
    # Until then the field is typed as str so the PoC at least parses.
    "object": "str",
    "dict": "str",
    "enum": "str",
}


def _py_type(type_name: str) -> str:
    return _TYPE_MAP.get(type_name.lower().strip(), "str")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_spec(target_output_spec: Dict[str, Any]) -> Dict[str, Any]:
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

    flat_fields: List[str] = []
    extra_descriptions: Dict[str, str] = {}
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
        normalised["required_fields"] = [
            r.get("id", r.get("title", "")) for r in raw_required
        ]
    return normalised


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_requirements_text(target_output_spec: Dict[str, Any]) -> str:
    """Build a plain-text user requirements string from target_output_spec.

    This is passed to AudioToStructuredData / DocumentsToStructuredData as
    user_requirements.  It mirrors the format used in the official examples.
    """
    target_output_spec = _normalize_spec(target_output_spec)
    fields: List[str] = target_output_spec.get("fields", [])
    field_types: Dict[str, str] = target_output_spec.get("field_types", {})
    required_fields: List[str] = target_output_spec.get("required_fields", [])
    field_descriptions: Dict[str, str] = target_output_spec.get("field_descriptions", {})
    allowed_values: Dict[str, List[str]] = target_output_spec.get("allowed_values", {})
    missing_value_policy: str = target_output_spec.get(
        "missing_value_policy", 'Return an empty string ("") if the value is not present.'
    )

    lines = [
        "Extract the following fields from the provided content.\n",
        f"If a field cannot be determined, apply this policy: {missing_value_policy}\n",
    ]

    for i, field in enumerate(fields, 1):
        req_marker = "REQUIRED" if field in required_fields else "OPTIONAL"
        type_str = field_types.get(field, "string")
        desc = field_descriptions.get(field, "")
        allowed = allowed_values.get(field, [])

        line = f"{i}. {field} ({type_str}, {req_marker})"
        if desc:
            line += f": {desc}"
        if allowed:
            line += f" -- allowed values: {', '.join(str(v) for v in allowed)}"
        lines.append(line)

    return "\n".join(lines)


def build_pydantic_model(
    target_output_spec: Dict[str, Any], schema_name: Optional[str] = None
) -> str:
    """Generate output_schema.py content -- a typed Pydantic model.

    This is a documentation/reference artefact.  The runtime uses it as a
    schema hint; the GAIK module generates its own internal schema from the
    user_requirements string.
    """
    target_output_spec = _normalize_spec(target_output_spec)
    fields: List[str] = target_output_spec.get("fields", [])
    field_types: Dict[str, str] = target_output_spec.get("field_types", {})
    required_fields: List[str] = target_output_spec.get("required_fields", [])
    field_descriptions: Dict[str, str] = target_output_spec.get("field_descriptions", {})
    allowed_values: Dict[str, Any] = target_output_spec.get("allowed_values", {})
    name = schema_name or target_output_spec.get("schema_name") or "OutputSchema"

    def _safe_enum_member(v: str) -> str:
        """Convert an allowed value to a valid Python identifier for an Enum member."""
        s = re.sub(r"[^a-zA-Z0-9_]", "_", str(v))
        # Enum members must not start with a digit
        if s and s[0].isdigit():
            s = f"V_{s}"
        return s.upper() or "UNKNOWN"

    # Do NOT include `from __future__ import annotations` (PEP 563).
    # That import defers all annotation evaluation, turning Optional[str] into
    # the string "Optional[str]". Pydantic v2 cannot resolve deferred strings
    # back to real types and raises "not fully defined". Eager evaluation (the
    # default without that import) is required for Pydantic v2 to build the
    # model correctly.
    imports = ["from pydantic import BaseModel, Field"]
    has_optional = any(f not in required_fields for f in fields)
    has_enum = any(f in allowed_values for f in fields)
    if has_optional:
        imports.append("from typing import Optional")
    if has_enum:
        imports.append("from enum import Enum")

    enum_blocks = []
    for field in fields:
        vals = allowed_values.get(field, [])
        if vals and all(isinstance(v, str) for v in vals):
            enum_name = "".join(w.title() for w in field.split("_")) + "Enum"
            members = "\n".join(f'    {_safe_enum_member(v)} = "{v}"' for v in vals)
            enum_blocks.append(f"class {enum_name}(str, Enum):\n{members}\n")

    field_lines = []
    for field in fields:
        py_type = _py_type(field_types.get(field, "string"))
        vals = allowed_values.get(field, [])
        if vals and all(isinstance(v, str) for v in vals):
            enum_name = "".join(w.title() for w in field.split("_")) + "Enum"
            py_type = enum_name

        desc = field_descriptions.get(field, "")
        # Use Field(description=...) so the description propagates into JSON Schema
        field_arg = f'Field(description="{desc}")' if desc else "..."

        if field in required_fields:
            field_lines.append(f"    {field}: {py_type} = {field_arg}")
        else:
            default_arg = f'Field(default=None, description="{desc}")' if desc else "None"
            field_lines.append(f"    {field}: Optional[{py_type}] = {default_arg}")

    body = "\n".join(field_lines) if field_lines else "    pass"

    parts = [
        '"""Generated output schema.\n\nGenerated by GAIK Solution Configuration Wizard V2.\nDo not hand-edit -- regenerate via scaffold_poc.py.\n"""',
        "",
        "\n".join(imports),
        "",
    ]
    # Enum definitions must come before the model class so Pydantic can resolve them
    if enum_blocks:
        parts += [""] + enum_blocks
    parts += [
        "",
        f"class {name}(BaseModel):",
        body,
        "",
    ]
    # Pydantic v2 requires model_rebuild() when the model references
    # types (e.g. Enums) defined in the same module / exec block.
    if enum_blocks:
        parts += [f"{name}.model_rebuild()", ""]
    return "\n".join(parts)


# Maps our field_types vocabulary to the AllowedTypes Literal expected by
# ExtractionRequirements / FieldSpec in gaik.software_components.extractor.schema
_ALLOWED_TYPES_MAP: Dict[str, str] = {
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
    target_output_spec: Dict[str, Any],
    use_case_name: str = "",
    schema_class_name: Optional[str] = None,
) -> Dict[str, Any]:
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
    fields: List[str] = target_output_spec.get("fields", [])
    field_types: Dict[str, str] = target_output_spec.get("field_types", {})
    required_fields: List[str] = target_output_spec.get("required_fields", [])
    field_descriptions: Dict[str, str] = target_output_spec.get("field_descriptions", {})
    allowed_values: Dict[str, Any] = target_output_spec.get("allowed_values", {})
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

    return {
        "model_name": class_name,
        "requirements": {
            "use_case_name": use_case_name or class_name,
            "fields": field_specs,
        },
    }


def write_schema_files(
    target_output_spec: Dict[str, Any],
    schema_name: Optional[str],
    output_dir: Path,
    use_case_name: str = "",
) -> Dict[str, Path]:
    """Write all schema artefacts into output_dir/schemas/.

    File layout that load_schema(schema_dir, "output_schema") expects:
        schemas/output_schema.py                  <- Pydantic model; class name = schema_name
        schemas/output_schema_requirements.json   <- {"model_name": ..., "requirements": ...}

    The class name (schema_name) in output_schema.py MUST match "model_name" in the
    requirements JSON so that load_schema() can do getattr(module, model_name).

    Returns a dict of {artefact_name: path}.
    """
    schemas_dir = output_dir / "schemas"
    schemas_dir.mkdir(parents=True, exist_ok=True)

    class_name = schema_name or target_output_spec.get("schema_name") or "OutputSchema"
    results: Dict[str, Path] = {}

    # output_schema.py -- class must be named class_name so load_schema can find it
    py_content = build_pydantic_model(target_output_spec, class_name)
    py_path = schemas_dir / "output_schema.py"
    py_path.write_text(py_content, encoding="utf-8")
    results["output_schema.py"] = py_path

    # output_schema.json (human-readable JSON Schema; best-effort)
    try:
        ns: Dict[str, Any] = {}
        exec(compile(py_content, "<schema>", "exec"), ns)
        model_cls = ns.get(class_name)
        if model_cls and hasattr(model_cls, "model_json_schema"):
            json_schema = model_cls.model_json_schema()
            json_path = schemas_dir / "output_schema.json"
            json_path.write_text(json.dumps(json_schema, indent=2), encoding="utf-8")
            results["output_schema.json"] = json_path
    except Exception:
        pass

    # output_schema_requirements.json -- the file load_schema() reads:
    #   load_schema(schema_dir, "output_schema") => schema_dir / "output_schema_requirements.json"
    # Payload: {"model_name": class_name, "requirements": <ExtractionRequirements.model_dump()>}
    req_data = build_requirements_json(target_output_spec, use_case_name, class_name)
    req_path = schemas_dir / "output_schema_requirements.json"
    req_path.write_text(json.dumps(req_data, indent=2), encoding="utf-8")
    results["output_schema_requirements.json"] = req_path

    return results


def write_extraction_requirements(target_output_spec: Dict[str, Any], output_dir: Path) -> Path:
    """Write prompts/extraction_requirements.md -- passed as user_requirements at runtime."""
    prompts_dir = output_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    req_text = build_requirements_text(target_output_spec)
    path = prompts_dir / "extraction_requirements.md"
    path.write_text(req_text, encoding="utf-8")
    return path
