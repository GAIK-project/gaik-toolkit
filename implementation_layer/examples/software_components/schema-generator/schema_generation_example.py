"""Standalone schema generation example.

This example uses SchemaGenerator to output a reusable Pydantic schema plus requirements
metadata that another component can use later for extraction.
It contains the examples of several task requirements.
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
# Several extraction task descriptions to test


TASK = """
Extract purchase order data.

The output will include the following top-level fields:
- date (DD/MM/YYYY format when unambiguous)
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


# TASK = """
# Extract purchase order data from the document.

# Top-level fields:
# - Purchase order number
# - Delivery date (Delivery date in DD/MM/YYYY format when unambiguous)
# - Delivery_address (Format: company name + street + postal code + city + country)
# - Vendor number

# For each line item, extract:
# - Item number (e.g. 0100, 0200)
# - Article code (internal supplier code)
# - Dimensions (cross-section as stated, e.g. "25x8mm")
# - Product form (Choose from: Flat, round, or rectangular bar)
# - Material grade (e.g. "6061 Aluminum", "316 Stainless", "C260 Brass")
# - Standard designation (alloy/standard code, e.g. "CW024A", "ASTM B221")
# - Cut length (text string including the unit, e.g. "2000mm")
# - Temper or condition (e.g. "Cold drawn, bright finish", "T6")
# - Hardness HV (numeric, if stated, else null)
# - Min bend radius (numeric, if stated, else null)
# - Delivery length note (e.g. "in lengths of 3000mm", if stated, else null)
# - Applicable standard (e.g. "ASTM B221", "EN 755-2", if stated, else null)
# - Special flags (any remaining codes, e.g. "XK", "chamfered edges", else null)
# - Quantity (text string including the unit, e.g. "4.200 kg")
# """


# TASK = """
# The task is to extract key fields from customer documents (Purchase Order (PO) and Bill of
# Material (BOM)), and align them so that each PO item is enriched with the correct technical
# details. Begin with the customer's purchase order, which may include multiple items. Each item
# is linked to its BOM via a Material Number.

# For every item in the PO, extract the Material Number along with the basic item details:
# Quantity, Description, and Delivery Date (Delivery date in DD/MM/YYYY format when unambiguous). Use the item's Material Number from the PO to find
# the BOM having the same Material Number (represented as 'ID'). From the matching BOM, extract
# the part's 'Type Part Designation' and Dimensions.

# The final output should contain as many lines as the number of items in the PO. Each line
# should have: Material Number, Quantity, Description, Delivery Date (from PO), Type Part
# Designation, Dimensions (from BOM).

# Also extract the following header information from the PO: Order Date, Buyer, Sales Person,
# Shipping Address, Payment Terms.
# """


# TASK = """
# Extract the following information from the medical audio.

# Fields:
# - Date (DD/MM/YYYY)
# - Patient's date of birth (DD-MM-YYYY)
# - Symptoms (few keywords separated by semicolons)
# - Medical history (few keywords separated by semicolons)
# - Examination description (few keywords separated by semicolons)
# - Body temperature (value and unit exactly as stated)
# - Heart rate (value and unit exactly as stated)
# - Oxygen saturation (value and unit exactly as stated)
# - Procedure performed (few keywords)
# - Diagnosis (few keywords)
# - Prescription (few keywords)
# - Follow-up (few keywords)

# Rules:
# - Extract only information explicitly stated in the audio or transcript.
# - Do not infer medical information.
# - If a field is not mentioned, output an empty string.
# - Preserve dates exactly if the required format cannot be inferred.
# - For symptoms, medical history, and examination description, output short keyword phrases separated by semicolons.
# """


# TASK = """
# Extract delivery information from the manifest.

# Header fields:
# - Manifest number
# - Carrier name
# - Dispatch date (DD/MM/YYYY)
# - Origin depot
# - Destination depot
# - Total weight (text string including the unit, e.g. "1250 kg")

# For each shipment in the manifest:
# - Tracking number
# - Recipient name
# - Recipient address
# - Package count
# - Weight (text string including the unit, e.g. "18.5 kg")
# - Service level (Standard, Express, or Overnight)
# - Fragile (yes/no)
# - Delivery instructions (if stated, else null)
# """

# TASK = """
# Extract the following from the security advisory:
# - CVE identifier (e.g. "CVE-2024-12345")
# - Affected product
# - Affected versions (text string as stated, e.g. "3.2.0 – 3.4.1")
# - Severity (Critical, High, Medium, or Low)
# - CVSS score (numeric, if stated, else null)
# - Attack vector (Network, Adjacent, Local, or Physical)
# - Patch available (yes/no)
# - Patched version (if stated, else null)
# - Published date (Format: DD/MM/YYYY)
# - Summary (in a few keywords separated by semicolons)
# """

# TASK = """
# Extract compliance-relevant information from the construction blueprint.

# Top-level fields:
# - Project address
# - Drawing title
# - Drawing number
# - Sheet number
# - Project number
# - Scale
# - Drawing date
# - Owner
# - Architect
# - General contractor
# - Surveyor

# For each compliance-relevant item visible in the blueprint, extract:
# - Item type (General note, Revision, Dimension, Elevation reference, Legend/material reference, Drawing view, Grid line, Section callout, Other)
# - Label or number
# - Exact text or value
# - Related drawing element or location
# - Compliance relevance (Dimensions, Structural reference, Utilities/fixtures, Survey/benchmarks, Specifications, Safety/compliance, Revision control, Material reference, Other)

# Rules:
# - Extract only explicitly visible information.
# - Preserve original wording, dimensions, dates, and labels.
# """

# TASK = """
# Extract compliance-relevant information from the construction blueprint.

# Top-level fields:
# - Project address
# - Drawing title
# - Drawing number
# - Sheet number
# - Project number
# - Scale
# - Drawing date
# - Owner
# - Architect
# - General contractor
# - Surveyor

# Repeated records:
# 1. General construction notes:
#    - Note number
#    - Note text
#    - Compliance category: Dimensions, Structural reference, Utilities/fixtures, Survey/benchmarks, Specifications, Safety/compliance, Other

# 2. Revision history:
#    - Revision number
#    - Revision date
#    - Revision description

# 3. Visible dimensions:
#    - Dimension value exactly as written
#    - Unit
#    - Direction or orientation
#    - Related element or view

# 4. Elevation references:
#    - Elevation value exactly as written
#    - Related element or section

# 5. Material and legend references:
#    - Symbol or pattern name
#    - Meaning
#    - Location or view

# 6. Drawing views, grid lines, and callouts:
#    - Label
#    - Type
#    - View title or related drawing element
#    - Compliance-relevant information shown

# Rules:
# - Extract only explicitly visible information.
# - Do not infer compliance decisions.
# - Preserve original wording, dimensions, dates, and labels.
# - Use an empty string for missing or unreadable values.
# """


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
                lines.append(f"    {field_name}: {annotation} = Field({', '.join(field_args)})")
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
