"""Shared schema utilities for extractor and pipeline routers.

Handles numeric normalization, schema persistence, and schema code generation.
"""

import hashlib
import importlib.util
import io
import json
import logging
from contextlib import redirect_stdout
from decimal import Decimal, InvalidOperation
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


def normalize_decimal_value(value: Any) -> Any:
    if value is None or isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = clean_numeric_string(value)
        if cleaned in _NULL_STRINGS:
            return None
        try:
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return value
    return value


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
    """Return a subclass of *schema* with Pydantic ``field_validator``s that
    clean and coerce numeric strings before validation."""
    decimal_fields = [
        name for name, field in schema.model_fields.items()
        if _annotation_contains(field.annotation, Decimal)
    ]
    float_fields = [
        name for name, field in schema.model_fields.items()
        if _annotation_contains(field.annotation, float)
    ]
    int_fields = [
        name for name, field in schema.model_fields.items()
        if _annotation_contains(field.annotation, int)
    ]

    if not any((decimal_fields, float_fields, int_fields)):
        return schema

    namespace: dict[str, object] = {}

    if decimal_fields:
        @field_validator(*decimal_fields, mode="before", check_fields=False)
        @classmethod
        def _normalize_decimal_fields(cls, value):
            return normalize_decimal_value(value)

        namespace["_normalize_decimal_fields"] = _normalize_decimal_fields

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


_SCHEMA_MODULE_TEMPLATE = '''\
"""
Auto-generated schema module (do not edit manually).
"""

import decimal
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, ConfigDict

{schema_code}
'''


def schema_paths(schema_key: str) -> tuple[Path, Path]:
    """Return (schema_module_path, requirements_json_path) for *schema_key*."""
    safe_key = "".join(
        c if c.isalnum() or c in {"_", "-"} else "_" for c in schema_key
    ).strip("_") or "schema"
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
    """Persist a generated schema to disk so it can be reloaded later."""
    from gaik.software_components.extractor.schema import print_pydantic_schema

    schema_path, req_path = schema_paths(schema_key)

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        print_pydantic_schema(schema, title="Saved Schema")

    schema_code = _sanitize_schema_code(_clean_schema_dump(buffer.getvalue()))
    schema_path.write_text(
        _SCHEMA_MODULE_TEMPLATE.format(schema_code=schema_code),
        encoding="utf-8",
    )

    payload = {
        "model_name": schema.__name__,
        "requirements": requirements.model_dump(),
        "user_requirements": user_requirements,
    }
    req_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_schema(
    schema_key: str,
    user_requirements: str,
) -> tuple[type[BaseModel], Any] | None:
    """Load a persisted schema from disk.

    Returns ``(normalised_schema_class, requirements)`` or ``None`` if no
    matching persisted schema exists.
    """
    from gaik.software_components.extractor import ExtractionRequirements

    schema_path, req_path = schema_paths(schema_key)
    if not (schema_path.exists() and req_path.exists()):
        return None

    data = json.loads(req_path.read_text(encoding="utf-8"))
    if data.get("user_requirements") != user_requirements:
        return None

    source = schema_path.read_text(encoding="utf-8")
    sanitized = _sanitize_schema_code(source)
    if sanitized != source:
        schema_path.write_text(sanitized, encoding="utf-8")
        logger.info("Sanitized cached schema module: %s", schema_path)

    model_name = data["model_name"]
    requirements = ExtractionRequirements(**data["requirements"])
    spec = importlib.util.spec_from_file_location(model_name, schema_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader is not None
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    schema = getattr(module, model_name)
    return wrap_schema_with_numeric_normalizers(schema), requirements


# ---------------------------------------------------------------------------
# Schema ID helper (hash-based, used by the extractor router)
# ---------------------------------------------------------------------------

def schema_id_from_requirements(user_requirements: str) -> str:
    """Return a short deterministic ID for the given requirements text."""
    return hashlib.sha256(user_requirements.encode()).hexdigest()[:16]
