"""
Dynamic Schema Extraction with Structured Outputs

Schema.py extracts structured data from documents using LLMs,
automatically generates Pydantic schemas from natural language requirements, and
extracts type-safe data with validation.

Main Interface:
    from schema_generator import SchemaGenerator

    generator = SchemaGenerator(use_azure=True)
    results = generator.extract(
        user_requirements="Extract invoice number and total...",
        documents=["document text"]
    )
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, get_args, get_origin

from openai import APIError, APITimeoutError, RateLimitError

# Import shared configuration
from gaik.building_blocks.config import create_openai_client, get_openai_config

try:
    # Pydantic v2 style config (preferred)
    from pydantic import ConfigDict

    _HAS_V2 = True
except Exception:
    _HAS_V2 = False


from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    constr,
    create_model,
    field_validator,
)

# -----------------------------------------------------------------------------
# Setup
# -----------------------------------------------------------------------------

SYSTEM_PARSER = (
    "You convert text into strictly structured data according to the provided schema. "
    "Never invent values. If uncertain or missing, return null. "
    "Do not include explanations or extra keys or extra fields."
)

# -----------------------------------------------------------------------------
# Retry & call helpers
# -----------------------------------------------------------------------------


def _with_retries(call, tries: int = 4):
    for i in range(tries):
        try:
            return call()
        except (RateLimitError, APITimeoutError, APIError):
            if i == tries - 1:
                raise
            time.sleep(2**i)  # backoff


def _parse_with(*, client, model: str, messages: list[dict], response_format: type[BaseModel]):
    """
    Wraps client.beta.chat.completions.parse in a retry + deterministic settings.

    Args:
        client: OpenAI or AzureOpenAI client instance
        model: Model name to use
        messages: Messages to send
        response_format: Pydantic model for structured output
    """
    return _with_retries(
        lambda: client.beta.chat.completions.parse(
            model=model,
            messages=messages,
            response_format=response_format,
            temperature=0,
            top_p=1.0,
            seed=12345,
            timeout=30,
        )
    )


# -----------------------------------------------------------------------------
# Fixed schema for parsing the user's extraction requirements
# -----------------------------------------------------------------------------

AllowedTypes = Literal["str", "int", "float", "bool", "list[str]", "date", "decimal", "list[dict]"]


class FieldSpec(BaseModel):
    """Specification for a single field to extract."""

    field_name: str = Field(description="snake_case field name, must start with a letter")
    field_type: AllowedTypes = Field(description="Type of the field")
    description: str
    required: bool = True
    enum: list[str] | None = Field(default=None, description="Allowed values (if enumerated)")
    pattern: str | None = Field(default=None, description="Regex to validate strings (optional)")
    format: Literal["iso-date", "currency-eur"] | None = Field(default=None)

    @field_validator("field_name")
    @classmethod
    def _snake_case(cls, v: str) -> str:
        v2 = re.sub(r"[^a-zA-Z0-9]+", "_", v).strip("_").lower()
        if not re.match(r"^[a-z][a-z0-9_]*$", v2 or ""):
            raise ValueError("field_name must be snake_case and start with a letter")
        return v2

    @field_validator("enum")
    @classmethod
    def _enum_nonempty(cls, v: list[str] | None) -> list[str] | None:
        if v is not None and len(v) == 0:
            raise ValueError("enum must be a non-empty list when provided")
        return v


class ExtractionRequirements(BaseModel):
    """Parsed extraction requirements from user input."""

    use_case_name: str
    fields: list[FieldSpec]

    @field_validator("fields")
    @classmethod
    def _unique_names(cls, fields: list[FieldSpec]) -> list[FieldSpec]:
        seen = set()
        for f in fields:
            if f.field_name in seen:
                raise ValueError(f"Duplicate field_name: {f.field_name}")
            seen.add(f.field_name)
        return fields


# -----------------------------------------------------------------------------
# Structure Detection for Nested vs Flat Schemas
# -----------------------------------------------------------------------------


class StructureAnalysis(BaseModel):
    """Analysis of whether the extraction requires nested or flat structure."""

    structure_type: Literal["flat", "nested_list"] = Field(
        description="Type of structure: 'flat' for single object, 'nested_list' for array of items"
    )
    parent_container_name: str = Field(
        description="Name for the parent container (e.g., 'items', 'records', 'entries')"
    )
    parent_description: str = Field(description="Description of what the parent container holds")
    item_description: str = Field(
        description="Description of extraction requirements for each individual item (if nested)"
    )
    reasoning: str = Field(description="Brief explanation of why this structure was chosen")


def detect_structure_type(
    user_description: str, *, client=None, model: str = None
) -> StructureAnalysis:
    """
    Analyze if the extraction requires a nested list structure or flat structure.
    """
    if client is None:
        config = get_openai_config(use_azure=True)
        client = create_openai_client(config)
        model = model if model else config["model"]
    elif model is None:
        raise ValueError("model must be provided when client is specified")

    resp = _parse_with(
        client=client,
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PARSER},
            {
                "role": "user",
                "content": (
                    "Analyze the following extraction requirements and determine the output structure.\n\n"
                    "Use NESTED_LIST when:\n"
                    "- The DOCUMENT contains multiple items/records/rows to extract\n"
                    "- Instructions mention 'multiple items IN THE DOCUMENT', 'list of items', 'table of records'\n"
                    "- 'one line per item', 'one row per record', 'repeat for each entry'\n"
                    "- Document is structured as a table, list, or collection of similar items\n"
                    "- Example: Extract all products from an invoice (multiple products in one invoice)\n\n"
                    "Use FLAT when:\n"
                    "- ONE record per document (even if processing multiple documents)\n"
                    "- 'for each document', 'from each document', 'per document'\n"
                    "- Document describes a SINGLE entity (e.g., one project, one invoice, one person)\n"
                    "- Extracting summary/aggregate information from the document\n"
                    "- Example: Extract project details from grant document (one project per document)\n\n"
                    "IMPORTANT: 'For each X, extract...' means FLAT if X is the document itself, NESTED if X refers to multiple items within the document.\n\n"
                    "Requirements:\n```txt\n" + user_description + "\n```"
                ),
            },
        ],
        response_format=StructureAnalysis,
    )
    analysis = resp.choices[0].message.parsed
    if getattr(resp, "usage", None):
        print(f"[detect_structure_type] tokens={resp.usage.total_tokens}")
    return analysis


def parse_nested_requirements(
    user_description: str, *, client=None, model: str = None
) -> tuple[type[BaseModel], ExtractionRequirements, StructureAnalysis]:
    """
    Stage 2: Parse nested requirements by:
    1. Detecting structure type
    2. Parsing item-level fields
    3. Creating nested parent model

    Returns: (ParentModel, item_requirements, structure_analysis)
    """
    if client is None:
        config = get_openai_config(use_azure=True)
        client = create_openai_client(config)
        model = model if model else config["model"]
    elif model is None:
        raise ValueError("model must be provided when client is specified")

    print("Analyzing structure type...")
    analysis = detect_structure_type(user_description, client=client, model=model)

    print(f"Structure type: {analysis.structure_type}")
    print(f"  Reasoning: {analysis.reasoning}")

    if analysis.structure_type == "flat":
        # Just parse as flat requirements
        print("  Using flat structure")
        requirements = parse_user_requirements(user_description, client=client, model=model)
        extraction_model = create_extraction_model(requirements)
        return extraction_model, requirements, analysis

    # Nested structure
    print(f"  Using nested structure with '{analysis.parent_container_name}' field")
    print(f"  Parent: {analysis.parent_description}")

    print("\nParsing item-level fields...")
    item_requirements = parse_user_requirements(
        analysis.item_description, client=client, model=model
    )

    print(f"Identified {len(item_requirements.fields)} fields per item")
    print(f"  Fields: {[f.field_name for f in item_requirements.fields]}")

    print("\nCreating nested Pydantic model...")
    ItemModel = create_extraction_model(item_requirements)

    # Create parent model with items list
    suffix = "_Collection"
    base_name = sanitize_model_name(item_requirements.use_case_name, suffix=suffix)
    model_name = base_name + suffix

    ParentModel = create_model(
        model_name,
        __config__=ConfigDict(extra="forbid"),
        __doc__=f"Collection of {item_requirements.use_case_name} items",
        **{
            analysis.parent_container_name: (
                list[ItemModel],
                Field(description=analysis.parent_description),
            )
        },
    )

    print(f"Created nested model: {ParentModel.__name__}")
    print(f"  Container field: '{analysis.parent_container_name}' (List[{ItemModel.__name__}])")

    return ParentModel, item_requirements, analysis


# -----------------------------------------------------------------------------
# Parse the user's natural language into field specs
# -----------------------------------------------------------------------------


def parse_user_requirements(
    user_description: str, *, client=None, model: str = None
) -> ExtractionRequirements:
    """
    Parse the extraction requirements from the user's natural language using structured outputs.
    """
    if client is None:
        config = get_openai_config(use_azure=True)
        client = create_openai_client(config)
        model = model if model else config["model"]
    elif model is None:
        raise ValueError("model must be provided when client is specified")

    resp = _parse_with(
        client=client,
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PARSER},
            {
                "role": "user",
                "content": "Parse the extraction requirements below into the target schema.\n"
                "If a field cannot be identified reliably, omit it.\n"
                "```txt\n" + user_description + "\n```",
            },
        ],
        response_format=ExtractionRequirements,
    )
    req = resp.choices[0].message.parsed
    if getattr(resp, "usage", None):
        print(f"[parse_user_requirements] tokens={resp.usage.total_tokens}")
    return req


# -----------------------------------------------------------------------------
# Create dynamic Pydantic model from field specs
# -----------------------------------------------------------------------------


def sanitize_model_name(name: str, suffix: str = "") -> str:
    """
    Sanitize model name following OpenAI requirements.
    Only alphanumeric, underscores, and hyphens are allowed.
    Ensures final name (with suffix) is <= 64 chars.

    Args:
        name: The base name to sanitize
        suffix: Optional suffix to add (e.g., "_Extraction", "_Collection")

    Returns:
        Sanitized name that when combined with suffix is <= 64 chars
    """
    # Replace invalid characters with underscores
    s = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    # Remove consecutive underscores
    s = re.sub(r"_+", "_", s).strip("_")

    # Remove leading/trailing underscores
    s = s.strip("_")

    # Remove suffix from name if it already exists (avoid duplication)
    if suffix and s.endswith(suffix.lstrip("_")):
        s = s[: -len(suffix.lstrip("_"))].rstrip("_")

    # Ensure final name fits within 64 char limit
    max_length = 64 - len(suffix)
    if len(s) > max_length:
        s = s[:max_length].rstrip("_")

    return s if s else "Dynamic"


def create_extraction_model(requirements: ExtractionRequirements) -> type[BaseModel]:
    """
    Create a Pydantic model dynamically from field specifications (strict).
    - Forbid extra/unknown keys.
    - Apply enums, regex patterns, and formats where applicable.
    """
    # Map string type names to actual Python types
    base_types = {
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list[str]": list[str],
        "date": str,
        "decimal": Decimal,
        "list[dict]": list[dict],  # for nested structures like items
    }

    field_defs: dict[str, tuple[object, Field]] = {}

    for f in requirements.fields:
        py_type = base_types[f.field_type]

        # Constrain strings when possible
        annotated: object = py_type
        if f.field_type == "str" and f.pattern:
            annotated = Annotated[str, constr(pattern=f.pattern)]
        elif f.field_type == "decimal":
            annotated = Decimal  # leave numeric constraints to normalization/validation

        # Enums -> Literal[...] for strict checking
        if f.enum:
            # Build a Literal[...] dynamically; acceptable for runtime checks
            annotated = Literal[tuple(f.enum)]  # type: ignore[misc,call-arg]

        # Optionality
        required_default = ... if f.required else None
        typ = annotated if f.required else (annotated | None)

        field_defs[f.field_name] = (
            typ,
            Field(default=required_default, description=f.description),
        )

    suffix = "_Extraction"
    base_name = sanitize_model_name(requirements.use_case_name, suffix=suffix)
    model_name = base_name + suffix

    DynamicModel = create_model(
        model_name,
        __config__=ConfigDict(extra="forbid"),
        __doc__=f"Extraction model for {requirements.use_case_name}",
        **field_defs,
    )
    return DynamicModel


# -----------------------------------------------------------------------------
# Normalization helpers (post-LLM)
# -----------------------------------------------------------------------------


def _to_iso_date(s: str) -> str:
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return s  # leave as-is if unparseable


def _normalize_record(data: dict, req: ExtractionRequirements) -> dict:
    spec_by_name = {f.field_name: f for f in req.fields}
    out = {}
    for k, v in data.items():
        spec = spec_by_name.get(k)
        if spec is None or v is None:
            out[k] = v
            continue

        if spec.field_type == "date" and isinstance(v, str):
            out[k] = _to_iso_date(v)
        elif spec.field_type == "list[str]":
            if isinstance(v, str):
                out[k] = [s.strip() for s in re.split(r"[;,]", v) if s.strip()]
            elif isinstance(v, list):
                out[k] = [str(x).strip() for x in v]
            else:
                out[k] = v
        else:
            out[k] = v
    return out


# -----------------------------------------------------------------------------
# Helper: Pretty print Pydantic model schema
# -----------------------------------------------------------------------------


def print_pydantic_schema(model: type[BaseModel], title: str = "Generated Pydantic Schema") -> None:
    """
    Print the exact Pydantic model as Python class definition.
    For nested structures, prints both the inner model and outer container model.
    """
    import inspect

    print(f"\n{'=' * 80}")
    print(f"{title}")
    print(f"{'=' * 80}\n")

    # Collect all models to print (handle nested structures)
    models_to_print = []

    # Check if this model has nested Pydantic models
    for field_name, field_info in model.model_fields.items():
        annotation = field_info.annotation

        # Check for List[SomeModel] pattern
        origin = get_origin(annotation)
        if origin is list:
            args = get_args(annotation)
            if args and len(args) > 0:
                inner_type = args[0]
                # Check if it's a Pydantic model
                if inspect.isclass(inner_type) and issubclass(inner_type, BaseModel):
                    models_to_print.append(inner_type)

    # Print inner models first
    for inner_model in models_to_print:
        _print_single_model(inner_model)
        print()

    # Print the main model
    _print_single_model(model)

    print(f"\n{'=' * 80}\n")


def _print_single_model(model: type[BaseModel]) -> None:
    """Helper to print a single Pydantic model."""
    # Class definition
    print(f"class {model.__name__}(BaseModel):")

    # Docstring
    if model.__doc__:
        print(f'    """{model.__doc__}"""')

    # Config
    if hasattr(model, "model_config"):
        config = model.model_config
        if config.get("extra") == "forbid":
            print("    model_config = ConfigDict(extra='forbid')")

    print()

    # Fields
    for field_name, field_info in model.model_fields.items():
        # Get type annotation
        annotation = field_info.annotation
        type_str = str(annotation).replace("typing.", "").replace("<class '", "").replace("'>", "")

        # Clean up the type string for better readability
        type_str = type_str.replace("schema_generator.", "")

        # Check if required
        is_required = field_info.is_required()

        # Get description
        description = field_info.description

        # Build field definition
        if is_required:
            if description:
                print(f'    {field_name}: {type_str} = Field(description="{description}")')
            else:
                print(f"    {field_name}: {type_str}")
        else:
            if description:
                print(f'    {field_name}: {type_str} = Field(None, description="{description}")')
            else:
                print(f"    {field_name}: {type_str} = None")


# -----------------------------------------------------------------------------
# REUSABLE CLASS INTERFACE
# -----------------------------------------------------------------------------


class SchemaGenerator:
    """
    Generates Pydantic schemas from natural language requirements.

    Automatically detects nested vs flat data structures and generates
    appropriate Pydantic models for structured data extraction.

    Features:
    - Smart structure detection (flat vs nested)
    - Type-safe Pydantic model generation
    - Support for Azure OpenAI and OpenAI
    - Field specification parsing (types, enums, patterns)

    Usage:
        # Create config once
        config = get_openai_config(use_azure=True)  # or use_azure=False for standard OpenAI

        # Initialize with config
        generator = SchemaGenerator(config=config)

        # Generate schema from requirements
        schema = generator.generate_schema(
            user_requirements="Extract invoice number, amount, and date..."
        )

        # Access generated models and requirements
        print(generator.extraction_model)
        print(generator.item_requirements)
        print(generator.get_schema_info())
    """

    def __init__(self, config: dict, model: str | None = None):
        """
        Initialize the SchemaGenerator.

        Args:
            config: OpenAI configuration dict from get_openai_config()
            model: Optional model name override
        """
        self.config = config
        self.model = model if model else self.config["model"]
        self.client = create_openai_client(self.config)
        self.extraction_model = None
        self.item_requirements = None
        self.structure_analysis = None

    def analyze_structure(self, user_requirements: str) -> StructureAnalysis:
        """
        Analyze if the requirements need nested or flat structure.

        Args:
            user_requirements: Natural language description of extraction task

        Returns:
            StructureAnalysis with structure type and descriptions
        """
        self.structure_analysis = detect_structure_type(
            user_requirements, client=self.client, model=self.model
        )
        return self.structure_analysis

    def generate_schema(self, user_requirements: str) -> type[BaseModel]:
        """
        Generate Pydantic schema from natural language requirements.

        Args:
            user_requirements: Natural language description of fields to extract

        Returns:
            Generated Pydantic model class (nested or flat)
        """
        print("Generating schema from requirements...")
        self.extraction_model, self.item_requirements, self.structure_analysis = (
            parse_nested_requirements(user_requirements, client=self.client, model=self.model)
        )

        # Print the generated Pydantic model
        print("\n" + "=" * 80)
        print("GENERATED PYDANTIC MODEL")
        print("=" * 80)
        print_pydantic_schema(self.extraction_model, title="Extraction Schema")

        return self.extraction_model

    def get_schema_info(self) -> dict:
        """
        Get information about the generated schema.

        Returns:
            Dict with schema information
        """
        if not self.extraction_model:
            return {"error": "No schema generated yet. Call generate_schema() first."}

        return {
            "model_name": self.extraction_model.__name__,
            "structure_type": self.structure_analysis.structure_type
            if self.structure_analysis
            else "unknown",
            "fields": [f.field_name for f in self.item_requirements.fields]
            if self.item_requirements
            else [],
            "field_count": len(self.item_requirements.fields) if self.item_requirements else 0,
        }

