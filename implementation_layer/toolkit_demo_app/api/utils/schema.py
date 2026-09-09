"""Shared schema utilities for extractor and pipeline routers.

Handles numeric normalization, schema persistence, and schema code generation.
"""

import hashlib
import importlib.util
import io
import json
import logging
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path
from typing import Any, get_args, get_origin

from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)

SCHEMA_DIR = Path(__file__).parent.parent / "schemas"
SCHEMA_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Numeric normalisation helpers
# ---------------------------------------------------------------------------

_NULL_STRINGS = {"", "-", "N/A", "n/a", "none", "null"}


def _annotation_contains(annotation: Any, target_type: type) -> bool:
    """Return True if *annotation* (possibly a generic alias) contains *target_type*."""
    if annotation is target_type:
        return True

    origin = get_origin(annotation)
    if origin is None:
        return False

    return any(
        arg is not type(None) and _annotation_contains(arg, target_type)
        for arg in get_args(annotation)
    )


def clean_numeric_string(value: str) -> str:
    """Strip currency symbols, whitespace, commas, percent signs and handle accounting negatives."""
    cleaned = value.strip()
    if not cleaned:
        return cleaned

    negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        negative = True
        cleaned = cleaned[1:-1].strip()

    cleaned = cleaned.replace("$", "").replace("EUR", "").replace("eur", "")
    cleaned = cleaned.replace(" ", "").replace(",", "")
    cleaned = cleaned.replace("%", "")

    if negative and cleaned and not cleaned.startswith("-"):
        cleaned = f"-{cleaned}"
    return cleaned


def normalize_float_value(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    if isinstance(value, str):
        cleaned = clean_numeric_string(value)
        if cleaned in _NULL_STRINGS:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return value
    return value


def normalize_int_value(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, (float, Decimal)):
        return int(value)
    if isinstance(value, str):
        cleaned = clean_numeric_string(value)
        if cleaned in _NULL_STRINGS:
            return None
        try:
            return int(float(cleaned))
        except ValueError:
            return value
    return value


def wrap_schema_with_numeric_normalizers(schema: type[BaseModel]) -> type[BaseModel]:
    """Return a subclass with int/float string normalizers.

    Decimal fields deliberately retain the core extractor's conservative
    BeforeValidator. The former website-specific Decimal validator turned
    ambiguous input such as "1 234,56 EUR" into 123456.
    """
    float_fields = [
        name
        for name, field in schema.model_fields.items()
        if _annotation_contains(field.annotation, float)
    ]
    int_fields = [
        name
        for name, field in schema.model_fields.items()
        if _annotation_contains(field.annotation, int)
    ]

    if not any((float_fields, int_fields)):
        return schema

    namespace: dict[str, object] = {}

    if float_fields:

        @field_validator(*float_fields, mode="before", check_fields=False)
        @classmethod
        def _normalize_float_fields(cls, value):
            return normalize_float_value(value)

        namespace["_normalize_float_fields"] = _normalize_float_fields

    if int_fields:

        @field_validator(*int_fields, mode="before", check_fields=False)
        @classmethod
        def _normalize_int_fields(cls, value):
            return normalize_int_value(value)

        namespace["_normalize_int_fields"] = _normalize_int_fields

    wrapped_schema = type(f"{schema.__name__}Normalized", (schema,), namespace)
    wrapped_schema.model_rebuild(force=True)
    return wrapped_schema


# ---------------------------------------------------------------------------
# Schema persistence (save / load generated Pydantic schemas to disk)
# ---------------------------------------------------------------------------


def _clean_schema_dump(raw_dump: str) -> str:
    """Strip header/footer lines from ``print_pydantic_schema`` output."""
    lines = raw_dump.splitlines()
    start_idx = 0
    for i, line in enumerate(lines):
        if line.startswith("class "):
            start_idx = i
            break
    body = lines[start_idx:]
    while body and (set(body[-1].strip()) == {"="} or not body[-1].strip()):
        body.pop()
    return "\n".join(body).strip()


def _sanitize_schema_code(schema_code: str) -> str:
    """Remove fully qualified extractor-schema references from cached modules."""
    return schema_code.replace("gaik.software_components.extractor.schema.", "")


SCHEMA_FORMAT_VERSION = 2


def _iter_model_types(root: type[BaseModel]) -> list[type[BaseModel]]:
    """Return root and all nested Pydantic model types once."""
    models: list[type[BaseModel]] = []
    seen: set[type[BaseModel]] = set()

    def visit(annotation: Any) -> None:
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            if annotation in seen:
                return
            seen.add(annotation)
            models.append(annotation)
            for field in annotation.model_fields.values():
                visit(field.annotation)
            return
        for argument in get_args(annotation):
            if argument is not type(None):
                visit(argument)

    visit(root)
    return models


def _restore_decimal_annotations(
    schema_code: str,
    model: type[BaseModel],
) -> tuple[str, set[str]]:
    """Restore safe Decimal aliases stripped by Pydantic field introspection."""
    from gaik.software_components.extractor.schema import decimal_field_repr

    replacements: dict[str, dict[str, str]] = {}
    for model_type in _iter_model_types(model):
        decimal_fields = {
            name: representation
            for name, field in model_type.model_fields.items()
            if (representation := decimal_field_repr(field.annotation)) is not None
        }
        if decimal_fields:
            replacements[model_type.__name__] = decimal_fields

    if not replacements:
        return schema_code, set()

    current_model: str | None = None
    lines = schema_code.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("class "):
            current_model = line.removeprefix("class ").split("(", 1)[0].strip()
            continue
        if current_model not in replacements:
            continue
        for field_name, representation in replacements[current_model].items():
            prefix = f"    {field_name}: "
            if line.startswith(prefix) and " = Field" in line:
                field_call = line.index(" = Field")
                lines[index] = f"{prefix}{representation}{line[field_call:]}"
                break

    aliases = {
        representation
        for model_replacements in replacements.values()
        for representation in model_replacements.values()
    }
    return "\n".join(lines), aliases


def schema_to_python_source(model: type[BaseModel]) -> str:
    """Render a model as importable Python without writing it to disk."""
    from gaik.software_components.extractor.schema import print_pydantic_schema

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        print_pydantic_schema(model, title="Saved Schema")

    schema_code = _sanitize_schema_code(_clean_schema_dump(buffer.getvalue()))
    for model_type in _iter_model_types(model):
        schema_code = schema_code.replace(f"{model_type.__module__}.", "")
    schema_code, decimal_aliases = _restore_decimal_annotations(schema_code, model)
    standard_imports: list[str] = []
    if "decimal." in schema_code:
        standard_imports.append("import decimal")
    if "Literal[" in schema_code:
        standard_imports.append("from typing import Literal")

    third_party_imports: list[str] = []
    if decimal_aliases:
        third_party_imports.append(
            "from gaik.software_components.extractor import " + ", ".join(sorted(decimal_aliases))
        )
    third_party_imports.append("from pydantic import BaseModel, ConfigDict, Field")

    imports = "\n".join(standard_imports)
    if standard_imports:
        imports += "\n\n"
    imports += "\n".join(third_party_imports)

    return f'''"""
Auto-generated schema module (do not edit manually).
"""

{imports}

{schema_code}
'''


def save_schema_to_python(model: type[BaseModel], path: Path) -> None:
    """Persist a model without losing the core Decimal schema and validator."""
    path.write_text(schema_to_python_source(model), encoding="utf-8")


def load_saved_schema(path: Path, model_name: str) -> type[BaseModel]:
    """Load one model class from a persisted schema module."""
    source = path.read_text(encoding="utf-8")
    sanitized = _sanitize_schema_code(source)
    if sanitized != source:
        path.write_text(sanitized, encoding="utf-8")
        logger.info("Sanitized cached schema module: %s", path)

    spec = importlib.util.spec_from_file_location(model_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader is not None
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return getattr(module, model_name)


def save_requirements(
    requirements: Any,
    model_name: str,
    path: Path,
    *,
    user_requirements: str | None = None,
) -> None:
    """Persist requirements with a schema-format version for cache invalidation."""
    payload = {
        "schema_format_version": SCHEMA_FORMAT_VERSION,
        "model_name": model_name,
        "requirements": requirements.model_dump(),
    }
    if user_requirements is not None:
        payload["user_requirements"] = user_requirements
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_saved_requirements(
    path: Path,
    *,
    expected_user_requirements: str | None = None,
) -> tuple[str, Any] | None:
    """Load current-format requirements, returning None for a stale cache."""
    from gaik.software_components.extractor import (
        CompositeExtractionRequirements,
        ExtractionRequirements,
    )

    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_format_version") != SCHEMA_FORMAT_VERSION:
        return None
    if (
        expected_user_requirements is not None
        and data.get("user_requirements") != expected_user_requirements
    ):
        return None

    raw_requirements = data["requirements"]
    requirements_type = (
        CompositeExtractionRequirements
        if "parent_requirements" in raw_requirements and "children" in raw_requirements
        else ExtractionRequirements
    )
    requirements = requirements_type.model_validate(raw_requirements)
    return data["model_name"], requirements


def schema_paths(schema_key: str) -> tuple[Path, Path]:
    """Return (schema_module_path, requirements_json_path) for *schema_key*."""
    safe_key = (
        "".join(c if c.isalnum() or c in {"_", "-"} else "_" for c in schema_key).strip("_")
        or "schema"
    )
    return (
        SCHEMA_DIR / f"{safe_key}_schema.py",
        SCHEMA_DIR / f"{safe_key}_requirements.json",
    )


def save_schema(
    schema: type[BaseModel],
    requirements: Any,
    schema_key: str,
    user_requirements: str,
) -> None:
    """Persist a generated schema and matching versioned requirements."""
    schema_path, req_path = schema_paths(schema_key)
    save_schema_to_python(schema, schema_path)
    save_requirements(
        requirements,
        schema.__name__,
        req_path,
        user_requirements=user_requirements,
    )


def load_schema(
    schema_key: str,
    user_requirements: str,
) -> tuple[type[BaseModel], Any] | None:
    """Load a persisted schema from disk.

    Returns ``(normalised_schema_class, requirements)`` or ``None`` if no
    matching persisted schema exists.
    """
    schema_path, req_path = schema_paths(schema_key)
    if not (schema_path.exists() and req_path.exists()):
        return None

    loaded_requirements = load_saved_requirements(
        req_path,
        expected_user_requirements=user_requirements,
    )
    if loaded_requirements is None:
        return None

    model_name, requirements = loaded_requirements
    schema = load_saved_schema(schema_path, model_name)
    return wrap_schema_with_numeric_normalizers(schema), requirements


# ---------------------------------------------------------------------------
# Schema ID helper (hash-based, used by the extractor router)
# ---------------------------------------------------------------------------


def schema_id_from_requirements(user_requirements: str) -> str:
    """Return a short deterministic ID for the given requirements text."""
    return hashlib.sha256(user_requirements.encode()).hexdigest()[:16]
