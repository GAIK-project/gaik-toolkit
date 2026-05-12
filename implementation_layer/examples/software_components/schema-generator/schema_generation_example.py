"""Standalone schema generation example.

This example uses SchemaGenerator by itself. It does not run DataExtractor or
VisionExtractor. The output is a reusable Pydantic schema plus requirements
metadata that another component can use later for extraction.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Literal, Union, get_args, get_origin

from pydantic import BaseModel

# Make the local source tree importable when this example is run directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.extractor import SchemaGenerator, get_openai_config


BASE_DIR = Path(__file__).parent
SCHEMA_DIR = BASE_DIR / "schema_generated_single_doc"


# Natural-language task description. SchemaGenerator turns this into:
# - a Pydantic model class
# - requirements metadata used for post-processing/normalization
TASK = """
Extract purchase order data.

The output will include the following top-level fields:
- date (DD-MM-YYYY)
- purchase order number
- supplier number
- contact

Also, the output will include the data for each line item.

For each line item, extract these scalar fields:
- item number
- complete description
- quantity
- price
- material number
"""


def _annotation_repr(annotation) -> str:
    """Return a Python source representation for common Pydantic field types."""
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


def _collect_models(model: type[BaseModel]) -> list[type[BaseModel]]:
    """Collect nested Pydantic models before the parent model."""
    seen: set[type[BaseModel]] = set()
    ordered: list[type[BaseModel]] = []

    def collect(current: type[BaseModel]) -> None:
        if current in seen:
            return
        seen.add(current)

        for field in current.model_fields.values():
            if get_origin(field.annotation) is list:
                args = get_args(field.annotation)
                if args and isinstance(args[0], type) and issubclass(args[0], BaseModel):
                    collect(args[0])

        ordered.append(current)

    collect(model)
    return ordered


def save_schema_to_python(model: type[BaseModel], path: Path) -> None:
    """Save a generated Pydantic model as importable Python source."""
    class_blocks: list[str] = []

    for current_model in _collect_models(model):
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

            annotation = _annotation_repr(field.annotation)
            if field_args:
                lines.append(
                    f"    {field_name}: {annotation} = Field({', '.join(field_args)})"
                )
            else:
                lines.append(f"    {field_name}: {annotation}")

        class_blocks.append("\n".join(lines))

    header = (
        '"""Auto-generated schema - do not edit manually."""\n\n'
        "from decimal import Decimal\n"
        "from typing import Literal, Optional, Union\n\n"
        "from pydantic import BaseModel, ConfigDict, Field\n\n"
    )
    path.write_text(header + "\n\n".join(class_blocks) + "\n", encoding="utf-8")


def save_requirements(requirements, model_name: str, path: Path) -> None:
    """Save requirements metadata beside the generated schema."""
    requirements_type = (
        "parent_with_nested_list"
        if getattr(requirements, "structure_type", None) == "parent_with_nested_list"
        else "extraction"
    )
    payload = {
        "model_name": model_name,
        "requirements_type": requirements_type,
        "requirements": requirements.model_dump(),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    # Schema generation uses the same OpenAI/Azure OpenAI config helper as the
    # extractor component. Set use_azure=False for direct OpenAI.
    config = get_openai_config(use_azure=True)

    # Generate the Pydantic model and keep the parsed requirements metadata.
    generator = SchemaGenerator(config=config)
    schema = generator.generate_schema(TASK)
    requirements = generator.item_requirements

    # Save generated artifacts so another workflow can reuse them later.
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    save_schema_to_python(schema, SCHEMA_DIR / "schema.py")
    save_requirements(requirements, schema.__name__, SCHEMA_DIR / "requirements.json")
    (SCHEMA_DIR / "schema_info.json").write_text(
        json.dumps(generator.get_schema_info(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Saved schema to: {SCHEMA_DIR}")
    print(f"Model name: {schema.__name__}")


if __name__ == "__main__":
    main()
