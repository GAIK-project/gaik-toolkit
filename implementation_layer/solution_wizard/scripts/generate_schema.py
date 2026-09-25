#!/usr/bin/env python3
"""Generate the extraction schema using the GAIK SchemaGenerator.

Called once during Phase 5 (Schema Design) of the wizard conversation.
The wizard presents the generated schema to the user for review; the user
approves or requests changes; approved changes are incorporated by the
wizard directly (no second SchemaGenerator call). The approved schema is
then saved and reused by run_poc.py via load_schema().

Flow:
    Phase 5 in SKILL.md:
        1. Call this script to generate the schema from extraction_requirements.md
        2. Present output_schema.py to the user for review
        3. User approves or requests changes (wizard edits directly, no re-generation)
        4. Confirmed schema is already saved -- scaffold_poc.py will use it as-is

Usage:
    python scripts/generate_schema.py \\
        --requirements poc/prompts/extraction_requirements.md \\
        --schema-name MaintenanceTicket \\
        --output-dir poc/
        [--provider azure|openai|google|aitta|litellm|...]
        [--use-azure / --no-azure]
        [--model gpt-6-luna]
        [--base-url https://your-inference-server.example/v1]

An explicit --provider overrides the legacy Azure flags. Without --provider,
Azure remains the default and --no-azure selects OpenAI. Credentials come from
the selected provider's environment variables, never command-line arguments.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Literal, Union, get_args, get_origin

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# GAIK imports -- only needed at runtime, not at scaffold time
try:
    from gaik.software_components.extractor.schema import (
        DECIMAL_PERSISTED_HELPER_SOURCE,
        CompositeExtractionRequirements,
        ExtractionRequirements,
        SchemaGenerator,
        decimal_field_repr,
    )
    from gaik.software_components.llm import Provider, get_llm_config

    _GAIK_AVAILABLE = True
except ImportError as _import_err:
    _GAIK_AVAILABLE = False
    _IMPORT_ERR = _import_err


def _annotation_repr(annotation) -> str:
    """Return a Python source representation for common Pydantic field types.

    Routes Decimal fields to the safe DecimalField/OptionalDecimalField
    aliases instead of the plain type -- see decimal_field_repr's docstring
    (gaik.software_components.extractor.schema) for why field.annotation
    alone can no longer tell a "made safe" Decimal field apart from a plain
    one, and _DECIMAL_HELPER_SOURCE below for what those aliases need.
    """
    decimal_repr = decimal_field_repr(annotation)
    if decimal_repr is not None:
        return decimal_repr

    origin = get_origin(annotation)

    if origin is list:
        args = get_args(annotation)
        return f"list[{_annotation_repr(args[0])}]" if args else "list"

    if origin is Literal:
        args = get_args(annotation)
        return f"Literal[{', '.join(repr(arg) for arg in args)}]"

    if origin is Union:
        args = get_args(annotation)
        non_none = [arg for arg in args if arg is not type(None)]
        if len(non_none) == 1 and type(None) in args:
            return f"Optional[{_annotation_repr(non_none[0])}]"
        return f"Union[{', '.join(_annotation_repr(arg) for arg in args)}]"

    # Python 3.10+ union syntax, e.g. str | None.
    try:
        import types as _types

        if isinstance(annotation, _types.UnionType):
            args = get_args(annotation)
            non_none = [arg for arg in args if arg is not type(None)]
            if len(non_none) == 1 and type(None) in args:
                return f"Optional[{_annotation_repr(non_none[0])}]"
            return f"Union[{', '.join(_annotation_repr(arg) for arg in args)}]"
    except AttributeError:
        pass

    if annotation is type(None):
        return "None"

    if hasattr(annotation, "__name__"):
        return annotation.__name__

    return repr(annotation)


def _collect_models(model: type) -> list[type]:
    """Collect nested Pydantic models before the parent model."""
    seen: set[type] = set()
    ordered: list[type] = []

    def collect(current: type) -> None:
        if current in seen:
            return
        seen.add(current)
        for field in current.model_fields.values():
            if get_origin(field.annotation) is list:
                args = get_args(field.annotation)
                if args and isinstance(args[0], type) and hasattr(args[0], "model_fields"):
                    collect(args[0])
        ordered.append(current)

    collect(model)
    return ordered


def _schema_to_py(schema_class: type, schema_name: str) -> str:
    """Render the generated Pydantic model (and any nested child models) to a
    .py file string.

    Builds source directly from model_fields rather than via
    print_pydantic_schema(): that helper reads field.annotation, which
    strips the Annotated/WithJsonSchema/BeforeValidator wrapping
    create_extraction_model() applies to Decimal fields (see
    decimal_field_repr's docstring) -- regenerating from the bare
    annotation would silently drop the safe Decimal representation,
    restoring both the regex-lookaround schema-rejection failure and the
    "12.40 EUR"-crashes-Decimal-parsing failure on the next PoC run.
    """
    class_blocks: list[str] = []
    needs_decimal_helper = False

    for current_model in _collect_models(schema_class):
        lines = [f"class {current_model.__name__}(BaseModel):"]

        docstring = (current_model.__doc__ or "").strip()
        if docstring:
            lines.append(f'    """{docstring}"""')

        lines.append("    model_config = ConfigDict(extra='forbid')")
        lines.append("")

        for field_name, field in current_model.model_fields.items():
            field_args: list[str] = []

            if field.description:
                field_args.append(f"description={field.description!r}")

            if field.default_factory is not None:
                factory_name = getattr(field.default_factory, "__name__", None)
                if factory_name in {"list", "dict", "set"}:
                    field_args.append(f"default_factory={factory_name}")
                else:
                    field_args.append(f"default={field.default_factory()!r}")
            elif not field.is_required():
                field_args.append(f"default={field.default!r}")

            if decimal_field_repr(field.annotation) is not None:
                needs_decimal_helper = True
            annotation = _annotation_repr(field.annotation)
            if field_args:
                lines.append(f"    {field_name}: {annotation} = Field({', '.join(field_args)})")
            else:
                lines.append(f"    {field_name}: {annotation}")

        class_blocks.append("\n".join(lines))

    header = (
        '"""Output schema for this use case.\n\n'
        "Generated by GAIK SchemaGenerator via the Solution Configuration Wizard.\n"
        "Reviewed and approved by the user during Phase 5 (Schema Design).\n"
        'Do not hand-edit -- re-run generate_schema.py if the requirements change.\n"""\n\n'
        "from decimal import Decimal\n"
        "from typing import List, Literal, Optional, Union\n\n"
        "from pydantic import BaseModel, Field, ConfigDict\n\n"
    )
    if needs_decimal_helper:
        header += DECIMAL_PERSISTED_HELPER_SOURCE.strip() + "\n\n\n"
    return header + "\n\n".join(class_blocks) + "\n"


def _requirements_to_json(
    schema_class: type,
    requirements: ExtractionRequirements | CompositeExtractionRequirements,
) -> dict:
    """Produce the payload that load_schema() expects."""
    return {
        "model_name": schema_class.__name__,
        "requirements_type": (
            "parent_with_nested_list"
            if isinstance(requirements, CompositeExtractionRequirements)
            else "extraction"
        ),
        "requirements": requirements.model_dump(),
    }


def _requirements_field_summary(
    requirements: ExtractionRequirements | CompositeExtractionRequirements,
) -> list[str] | dict[str, list[str]]:
    """Return printable field names for flat and repeated-record schemas."""
    if isinstance(requirements, CompositeExtractionRequirements):
        return {
            "parent": [field.field_name for field in requirements.parent_requirements.fields],
            **{
                child.container_name: [field.field_name for field in child.requirements.fields]
                for child in requirements.children
            },
        }
    return [field.field_name for field in requirements.fields]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate extraction schema via GAIK SchemaGenerator."
    )
    parser.add_argument(
        "--requirements",
        required=True,
        help="Path to extraction_requirements.md (user requirements text)",
    )
    parser.add_argument(
        "--schema-name",
        default=None,
        help="Expected class name (informational; SchemaGenerator decides the actual name)",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="PoC root directory -- schema files written to <output-dir>/schemas/",
    )
    parser.add_argument(
        "--provider",
        choices=[provider.value for provider in Provider] if _GAIK_AVAILABLE else None,
        default=None,
        help="Shared LLM provider; overrides --use-azure/--no-azure. Credentials come from env.",
    )
    parser.add_argument(
        "--use-azure",
        dest="use_azure",
        action="store_true",
        default=True,
        help="Use Azure OpenAI (default when --provider is omitted)",
    )
    parser.add_argument(
        "--no-azure",
        dest="use_azure",
        action="store_false",
        help="Use OpenAI directly when --provider is omitted",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override the model used for schema generation",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Override the API base URL for compatible endpoints or LiteLLM",
    )
    args = parser.parse_args()

    if not _GAIK_AVAILABLE:
        print(
            f"ERROR: GAIK toolkit not available: {_IMPORT_ERR}\n"
            "Install with: pip install gaik[extract]",
            file=sys.stderr,
        )
        return 1

    req_path = Path(args.requirements)
    if not req_path.exists():
        print(f"ERROR: Requirements file not found: {req_path}", file=sys.stderr)
        return 1

    user_requirements = req_path.read_text(encoding="utf-8")
    provider = args.provider or ("azure" if args.use_azure else "openai")
    overrides = {}
    if args.model is not None:
        overrides["model"] = args.model
    if args.base_url is not None:
        overrides["base_url"] = args.base_url
    try:
        # Overrides must reach the factory before it validates required fields
        # (e.g. an OpenAI-compatible server's model and endpoint).
        config = get_llm_config(provider, **overrides)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir).expanduser().resolve()
    schemas_dir = output_dir / "schemas"
    schemas_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating schema from: {req_path}")
    print(f"Output directory:       {schemas_dir}")
    print(f"Provider:               {provider}")
    print(f"Model:                  {config['model']}")
    print()

    # -- Call SchemaGenerator --
    generator = SchemaGenerator(config=config)
    schema_class = generator.generate_schema(user_requirements=user_requirements)
    requirements: ExtractionRequirements | CompositeExtractionRequirements = (
        generator.item_requirements
    )

    # -- Write output_schema.py --
    py_content = _schema_to_py(schema_class, args.schema_name or schema_class.__name__)
    py_path = schemas_dir / "output_schema.py"
    py_path.write_text(py_content, encoding="utf-8")
    print(f"\nSchema written to:       {py_path}")

    # -- Write output_schema_requirements.json (load_schema() contract) --
    req_payload = _requirements_to_json(schema_class, requirements)
    req_path_out = schemas_dir / "output_schema_requirements.json"
    req_path_out.write_text(json.dumps(req_payload, indent=2), encoding="utf-8")
    print(f"Requirements written to: {req_path_out}")

    # -- Export JSON Schema (best-effort, for documentation) --
    try:
        json_schema = schema_class.model_json_schema()
        json_path = schemas_dir / "output_schema.json"
        json_path.write_text(json.dumps(json_schema, indent=2), encoding="utf-8")
        print(f"JSON Schema written to:  {json_path}")
    except Exception:
        pass

    # -- Save requirements hash so run_poc.py knows the schema is current --
    # If extraction_requirements.md is later edited, the hash mismatch will
    # trigger regeneration on the next run_poc.py invocation.
    import hashlib

    req_hash = hashlib.sha256(req_path.read_bytes()).hexdigest()
    # All schema files are always named output_schema.* regardless of the class
    # name. The hash file is therefore always output_schema.hash so that every
    # PoC template's _load_schema_if_fresh() finds it with schema_name="output_schema".
    hash_path = schemas_dir / "output_schema.hash"
    hash_path.write_text(req_hash)
    print(f"Requirements hash saved: {hash_path}")

    print(
        f"\nGenerated class name: {schema_class.__name__}"
        f"\nFields: {_requirements_field_summary(requirements)}"
        f"\n\nPresent {py_path} to the user for review."
        "\nIf the user requests changes, edit output_schema.py and"
        "\noutput_schema_requirements.json directly -- do NOT re-run this script."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
