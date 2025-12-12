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
from datetime import date, datetime
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
    format: str | None = Field(default=None, description="Output format (e.g., date strftime format)")

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
        print("Using flat structure")
        requirements = parse_user_requirements(user_description, client=client, model=model)
        extraction_model = create_extraction_model(requirements)
        return extraction_model, requirements, analysis

    # Nested structure
    print(f"Using nested structure with '{analysis.parent_container_name}' field")
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
    print(f"Container field: '{analysis.parent_container_name}' (List[{ItemModel.__name__}])")

    return ParentModel, item_requirements, analysis


# -----------------------------------------------------------------------------
# Type Detection Rules for LLM Prompt
# -----------------------------------------------------------------------------

TYPE_DETECTION_RULES = """
FIELD TYPE DETECTION RULES - Apply these rules to determine field_type and enum:

1. ENUM (field_type='str' + populate 'enum' list):
   Use when a SMALL, FIXED set of allowed values (2-8 options) is explicitly specified.
   Recognition patterns:
   - Bracketed values: [value1, value2, value3] or (a, b, c)
   - Slash/pipe separated: "hot/cold/warm", "yes|no|maybe"
   - Explicit options: "one of:", "options:", "allowed values:", "choose from:"
   - Binary choices: "yes/no", "true/false", "active/inactive"
   Examples:
   - "Weather [hot, cold, warm]" -> field_type='str', enum=['hot', 'cold', 'warm']
   - "Status: active/inactive/pending" -> field_type='str', enum=['active', 'inactive', 'pending']
   IMPORTANT: Do NOT treat examples prefixed with "e.g.", "example:", "such as" as enum values.

2. DATE (field_type='date'):
   Use for any date or timestamp field.
   Recognition patterns:
   - Contains "date" in name or description: "entry date", "start date", "date of birth"
   - Date words in any language: "pÃ¤ivÃ¤mÃ¤Ã¤rÃ¤" (Finnish), "datum" (German), "fecha" (Spanish), etc.
   - Temporal references: "when", "timestamp", "created on", "modified at"
   Examples:
   - "Entry Date" -> field_type='date'
   - "Date of visit" -> field_type='date'
   - "PÃ¤ivÃ¤mÃ¤Ã¤rÃ¤" -> field_type='date'

3. LIST OF STRINGS (field_type='list[str]'):
   Use when field should contain multiple text items.
   Recognition patterns:
   - Explicit list notation: "[List of ...]", "list of items"
   - Multiple items expected: "comma-separated", "multiple values"
   - Plural collection nouns: "tasks", "attachments", "tags", "categories", "items"
   Examples:
   - "Tasks performed" -> field_type='list[str]'
   - "Attachments [List of files]" -> field_type='list[str]'

4. LIST OF OBJECTS (field_type='list[dict]'):
   Use for complex nested structures with multiple fields per item.
   Recognition patterns:
   - "table of", "records containing", "items with fields"
   - Multiple sub-fields described for each item
   Example:
   - "Line items with product, quantity, and price" -> field_type='list[dict]'

5. INTEGER (field_type='int'):
   Use for whole numbers, counts, quantities.
   Recognition patterns:
   - "number of", "count", "quantity", "total"
   - Week/day/year numbers: "week number", "day of month"
   - IDs that are numeric: "employee ID" (if specified as numeric)
   Examples:
   - "Work Week [Week number]" -> field_type='int'
   - "Number of attendees" -> field_type='int'

6. FLOAT (field_type='float'):
   Use for decimal numbers, measurements, percentages, ratios.
   Recognition patterns:
   - "percentage", "ratio", "rate"
   - Measurements: "temperature", "weight", "height", "distance"
   - Averages or statistics: "average", "mean", "score"
   Examples:
   - "Completion percentage" -> field_type='float'
   - "Temperature reading" -> field_type='float'

7. DECIMAL (field_type='decimal'):
   Use for precise monetary or financial values where precision matters.
   Recognition patterns:
   - Currency: "price", "cost", "amount", "total", "fee", "salary"
   - Financial: "invoice total", "payment amount", "budget"
   Examples:
   - "Total Amount [EUR]" -> field_type='decimal'
   - "Unit price" -> field_type='decimal'

8. BOOLEAN (field_type='bool'):
   Use for true/false flags and binary states.
   Recognition patterns:
   - Field names starting with: "is_", "has_", "can_", "should_"
   - Questions: "whether", "if applicable"
   - Binary flags: "approved", "completed", "verified" (when yes/no answer)
   Examples:
   - "Is approved" -> field_type='bool'
   - "Has attachments" -> field_type='bool'

9. STRING (field_type='str'):
   Default for text fields when no other type clearly applies.
   Use for: names, descriptions, remarks, comments, signatures, addresses, observations.
   Examples:
   - "Company name" -> field_type='str'
   - "General remarks" -> field_type='str'

PRIORITY ORDER: When uncertain, apply rules in this order:
1. Check for explicit enum values first (brackets, slashes)
2. Check for date-related keywords
3. Check for list indicators
4. Check for numeric patterns (int vs float vs decimal)
5. Check for boolean patterns
6. Default to 'str'
"""

# -----------------------------------------------------------------------------
# Parse the user's natural language into field specs
# -----------------------------------------------------------------------------


def parse_user_requirements(
    user_description: str, *, client=None, model: str = None
) -> ExtractionRequirements:
    """
    Parse extraction requirements from natural language using LLM with type detection rules.
    Works with any input format - numbered lists, bullets, prose, tables, etc.
    """
    if client is None:
        config = get_openai_config(use_azure=True)
        client = create_openai_client(config)
        model = model if model else config["model"]
    elif model is None:
        raise ValueError("model must be provided when client is specified")

    cleaned_description = _clean_requirements_text(user_description)

    resp = _parse_with(
        client=client,
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PARSER},
            {
                "role": "user",
                "content": "Parse the extraction requirements below into the target schema.\n"
                "Apply the type detection rules to determine the correct field_type for each field.\n"
                "If a field cannot be identified reliably, omit it.\n"
                + TYPE_DETECTION_RULES
                + "\n\nRequirements to parse:\n```txt\n"
                + cleaned_description
                + "\n```",
            },
        ],
        response_format=ExtractionRequirements,
    )
    req = resp.choices[0].message.parsed
    _apply_type_overrides(req)
    if getattr(resp, "usage", None):
        print(f"[parse_user_requirements] tokens={resp.usage.total_tokens}")
    return req


def _clean_requirements_text(text: str) -> str:
    """Trim whitespace noise while preserving numbered/bulleted structure."""
    lines = [line.strip() for line in text.splitlines()]
    cleaned_lines = [line for line in lines if line]
    return "\n".join(cleaned_lines)


# Date format patterns to detect from user requirements
DATE_FORMAT_PATTERNS: dict[str, str] = {
    "dd/mm/yyyy": "%d/%m/%Y",
    "dd/mm/yyy": "%d/%m/%Y",
    "dd-mm-yyyy": "%d-%m-%Y",
    "dd.mm.yyyy": "%d.%m.%Y",
    "mm/dd/yyyy": "%m/%d/%Y",
    "mm-dd-yyyy": "%m-%d-%Y",
    "yyyy-mm-dd": "%Y-%m-%d",
    "yyyy/mm/dd": "%Y/%m/%d",
    "yyyy.mm.dd": "%Y.%m.%d",
}

# Date-related keywords in multiple languages for field detection
DATE_KEYWORDS = [
    "date",        # English
    "datum",       # German, Dutch, Swedish
    "fecha",       # Spanish
    "päivämäärä",  # Finnish
    "paivamaara",  # Finnish (ASCII)
    "päiväys",     # Finnish (alternative)
    "paivays",     # Finnish (ASCII alternative)
    "data",        # Italian, Portuguese, Polish
    "jour",        # French
    "dátum",       # Hungarian
    "dato",        # Norwegian, Danish
    "tarih",       # Turkish
]



def _detect_date_format(text: str) -> str | None:
    """Detect date format from description text (e.g., 'DD/MM/YYYY' -> '%d/%m/%Y')."""
    if not text:
        return None
    text_lower = text.lower().replace(" ", "")
    for pattern, strftime_fmt in DATE_FORMAT_PATTERNS.items():
        if pattern in text_lower:
            return strftime_fmt
    return None


def _is_date_field(name: str, description: str) -> bool:
    """Check if a field is a date field based on name or description (multilingual)."""
    name_lower = name.lower()
    desc_lower = description.lower()
    for keyword in DATE_KEYWORDS:
        if keyword in name_lower or keyword in desc_lower:
            return True
    return False


def _apply_type_overrides(requirements: ExtractionRequirements) -> None:
    """
    Apply deterministic heuristics to FieldSpec entries to enforce critical types
    even when the LLM guesses incorrectly (e.g., date fields must be typed as date).
    Also detects date output format from field descriptions.
    Supports multiple languages for date detection.
    """
    for field in requirements.fields:
        if _is_date_field(field.field_name, field.description):
            field.field_type = "date"
            # Detect date format from description (e.g., "DD/MM/YYYY")
            detected_format = _detect_date_format(field.description)
            if detected_format:
                field.format = detected_format


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
    # Note: dates use str to allow flexible input formats, then normalized in post-processing
    base_types = {
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list[str]": list[str],
        "date": str,  # Use str for dates - normalized in post-processing
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


def parse_date(value: str | date | None, output_format: str = "%Y-%m-%d") -> str | None:
    """
    Parse a date from various formats and return in the specified output format.

    Handles common formats: ISO, European (DD/MM/YYYY), US (MM/DD/YYYY), etc.
    Also fixes common OCR/LLM year errors (e.g., 1004 -> 2004).

    Args:
        value: Date string, datetime.date object, or None
        output_format: strftime format for output (default: ISO format)

    Returns:
        Formatted date string or None if parsing fails
    """
    if value is None:
        return None

    # Handle datetime.date objects directly
    if isinstance(value, date):
        return value.strftime(output_format)

    value = str(value).strip()
    if not value:
        return None

    # Common date formats to try (ordered by likelihood)
    formats = [
        "%Y-%m-%d",      # ISO: 2024-04-25
        "%d/%m/%Y",      # European: 25/04/2024
        "%d-%m-%Y",      # European with dash: 25-04-2024
        "%d.%m.%Y",      # European with dot: 25.04.2024
        "%m/%d/%Y",      # US: 04/25/2024
        "%m-%d-%Y",      # US with dash: 04-25-2024
        "%Y/%m/%d",      # ISO with slash: 2024/04/25
        "%Y.%m.%d",      # ISO with dot: 2024.04.25
        "%B %d, %Y",     # Full month: April 25, 2024
        "%d %B %Y",      # Day first: 25 April 2024
        "%b %d, %Y",     # Short month: Apr 25, 2024
        "%d %b %Y",      # Day first short: 25 Apr 2024
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)

            # Fix common year errors
            year = parsed.year
            if year < 100:
                # Two-digit year: 24 -> 2024, 95 -> 1995
                year = year + 2000 if year < 50 else year + 1900
            elif 1000 <= year < 1100:
                # OCR/LLM error: 1004 -> 2004, 1024 -> 2024
                year = year + 1000

            if year != parsed.year:
                parsed = parsed.replace(year=year)

            return parsed.strftime(output_format)
        except ValueError:
            continue

    # Return original value if no format matched
    return value


def normalize_extracted_data(
    data: dict, requirements: ExtractionRequirements, default_date_format: str = "%Y-%m-%d"
) -> dict:
    """
    Normalize extracted data, converting dates and handling list fields.

    Args:
        data: Raw extracted data dictionary
        requirements: Field specifications
        default_date_format: Default output format for dates (used if not specified in field)

    Returns:
        Normalized data dictionary
    """
    spec_by_name = {f.field_name: f for f in requirements.fields}
    result = {}

    for key, value in data.items():
        spec = spec_by_name.get(key)

        if spec is None or value is None:
            result[key] = value
            continue

        if spec.field_type == "date":
            # Use format from field spec if available, otherwise use default
            date_format = spec.format if spec.format else default_date_format
            result[key] = parse_date(value, date_format)
        elif spec.field_type == "list[str]":
            if isinstance(value, str):
                result[key] = [s.strip() for s in re.split(r"[;,]", value) if s.strip()]
            elif isinstance(value, list):
                result[key] = [str(x).strip() for x in value]
            else:
                result[key] = value
        else:
            result[key] = value

    return result


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

