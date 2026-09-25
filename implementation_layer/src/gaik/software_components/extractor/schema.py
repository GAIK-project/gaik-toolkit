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

import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Union, get_args, get_origin

from openai import APIError, APITimeoutError, RateLimitError
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    WithJsonSchema,
    constr,
    create_model,
    field_validator,
    model_validator,
)

from gaik.observability import (
    UsageRecord,
    build_usage_record,
    measure_duration,
    openai_usage_to_dict,
)

# Import shared configuration
from gaik.software_components.config import get_openai_config
from gaik.software_components.llm.base import ProviderClient
from gaik.software_components.llm.factory import build_compat_client
from gaik.software_components.llm.parameters import normalize_chat_kwargs

# -----------------------------------------------------------------------------
# Setup
# -----------------------------------------------------------------------------

SYSTEM_PARSER = (
    "You convert text into strictly structured data according to the provided schema. "
    "Never invent values. If a value is uncertain or missing, use the field's default "
    "value (empty string for text fields, null for numeric fields). "
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


class _ParsedMessage:
    def __init__(self, parsed: BaseModel):
        self.parsed = parsed


class _ParsedChoice:
    def __init__(self, parsed: BaseModel):
        self.message = _ParsedMessage(parsed)


class _ParsedShim:
    """OpenAI-completion-shaped wrapper around a parsed Pydantic instance.

    Lets non-OpenAI providers (Anthropic, Google) reuse the same caller code
    that does ``resp.choices[0].message.parsed``.
    """

    def __init__(self, parsed: BaseModel):
        self.choices = [_ParsedChoice(parsed)]
        self.usage = None


def _sampling_kwargs(
    temperature: float | None, reasoning_effort: str | None
) -> dict[str, float | str]:
    """The sampling half of a ``parse`` call, with either half omittable.

    ``temperature`` and ``reasoning_effort`` are coupled on the gpt-5.x
    reasoning deployments, so they are resolved together rather than
    independently. A custom temperature is accepted only while reasoning
    effort is ``"none"``; under any active effort (``low``/``medium``/
    ``high``/``max``) the API rejects it outright::

        Unsupported value: 'temperature' does not support 0 with this model.
        Only the default (1) value is supported.

    A parameter set to ``None`` is left out of the request entirely, which is
    what the API requires — sending ``null`` is not the same as not sending it.
    """
    kwargs: dict[str, float | str] = {}
    if temperature is not None:
        kwargs["temperature"] = temperature
    if reasoning_effort is not None:
        kwargs["reasoning_effort"] = reasoning_effort
    return kwargs


def _parse_with(
    *,
    client,
    model: str,
    messages: list[dict],
    response_format: type[BaseModel],
    temperature: float | None = 0.0,
    reasoning_effort: str | None = None,
    config: dict | None = None,
):
    """
    Wraps client.beta.chat.completions.parse in a retry + deterministic settings.

    Accepts either a raw OpenAI/Azure client or a ``ProviderClient`` adapter
    (from ``gaik.software_components.llm``). Returns an object with a
    ``.choices[0].message.parsed`` shape in both cases.

    Args:
        client: OpenAI or AzureOpenAI client instance, or a ProviderClient
        model: Model name to use
        messages: Messages to send
        response_format: Pydantic model for structured output
        temperature: Sampling temperature. Defaults to ``0`` — the same
            requirements should yield the same schema. ``None`` omits it.
        reasoning_effort: Reasoning effort for a reasoning deployment.
            Defaults to ``None`` (not sent), which is required by the
            non-reasoning models that reject the parameter. See
            :func:`_sampling_kwargs` for why the two are set as a pair: to run
            a gpt-5.x reasoning deployment, either pair ``"none"`` with an
            explicit temperature to keep determinism, or pass an active effort
            with ``temperature=None``.
    """
    if isinstance(client, ProviderClient):
        # Temperature is shared by the text adapters. Reasoning effort is an
        # OpenAI option; native Anthropic and Google have different controls.
        provider_effort = (
            reasoning_effort
            if client.provider in {"openai", "azure", "openai_compatible", "aitta", "litellm"}
            else None
        )
        sampling = _sampling_kwargs(temperature, provider_effort)
        parsed = _with_retries(
            lambda: client.chat_parsed(
                messages=messages,
                response_format=response_format,
                model=model,
                **sampling,
            )
        )
        return _ParsedShim(parsed)
    sampling = _sampling_kwargs(temperature, reasoning_effort)
    sampling = normalize_chat_kwargs(model, {"top_p": 1.0, **sampling}, config=config)
    return _with_retries(
        lambda: client.beta.chat.completions.parse(
            model=model,
            messages=messages,
            response_format=response_format,
            timeout=(config or {}).get("timeout", 30),
            **sampling,
        )
    )


# -----------------------------------------------------------------------------
# Fixed schema for parsing the user's extraction requirements
# -----------------------------------------------------------------------------

AllowedTypes = Literal["str", "int", "float", "bool", "list[str]", "date", "decimal", "list[dict]"]
NUMERIC_FIELD_TYPES = {"int", "float", "decimal"}
RequirementsParseMode = Literal["normal", "repeated_item"]


class FieldSpec(BaseModel):
    """Specification for a single field to extract."""

    field_name: str = Field(description="Field identifier in lowercase_with_underscores format")
    field_type: AllowedTypes = Field(description="Type of the field")
    description: str
    required_in_output: bool = Field(
        default=True, description="Must this key appear in every output object?"
    )
    nullable: bool = Field(default=False, description="Is None an allowed value?")
    enum: list[str] | None = Field(default=None, description="Allowed values (if enumerated)")
    default: str | None = Field(default=None, description="Fallback value from the task")
    has_explicit_default: bool = Field(
        default=False, description="True when the task explicitly stated a default"
    )
    required: bool = True
    pattern: str | None = Field(default=None, description="Regex to validate strings (optional)")
    format: str | None = Field(
        default=None, description="Output format (e.g., date strftime format)"
    )

    @model_validator(mode="before")
    @classmethod
    def _compat_required_to_nullable(cls, data):
        if isinstance(data, dict) and "required" in data and "nullable" not in data:
            data["nullable"] = not data["required"]
        return data

    @model_validator(mode="after")
    def _sync_required_from_policy(self):
        self.required = self.required_in_output and not self.nullable
        return self

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


class ChildRequirements(BaseModel):
    """Parsed requirements for one repeated child collection."""

    container_name: str
    container_description: str
    requirements: ExtractionRequirements


class CompositeExtractionRequirements(BaseModel):
    """Requirements for one parent record with one or more repeated child collections."""

    structure_type: Literal["parent_with_nested_list"] = "parent_with_nested_list"
    parent_requirements: ExtractionRequirements
    children: list[ChildRequirements]

    @property
    def child_container_name(self) -> str:
        """Backward-compat shim — returns the first child's container name."""
        return self.children[0].container_name if self.children else ""

    @property
    def child_requirements(self) -> ExtractionRequirements:
        """Backward-compat shim — returns the first child's requirements."""
        return (
            self.children[0].requirements
            if self.children
            else ExtractionRequirements(fields=[], use_case_name="")
        )


# -----------------------------------------------------------------------------
# Structure Detection for Nested vs Flat Schemas
# -----------------------------------------------------------------------------


class ChildContainerSpec(BaseModel):
    """Metadata for one repeated child collection identified by detect_structure_type."""

    container_name: str = Field(description="snake_case field name for the list")
    container_description: str = Field(description="Description of this child collection")


class StructureAnalysis(BaseModel):
    """Analysis of whether the extraction requires nested or flat structure."""

    structure_type: Literal["flat", "nested_list", "parent_with_nested_list"] = Field(
        description=(
            "Type of structure: 'flat' for one object, 'nested_list' for only "
            "repeated records, or 'parent_with_nested_list' for one parent "
            "object plus one or more repeated child collections"
        )
    )
    parent_container_name: str = Field(
        description="Name for the parent container (e.g., 'items', 'records', 'entries')"
    )
    parent_description: str = Field(description="Description of what the parent container holds")
    item_description: str = Field(
        description="Description of extraction requirements for each individual item (if nested)"
    )
    parent_fields_description: str = Field(
        default="",
        description=(
            "For parent_with_nested_list: extraction requirements for fields that "
            "occur once per document/entity"
        ),
    )
    child_container_name: str = Field(
        default="",
        description=(
            "For parent_with_nested_list: snake_case name of the repeated child collection field"
        ),
    )
    child_container_description: str = Field(
        default="",
        description="For parent_with_nested_list: description of the child collection",
    )
    child_fields_description: str = Field(
        default="",
        description=(
            "For parent_with_nested_list: extraction requirements for one repeated "
            "child row/item/record"
        ),
    )
    child_containers: list[ChildContainerSpec] = Field(
        default=[],
        description=(
            "For parent_with_nested_list: ALL distinct repeated child collections. "
            "Each entry names one repeated section. Must have at least one entry "
            "when structure_type is parent_with_nested_list."
        ),
    )
    reasoning: str = Field(description="Brief explanation of why this structure was chosen")


# Legacy schema classification prompt
#
# Analyze the extraction requirements and choose PARENT_WITH_NESTED_LIST when
# document-level fields are combined with one or more repeated collections of
# rows/items/entries/events/findings/records. Choose NESTED_LIST when the
# document contains repeated rows/items/records without separate common fields.
# Choose FLAT for one record or entity per document and for summary/aggregate
# extraction. Treat "for each X" as flat when X is the document and nested when
# X identifies multiple items in the document. When headings combine common or
# header fields with line items/rows/records/events/actions/findings, choose
# PARENT_WITH_NESTED_LIST and include every repeated section in child_containers.
# This prompt did not distinguish scalar lists from repeated object records, so
# newer reasoning models could incorrectly turn fields such as list[str] tasks,
# attachments, or remarks into nested child models.


def _build_structure_classification_prompt(user_description: str) -> str:
    """Build the single prompt used to classify the extraction output shape."""
    return (
        "Analyze the following extraction requirements and determine the output "
        "structure.\n\n"
        "FIRST DISTINGUISH SCALAR LISTS FROM REPEATED OBJECTS.\n\n"
        "SCALAR LIST:\n"
        "- Each element is one primitive value, such as a string, number, date, "
        "or code.\n"
        "- Examples include lists of tasks, filenames, tags, remarks, identifiers, "
        "event descriptions, work phases, or attachment names.\n"
        "- A scalar list remains a field within a FLAT object.\n"
        "- Any number of scalar-list fields may exist without making the schema "
        "nested.\n"
        "- Wording such as 'a list of tasks', 'mentioned attachments', or 'events "
        "that occurred' does not by itself imply repeated objects.\n\n"
        "REPEATED OBJECT:\n"
        "- Each element is a record with its own named properties.\n"
        "- This is normally expressed as 'For each line item, extract item number, "
        "quantity, and price' or 'For each revision, extract revision number, date, "
        "and description'.\n"
        "- Use a child model only when the task defines fields belonging to each "
        "repeated item.\n"
        "- Do not create a child object containing only a duplicate of its container, "
        "such as tasks: [{'tasks': '...'}]. Use tasks: ['...'] instead.\n\n"
        "Choose FLAT when:\n"
        "- The output represents one document or entity.\n"
        "- It contains scalar fields, scalar-list fields, or both.\n"
        "- It may contain multiple scalar lists.\n"
        "- It extracts summary or aggregate information from one document.\n\n"
        "Choose NESTED_LIST when:\n"
        "- The root output consists only of repeated objects.\n"
        "- Each repeated object has explicitly stated per-item fields.\n"
        "- There are no separate document-level or header fields.\n\n"
        "Choose PARENT_WITH_NESTED_LIST when:\n"
        "- The output contains document-level or header fields.\n"
        "- It also contains at least one repeated object collection with explicitly "
        "stated per-item fields.\n"
        "- Scalar-list fields remain parent fields and must not be added to "
        "child_containers.\n\n"
        "IMPORTANT RULES:\n"
        "- Do not infer nesting from plural field names.\n"
        "- Words such as items, events, findings, actions, attachments, tasks, or "
        "records do not alone imply repeated objects.\n"
        "- Include only genuine repeated-object collections in child_containers.\n"
        "- Keep scalar lists in parent_fields_description.\n"
        "- When structure is ambiguous and no per-item fields are explicitly stated, "
        "prefer FLAT.\n\n"
        "FLAT example:\n"
        "- Project name\n"
        "- Tasks: a list of work tasks\n"
        "- Attachments: mentioned filenames\n"
        "Result: one flat object containing tasks: list[str] and attachments: "
        "list[str].\n\n"
        "PARENT_WITH_NESTED_LIST example:\n"
        "Header fields: purchase order number and supplier.\n"
        "For each line item: item number, description, quantity, and price.\n"
        "Result: one parent object containing a list of structured line-item "
        "objects.\n\n"
        "NESTED_LIST example:\n"
        "For each inspection: inspection date, inspector, and result.\n"
        "Result: a root list of structured inspection objects.\n\n"
        "Populate parent_fields_description with all parent scalar and scalar-list "
        "fields. Populate child_containers only for repeated objects; include every "
        "genuine repeated-object collection.\n\n"
        "Requirements:\n```txt\n" + user_description + "\n```"
    )


def detect_structure_type(
    user_description: str,
    *,
    client=None,
    model: str = None,
    temperature: float | None = 0.0,
    reasoning_effort: str | None = None,
    _usage_sink: list | None = None,
    config: dict | None = None,
) -> StructureAnalysis:
    """
    Analyze if the extraction requires a nested list structure or flat structure.

    ``temperature`` / ``reasoning_effort`` are passed straight to
    :func:`_parse_with`; see it for how the two interact on reasoning
    deployments.

    When ``_usage_sink`` is a list, the OpenAI usage dict from the underlying
    LLM call is appended to it. This is an internal hook used by
    :class:`SchemaGenerator` to aggregate token counts across the schema
    generation calls; external callers can ignore it.
    """
    if client is None:
        config = config or get_openai_config(use_azure=True)
        client = build_compat_client(config)
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
                "content": _build_structure_classification_prompt(user_description),
            },
        ],
        response_format=StructureAnalysis,
        temperature=temperature,
        reasoning_effort=reasoning_effort,
        config=config,
    )
    analysis = resp.choices[0].message.parsed
    if _usage_sink is not None:
        _usage_sink.append(openai_usage_to_dict(resp))
    if getattr(resp, "usage", None):
        print(f"[detect_structure_type] tokens={resp.usage.total_tokens}")
    return analysis


def _sanitize_field_name(name: str, fallback: str = "records") -> str:
    field_name = re.sub(r"[^a-zA-Z0-9]+", "_", name or "").strip("_").lower()
    if not field_name:
        field_name = fallback
    if not re.match(r"^[a-z]", field_name):
        field_name = f"{fallback}_{field_name}".strip("_")
    return field_name


def _ensure_no_list_dict_fields(requirements: ExtractionRequirements, *, context: str) -> None:
    bad_fields = [f.field_name for f in requirements.fields if f.field_type == "list[dict]"]
    if bad_fields:
        raise ValueError(
            f"{context} cannot contain list[dict] fields because the surrounding "
            "schema already represents the repeated object. Parse the row/item "
            f"fields as scalar fields instead. Problem fields: {bad_fields}"
        )


def _create_parent_with_nested_list_model(
    *,
    parent_requirements: ExtractionRequirements,
    children: list[ChildRequirements],
) -> type[BaseModel]:
    ParentFieldsModel = create_extraction_model(parent_requirements)  # noqa: N806

    combined_fields = {
        name: (finfo.annotation, finfo) for name, finfo in ParentFieldsModel.model_fields.items()
    }
    for child in children:
        ChildModel = create_extraction_model(child.requirements)  # noqa: N806
        combined_fields[child.container_name] = (
            list[ChildModel],
            Field(description=child.container_description),
        )

    suffix = "_Extraction"
    base_name = sanitize_model_name(parent_requirements.use_case_name, suffix=suffix)
    model_name = base_name + suffix
    child_names = ", ".join(c.container_name for c in children)

    return create_model(  # noqa: N806
        model_name,
        __config__=ConfigDict(extra="forbid"),
        __doc__=(
            f"Extraction model for {parent_requirements.use_case_name} with repeated {child_names}"
        ),
        **combined_fields,
    )


def _resolve_child_containers(analysis: StructureAnalysis) -> list[ChildContainerSpec]:
    """Return the de-duplicated child collections for a parent_with_nested_list.

    Uses ``analysis.child_containers`` when the detector populated it, otherwise
    falls back to the legacy single-child fields for backward compatibility.
    Container names are sanitized to snake_case and de-duplicated (preserving
    order), so any number of distinct collections is supported.
    """
    raw_containers = list(analysis.child_containers)
    if not raw_containers:
        raw_containers = [
            ChildContainerSpec(
                container_name=analysis.child_container_name
                or analysis.parent_container_name
                or "records",
                container_description=analysis.child_container_description
                or analysis.parent_description
                or "",
            )
        ]

    specs: list[ChildContainerSpec] = []
    seen: set[str] = set()
    for spec in raw_containers:
        cname = _sanitize_field_name(spec.container_name, fallback="records")
        if cname in seen:
            continue
        seen.add(cname)
        specs.append(
            ChildContainerSpec(
                container_name=cname,
                container_description=(
                    spec.container_description or f"Repeated {cname.replace('_', ' ')} records"
                ),
            )
        )
    return specs


def _build_parent_task(user_description: str, container_specs: list[ChildContainerSpec]) -> str:
    """Build the parent-field parse prompt, excluding the known child collections.

    Naming the detected repeated collections explicitly steers the parser away
    from emitting them as ``list[dict]`` fields on the parent object.
    """
    excluded = ", ".join(c.container_name.replace("_", " ") for c in container_specs)
    exclusion_clause = (
        f" In particular, exclude these repeated collections: {excluded}." if excluded else ""
    )
    return (
        "From the requirements below, parse only the once-per-document "
        "(header / summary) fields. Ignore any repeated row or item-level "
        "fields, i.e. any field that would hold a list of repeated records."
        + exclusion_clause
        + "\n\n"
        + user_description
    )


def _reroute_leaked_collections(
    parent_requirements: ExtractionRequirements,
    container_specs: list[ChildContainerSpec],
    seen_container_names: set[str],
) -> tuple[ExtractionRequirements, list[tuple[str, str]]]:
    """Move any ``list[dict]`` field on the parent into its own child container.

    Mutates ``container_specs`` / ``seen_container_names`` in place by appending
    a new :class:`ChildContainerSpec` for each leaked collection that is not
    already tracked. Returns the parent requirements with the leaked fields
    removed, plus a list of ``(container_name, original_field_name)`` pairs for
    logging. Generic: handles any number of leaked collections.
    """
    leaked = [f for f in parent_requirements.fields if f.field_type == "list[dict]"]
    if not leaked:
        return parent_requirements, []

    kept = [f for f in parent_requirements.fields if f.field_type != "list[dict]"]
    stripped = ExtractionRequirements(
        use_case_name=parent_requirements.use_case_name,
        fields=kept,
    )

    recovered: list[tuple[str, str]] = []
    for field in leaked:
        cname = _sanitize_field_name(field.field_name, fallback="records")
        if cname in seen_container_names:
            # Already covered by a detected container; the child parse for that
            # container reads from the full requirements text, so no work lost.
            continue
        seen_container_names.add(cname)
        container_specs.append(
            ChildContainerSpec(
                container_name=cname,
                container_description=(
                    field.description or f"Repeated {cname.replace('_', ' ')} records"
                ),
            )
        )
        recovered.append((cname, field.field_name))
    return stripped, recovered


def _collection_as_list_str_field(spec: ChildContainerSpec) -> FieldSpec:
    """Represent an underspecified repeated collection as a ``list[str]`` field.

    Used when a child collection has no per-item fields defined (e.g. the task
    says "items purchased" or "services offered" without naming any sub-fields).
    A list of strings is a faithful, non-degenerate representation — better than
    a ``list`` of empty objects, which would extract nothing.
    """
    label = spec.container_name.replace("_", " ")
    return FieldSpec(
        field_name=spec.container_name,
        field_type="list[str]",
        description=spec.container_description or f"List of {label}",
    )


def parse_nested_requirements(
    user_description: str,
    *,
    client=None,
    model: str = None,
    temperature: float | None = 0.0,
    reasoning_effort: str | None = None,
    _usage_sink: list | None = None,
    config: dict | None = None,
) -> tuple[
    type[BaseModel],
    ExtractionRequirements | CompositeExtractionRequirements,
    StructureAnalysis,
]:
    """
    Stage 2: Parse nested requirements by:
    1. Detecting structure type
    2. Parsing item-level fields
    3. Creating nested parent model

    Returns: (ParentModel, item_requirements, structure_analysis)

    ``temperature`` / ``reasoning_effort`` are forwarded to every underlying
    call; see :func:`_parse_with` for how the two interact on reasoning
    deployments.

    When ``_usage_sink`` is a list, OpenAI usage dicts from each underlying
    LLM call are appended to it. Internal hook for :class:`SchemaGenerator`;
    external callers can ignore it.
    """
    if client is None:
        config = config or get_openai_config(use_azure=True)
        client = build_compat_client(config)
        model = model if model else config["model"]
    elif model is None:
        raise ValueError("model must be provided when client is specified")

    print("Analyzing structure type...")
    sampling = {"temperature": temperature, "reasoning_effort": reasoning_effort, "config": config}
    analysis = detect_structure_type(
        user_description, client=client, model=model, _usage_sink=_usage_sink, **sampling
    )

    print(f"Structure type: {analysis.structure_type}")
    print(f"  Reasoning: {analysis.reasoning}")

    if analysis.structure_type == "flat":
        # Just parse as flat requirements
        print("Using flat structure")
        requirements = parse_user_requirements(
            user_description, client=client, model=model, _usage_sink=_usage_sink, **sampling
        )
        extraction_model = create_extraction_model(requirements)
        return extraction_model, requirements, analysis

    if analysis.structure_type == "parent_with_nested_list":
        print("Using parent-with-nested-list structure")
        print(f"  Parent fields: {analysis.parent_fields_description}")

        # Resolve the child containers the detector identified *before* parsing
        # the parent fields, so the parent parse can be told exactly which
        # repeated collections to exclude. Fall back to the legacy single-child
        # fields when the detector did not populate child_containers.
        container_specs = _resolve_child_containers(analysis)
        seen_container_names = {c.container_name for c in container_specs}
        print(f"  Child collections: {[c.container_name for c in container_specs]}")

        print("\nParsing parent-level fields...")
        parent_requirements = parse_user_requirements(
            _build_parent_task(user_description, container_specs),
            client=client,
            model=model,
            _usage_sink=_usage_sink,
            **sampling,
        )

        # Recovery: if the parent parse still emitted any list[dict] field, a
        # repeated collection leaked into the parent. Rather than failing, strip
        # each leaked field out of the parent and route it through the child
        # pipeline as its own container. This keeps the parser robust for any
        # number of repeated collections, whether or not the structure detector
        # enumerated them up front.
        parent_requirements, recovered = _reroute_leaked_collections(
            parent_requirements, container_specs, seen_container_names
        )
        for cname, original in recovered:
            print(
                f"  Recovered leaked repeated collection '{original}' "
                f"from parent -> child container '{cname}'"
            )

        # Final safety net: after recovery the parent must be scalar-only.
        _ensure_no_list_dict_fields(
            parent_requirements,
            context="Parent requirements for parent_with_nested_list",
        )

        children: list[ChildRequirements] = []
        for spec in container_specs:
            cname = spec.container_name
            cdesc = spec.container_description or f"Repeated {cname} records"
            print(f"\nParsing child fields for '{cname}'...")
            _child_task = (
                f"From the requirements below, parse only the fields for each repeated "
                f"{cname.replace('_', ' ')} record. "
                "Treat every field as a scalar value. "
                "Ignore any once-per-document, header, or summary fields. "
                "Ignore any other repeated sections not related to this collection.\n\n"
                + user_description
            )
            child_req = parse_user_requirements(
                _child_task,
                client=client,
                model=model,
                _usage_sink=_usage_sink,
                parse_mode="repeated_item",
                **sampling,
            )
            _ensure_no_list_dict_fields(child_req, context=f"Child requirements for '{cname}'")

            if not child_req.fields:
                # Underspecified collection — no per-item fields were described.
                # Represent it as a list[str] on the parent instead of a list of
                # empty objects (which would extract nothing).
                print(f"  '{cname}' has no per-item fields -> representing as list[str] on parent")
                existing_names = {f.field_name for f in parent_requirements.fields}
                if cname not in existing_names:
                    parent_requirements.fields.append(_collection_as_list_str_field(spec))
                continue

            print(f"  Fields: {[f.field_name for f in child_req.fields]}")
            children.append(
                ChildRequirements(
                    container_name=cname,
                    container_description=cdesc,
                    requirements=child_req,
                )
            )

        print(f"Identified parent fields: {[f.field_name for f in parent_requirements.fields]}")

        if not children:
            # Every repeated collection was underspecified and promoted to a
            # list[str] field, so the result is effectively a flat object.
            print("No structured child collections remain -> using flat model")
            extraction_model = create_extraction_model(parent_requirements)
            return extraction_model, parent_requirements, analysis

        print("\nCreating parent-with-nested-list Pydantic model...")
        extraction_model = _create_parent_with_nested_list_model(
            parent_requirements=parent_requirements,
            children=children,
        )
        composite_requirements = CompositeExtractionRequirements(
            parent_requirements=parent_requirements,
            children=children,
        )

        print(f"Created combined model: {extraction_model.__name__}")
        print(f"Child container fields: {[c.container_name for c in children]}")

        return extraction_model, composite_requirements, analysis

    # Nested structure
    print(f"Using nested structure with '{analysis.parent_container_name}' field")
    print(f"  Parent: {analysis.parent_description}")

    print("\nParsing item-level fields...")
    _item_task = (
        "From the requirements below, parse only the fields for each repeated "
        "item. Treat every field as a scalar value. "
        "Ignore any once-per-document, header, or summary fields.\n\n" + user_description
    )
    item_requirements = parse_user_requirements(
        _item_task,
        client=client,
        model=model,
        _usage_sink=_usage_sink,
        parse_mode="repeated_item",
        **sampling,
    )

    print(f"Identified {len(item_requirements.fields)} fields per item")
    print(f"  Fields: {[f.field_name for f in item_requirements.fields]}")
    _ensure_no_list_dict_fields(item_requirements, context="Nested list item requirements")

    print("\nCreating nested Pydantic model...")
    ItemModel = create_extraction_model(item_requirements)  # noqa: N806

    # Create parent model with items list
    suffix = "_Collection"
    base_name = sanitize_model_name(item_requirements.use_case_name, suffix=suffix)
    model_name = base_name + suffix

    ParentModel = create_model(  # noqa: N806
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

OVERRIDE RULE — Explicit representation instructions in the task text take priority
over all field-name heuristics below. Apply these mappings strictly, regardless of
what the field name suggests:
- "text string", "as text", "preserve exactly as written",
  "text string including the unit", "with the unit", "with the currency symbol"
  → field_type='str'  (even if the field name is "quantity", "price", "amount",
  "measurement", "reading", or another name that normally implies a numeric type)
- "choose from A, B, C", "one of: A, B, C", "select from: A, B, C",
  "Choose from: A, B, or C"
  → field_type='str' with enum=['A', 'B', 'C']
- "numeric, if stated, else null", "if stated, else null" on a numeric context
  → appropriate numeric type (float or int) with nullable=True
- "if stated, else null", "else null" on a text context
  → field_type='str' with nullable=True
- "return empty string if missing", "else empty string", "else ''"
  → field_type='str' with nullable=False and default=''

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
   - Date words in any language: "päivämäärä" (Finnish), "datum" (German),
     "fecha" (Spanish), etc.
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

10. DEFAULT VALUES (default, has_explicit_default):
   Set has_explicit_default=True when the task says "default is X",
   "if unclear return X", "otherwise return X", or states a primary value
   for an enum/binary choice. Set 'default' to that value.
   A general instruction to leave unmentioned/missing fields "empty" (e.g.
   "leave unmentioned fields empty", "leave blank if not found") is NOT a
   per-field default. Do not set has_explicit_default=True or default=''
   because of it -- especially for int/float/decimal/bool/list[str]/list[dict]
   fields, where an empty string is not a valid value for the type. Leave
   has_explicit_default=False for those fields instead; the correct
   type-safe fallback (null for numbers/booleans, an empty list for list
   fields) is applied automatically.

11. NULLABILITY (nullable):
   Default to nullable=False. Set True only when task explicitly allows
   null/None. If task says "do not use null" or "missing → ''", nullable=False.

12. REQUIRED IN OUTPUT (required_in_output):
   Default to True. Set False only when the task says "omit if not found"
   or "include only if present".

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
    user_description: str,
    *,
    client=None,
    model: str = None,
    temperature: float | None = 0.0,
    reasoning_effort: str | None = None,
    _usage_sink: list | None = None,
    parse_mode: RequirementsParseMode = "normal",
    config: dict | None = None,
) -> ExtractionRequirements:
    """
    Parse extraction requirements from natural language using LLM with type detection rules.
    Works with any input format - numbered lists, bullets, prose, tables, etc.

    ``temperature`` / ``reasoning_effort`` are passed straight to
    :func:`_parse_with`; see it for how the two interact on reasoning
    deployments.

    When ``_usage_sink`` is a list, the OpenAI usage dict from the underlying
    LLM call is appended to it. Internal hook for :class:`SchemaGenerator`;
    external callers can ignore it.
    """
    if client is None:
        config = config or get_openai_config(use_azure=True)
        client = build_compat_client(config)
        model = model if model else config["model"]
    elif model is None:
        raise ValueError("model must be provided when client is specified")

    cleaned_description = _clean_requirements_text(user_description)
    prompt = _build_parse_requirements_prompt(cleaned_description, parse_mode=parse_mode)

    resp = _parse_with(
        client=client,
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PARSER},
            {"role": "user", "content": prompt},
        ],
        response_format=ExtractionRequirements,
        temperature=temperature,
        reasoning_effort=reasoning_effort,
        config=config,
    )
    req = resp.choices[0].message.parsed
    # Keep the original line/bullet structure for field-scoped policy
    # detection. The prompt itself still uses the compact cleaned form.
    _apply_type_overrides(req, original_text=user_description)
    if _usage_sink is not None:
        _usage_sink.append(openai_usage_to_dict(resp))
    if getattr(resp, "usage", None):
        print(f"[parse_user_requirements] tokens={resp.usage.total_tokens}")
    return req


def _build_parse_requirements_prompt(
    cleaned_description: str,
    *,
    parse_mode: RequirementsParseMode = "normal",
) -> str:
    repeated_item_instruction = ""
    if parse_mode == "repeated_item":
        repeated_item_instruction = (
            "SPECIAL CONTEXT: You are parsing the schema for ONE repeated child "
            "row/item/record. The surrounding parent schema already contains the "
            "list field. Therefore, do NOT create any field with field_type "
            "'list[dict]'. Phrases such as 'for each item', 'for each row', "
            "'for each record', 'records containing', or 'items with fields' "
            "refer to the current single child object. Convert the named subfields "
            "into scalar fields on that child object.\n\n"
        )

    repeated_item_footer = ""
    if parse_mode == "repeated_item":
        repeated_item_footer = (
            "\n\nRepeated child row reminder:\n"
            "- The output model you are parsing is ONE row/item/record, not the "
            "list container.\n"
            "- Do not output a collection field such as items/rows/records.\n"
            "- Do not use field_type='list[dict]'.\n"
            "- If the text says 'For each record, extract name, date, status', "
            "return scalar fields like name, date, and status."
        )

    return (
        "Parse the extraction requirements below into the target schema.\n"
        + repeated_item_instruction
        + "Apply the type detection rules to determine "
        "the correct field_type for each field.\n"
        "If a field cannot be identified reliably, omit it.\n\n"
        "For each field, also determine:\n"
        "- required_in_output: must the key appear in every output object?\n"
        "- nullable: does the task explicitly allow null/None?\n"
        "- default + has_explicit_default: does the task state a fallback value?\n"
        "- enum: include '' in enum only when empty string is an allowed value.\n\n"
        "Treat output-key presence, nullability, and defaults as three independent "
        "properties:\n"
        "- required_in_output controls whether the key must appear in every output "
        "object. A requested field remains required_in_output=True even when its "
        "value is nullable, unless the task explicitly permits omitting the key.\n"
        "- nullable controls whether the field value may be JSON null/Python None. "
        "Instructions such as 'return null if not found' set nullable=True; they do "
        "not make the output key optional.\n"
        "- A default is a replacement value explicitly specified by the task. Set "
        "has_explicit_default=True only for such an explicit replacement. A null "
        "missing-value policy is not an explicit default: keep "
        "has_explicit_default=False and never translate null into ''.\n"
        "Use default='' only when the task explicitly requests an empty string. "
        "Never add '' to an enum unless the task explicitly lists empty string as "
        "an allowed value. If the task gives contradictory missing-value policies, "
        "follow the most specific field-level instruction rather than combining "
        "the policies. Missing repeated collections should be empty lists unless "
        "the task explicitly requests null for the collection.\n\n"
        "Choose types from the semantic role of the value, not from a keyword "
        "alone. Use field_type='str' for identifiers, codes, reference numbers, "
        "labels, and values whose original representation must be preserved. The "
        "word 'number' does not by itself imply a numeric type. If leading zeros, "
        "letters, punctuation, or exact formatting may matter, use 'str'. Fields "
        "such as note number, revision number, drawing number, item number, order "
        "number, and similar identifiers should normally be 'str' unless the task "
        "explicitly requires an integer. Use 'int' for whole-number counts or "
        "quantities intended for numeric use, and 'float' or 'decimal' for "
        "measurements or amounts intended for numeric use. Making a field nullable "
        "must not change its underlying field_type.\n\n"
        "Each field description must be self-contained. Preserve every "
        "field-specific output constraint from the original task, including "
        "date/time formats, units, ordering or composition rules, leading-zero "
        "requirements, exact-text or preserve-as-written instructions, casing, "
        "examples, and allowed choices. Copy format tokens and examples exactly. "
        "For example, never shorten 'Dispatch date (DD/MM/YYYY)' to 'Dispatch "
        "date'. Do not copy constraints from neighboring fields. Preserve "
        "field-specific constraints, but do not repeat task-wide extraction, "
        "inference, or missing-value rules in every field description. Even when "
        "format, enum, or pattern is populated separately, repeat the user-facing "
        "field-specific constraint in the field description.\n\n"
        "Set pattern=null unless the task explicitly states a regex/pattern.\n"
        "Set format=null unless the task explicitly states an output date format; "
        "never use descriptive placeholders such as 'date', 'string', or "
        "'lowercase_with_underscores' as a format.\n\n"
        + TYPE_DETECTION_RULES
        + repeated_item_footer
        + "\n\nRequirements to parse:\n```txt\n"
        + cleaned_description
        + "\n```"
    )


def _clean_requirements_text(text: str) -> str:
    """Trim whitespace noise while preserving numbered/bulleted structure."""
    lines = [line.strip() for line in text.splitlines()]
    cleaned_lines = [line for line in lines if line]
    return "\n".join(cleaned_lines)


# Date format patterns to detect from user requirements
DATE_FORMAT_PATTERNS: dict[str, str] = {
    # English: DD, MM, YYYY
    "dd/mm/yyyy": "%d/%m/%Y",
    "dd/mm/yyy": "%d/%m/%Y",
    "dd-mm-yyyy": "%d-%m-%Y",
    "dd.mm.yyyy": "%d.%m.%Y",
    "mm/dd/yyyy": "%m/%d/%Y",
    "mm-dd-yyyy": "%m-%d-%Y",
    "yyyy-mm-dd": "%Y-%m-%d",
    "yyyy/mm/dd": "%Y/%m/%d",
    "yyyy.mm.dd": "%Y.%m.%d",
    # Finnish: pp (päivä), kk (kuukausi), vvvv (vuosi)
    "pp/kk/vvvv": "%d/%m/%Y",
    "pp-kk-vvvv": "%d-%m-%Y",
    "pp.kk.vvvv": "%d.%m.%Y",
    "vvvv-kk-pp": "%Y-%m-%d",
    "vvvv.kk.pp": "%Y.%m.%d",
    # German: TT (Tag), MM (Monat), JJJJ (Jahr)
    "tt/mm/jjjj": "%d/%m/%Y",
    "tt-mm-jjjj": "%d-%m-%Y",
    "tt.mm.jjjj": "%d.%m.%Y",
    "jjjj-mm-tt": "%Y-%m-%d",
    "jjjj.mm.tt": "%Y.%m.%d",
}

# Date-related keywords in multiple languages for field detection
DATE_KEYWORDS = [
    "date",  # English
    "datum",  # German, Dutch, Swedish
    "fecha",  # Spanish
    "päivämäärä",  # Finnish
    "paivamaara",  # Finnish (ASCII)
    "päiväys",  # Finnish (alternative)
    "paivays",  # Finnish (ASCII alternative)
    "data",  # Italian, Portuguese, Polish
    "jour",  # French
    "dátum",  # Hungarian
    "dato",  # Norwegian, Danish
    "tarih",  # Turkish
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


SUPPORTED_DATE_OUTPUT_FORMATS = frozenset(DATE_FORMAT_PATTERNS.values())

_GLOBAL_DATE_FORMAT_SCOPE_RE = re.compile(
    r"\b(?:all|every)\s+(?:output\s+)?dates?\b|"
    r"\bdate\s+fields?\b|"
    r"\bfor\s+(?:all\s+)?dates?\b",
    re.IGNORECASE,
)

_TEXT_REPRESENTATION_RE = re.compile(
    r"\b(?:text\s+string|as\s+text|as\s+a\s+string|"
    r"preserve(?:\s+the)?(?:\s+original)?\s+(?:format|wording|value)|"
    r"preserve\s+exactly\s+as\s+written|exactly\s+as\s+written|"
    r"preserve\s+format\s+in\s+(?:a\s+)?string|"
    r"including\s+the\s+unit|with\s+the\s+unit)\b",
    re.IGNORECASE,
)

_EXPLICIT_PATTERN_RE = re.compile(r"\b(?:regex|regular\s+expression|pattern)\b", re.IGNORECASE)


def _field_specific_context(field: FieldSpec, original_text: str) -> str:
    """Return task text scoped to ``field`` instead of the whole task.

    The requirements LLM is allowed to summarize field descriptions, so an
    explicit representation instruction can be present only in the original
    task. Search the field's own clause/bullet and never borrow a neighboring
    field's format. This prevents ``Delivery Date (DD/MM/YYYY)`` from silently
    changing ``Order Date`` as well.
    """
    pieces: list[str] = []
    label = field.field_name.replace("_", " ")
    label_re = re.compile(rf"\b{re.escape(label)}\b", re.IGNORECASE)
    lines = original_text.splitlines()

    for index, line in enumerate(lines):
        match = label_re.search(line)
        if not match:
            continue

        # A prose line often lists several fields. Keep only this field's
        # comma/semicolon/period-delimited clause so one field's parenthesized
        # format cannot leak into another field on the same line.
        clause_chars: list[str] = []
        depth = 0
        for char in line[match.start() :]:
            if char in "([":
                depth += 1
            elif char in ")]" and depth:
                depth -= 1
            if depth == 0 and char in ",;." and clause_chars:
                break
            clause_chars.append(char)
        pieces.append("".join(clause_chars))

        # Support a bullet whose following indented lines carry the detailed
        # representation instruction.
        if re.match(r"^\s*(?:[-*]|\d+[.)])\s+", line):
            for following in lines[index + 1 :]:
                if not following.strip() or re.match(r"^\s*(?:[-*]|\d+[.)])\s+", following):
                    break
                pieces.append(following)

    return "\n".join(piece for piece in pieces if piece)


def _detect_global_date_format(text: str) -> str | None:
    """Return a format only when the task explicitly scopes it to all dates."""
    for clause in re.split(r"(?<=[.!?])\s+|\n", text):
        if _GLOBAL_DATE_FORMAT_SCOPE_RE.search(clause):
            detected = _detect_date_format(clause)
            if detected:
                return detected
    return None


def _requests_text_representation(text: str) -> bool:
    return bool(_TEXT_REPRESENTATION_RE.search(text))


def _is_date_field(name: str, description: str) -> bool:
    """Check if a field is a date field based on name or description (multilingual)."""
    name_lower = name.lower()
    desc_lower = description.lower()
    for keyword in DATE_KEYWORDS:
        if keyword in name_lower or keyword in desc_lower:
            return True
    return False


def _apply_type_overrides(requirements: ExtractionRequirements, original_text: str = "") -> None:
    """
    Apply deterministic heuristics to FieldSpec entries to enforce critical types
    even when the LLM guesses incorrectly (e.g., date fields must be typed as date).
    Also detects date output format from field descriptions.
    Supports multiple languages for date detection.
    """
    global_date_format = _detect_global_date_format(original_text)

    for field in requirements.fields:
        field_context = _field_specific_context(field, original_text)

        # ``pattern`` and ``format`` remain permissive strings in the
        # LLM-facing FieldSpec so a non-OpenAI provider cannot fail validation
        # before this cleanup runs. Treat both as untrusted afterwards: models
        # have copied schema metadata such as "lowercase_with_underscores",
        # "string", and "^.*$" into these properties.
        if not _EXPLICIT_PATTERN_RE.search(field_context):
            field.pattern = None

        if _is_date_field(field.field_name, field.description):
            if _requests_text_representation(field_context):
                field.field_type = "str"
                field.format = None
                continue

            field.field_type = "date"
            detected_format = _detect_date_format(field_context)
            field.format = detected_format or global_date_format
            continue

        field.format = None

        # Match the documented type rule for plain quantities/counts, while
        # preserving an explicit request for text or a unit-bearing string.
        is_integer_count = (
            field.field_name == "quantity"
            or field.field_name.endswith("_quantity")
            or field.field_name == "count"
            or field.field_name.endswith("_count")
        )
        if (
            is_integer_count
            and field.field_type == "str"
            and not _requests_text_representation(field_context)
        ):
            field.field_type = "int"


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


# -----------------------------------------------------------------------------
# Decimal field safety
#
# Pydantic's default JSON Schema for a Decimal field is
# ``anyOf: [number, string(pattern=<negative-lookahead regex>), null]``. Some
# structured-output providers reject the whole request over that unsupported
# regex feature; others accept the request but then crash when the model
# writes something like "12.40 EUR" into the field, since Decimal parsing
# rejects it. DECIMAL_JSON_SCHEMA / DECIMAL_JSON_SCHEMA_OR_NULL replace the
# advertised schema with a plain string (no pattern, so no provider can
# reject it on regex-support grounds; a JSON string also preserves full
# precision, unlike a JSON number, which several providers/parsers round-trip
# through a 64-bit float and silently truncate past ~17 significant digits).
# _clean_decimal_string then strips common currency/unit noise before Decimal
# parsing runs, so a model's "12.40 EUR" still resolves to Decimal('12.40')
# instead of crashing.
# -----------------------------------------------------------------------------

DECIMAL_JSON_SCHEMA = {"type": "string"}
DECIMAL_JSON_SCHEMA_OR_NULL = {"anyOf": [{"type": "string"}, {"type": "null"}]}

_CURRENCY_NOISE_RE = re.compile(r"(?i)\b(EUR|USD|GBP|JPY|CHF|SEK|NOK|DKK|CAD|AUD|INR)\b|[€$£¥₹]")
# Exactly one signed amount: comma is accepted only as a thousands separator
# in groups of exactly 3 digits, dot only as the decimal separator. European
# comma-decimal formatting ("1.234,56") and multi-number/ambiguous strings
# are deliberately NOT interpreted -- see _clean_decimal_string's docstring.
_SINGLE_AMOUNT_RE = re.compile(r"^[-+]?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$")


def _clean_decimal_string(v):
    """Strip currency/unit noise from a numeric string before Decimal parsing.

    Explicit, conservative policy -- this does not attempt general-purpose
    number parsing:

    - Known currency codes/symbols (EUR, USD, "$", "€", etc.) and surrounding
      whitespace are stripped.
    - What remains must be exactly one well-formed amount: an optional sign,
      digits optionally grouped in thousands of exactly 3 via ``,``, and an
      optional ``.``-delimited fractional part. Anything else -- multiple
      embedded numbers ("abc1def2"), space-grouped or comma-decimal
      formatting ("1 234,56"), malformed grouping ("1,23.56"), or leftover
      non-numeric text -- is rejected outright rather than guessed at.
    - Rejected or blank input resolves to ``None``, matching the fallback
      already used elsewhere for blank/unparseable numeric values -- not a
      crash, and not a fabricated number from a partial match.

    Non-string input (already a Decimal/int/float/None) passes through
    unchanged.
    """
    if not isinstance(v, str):
        return v
    s = v.strip()
    if not s:
        return None
    s = _CURRENCY_NOISE_RE.sub("", s).strip()
    if not s:
        return None
    if not _SINGLE_AMOUNT_RE.match(s):
        return None
    return s.replace(",", "")


DecimalField = Annotated[
    Decimal,
    WithJsonSchema(DECIMAL_JSON_SCHEMA),
    BeforeValidator(_clean_decimal_string),
]
OptionalDecimalField = Annotated[
    Decimal | None,
    WithJsonSchema(DECIMAL_JSON_SCHEMA_OR_NULL),
    BeforeValidator(_clean_decimal_string),
]


def decimal_field_repr(annotation) -> str | None:
    """Return "DecimalField"/"OptionalDecimalField" if ``annotation`` is
    ``Decimal`` or ``Decimal | None`` (any Optional spelling), else ``None``.

    Shared by every schema-persistence writer (schema_generation_example.py,
    vision_extractor.py's _save_schema_to_python) so a Decimal field is always
    routed to the safe representation instead of the plain type -- necessary
    because field.annotation strips the Annotated/WithJsonSchema/BeforeValidator
    wrapping create_extraction_model applies, so introspecting the bare
    annotation alone can no longer tell a "made safe" Decimal field apart from
    a plain one.
    """
    if annotation is Decimal:
        return "DecimalField"

    args: tuple = ()
    origin = get_origin(annotation)
    if origin is Union:
        args = get_args(annotation)
    else:
        try:
            import types as _types

            if isinstance(annotation, _types.UnionType):
                args = get_args(annotation)
        except AttributeError:
            pass

    if Decimal in args and type(None) in args:
        return "OptionalDecimalField"
    return None


# Standalone Python source for a persisted schema.py's header, reconstructing
# the same Decimal safety net as DECIMAL_JSON_SCHEMA(_OR_NULL) /
# _clean_decimal_string above. field.annotation strips Annotated metadata (see
# decimal_field_repr's docstring), so a persisted schema regenerated from bare
# field.annotation values would otherwise silently revert to a plain
# `Optional[Decimal]` -- restoring both the regex-lookaround schema-rejection
# failure and the "12.40 EUR"-crashes-Decimal-parsing failure on next load.
# Persisted files are meant to be standalone (no gaik import), so this is
# embedded as literal source text rather than imported at reload time. Keep
# this in sync with the block above if that logic ever changes.
DECIMAL_PERSISTED_HELPER_SOURCE = r'''
import re as _re
from decimal import Decimal
from typing import Annotated

from pydantic import BeforeValidator, WithJsonSchema

_CURRENCY_NOISE_RE = _re.compile(
    r"(?i)\b(EUR|USD|GBP|JPY|CHF|SEK|NOK|DKK|CAD|AUD|INR)\b|[€$£¥₹]"
)
_SINGLE_AMOUNT_RE = _re.compile(r"^[-+]?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$")


def _clean_decimal_string(v):
    """Strip currency/unit noise before Decimal parsing; reject (return None)
    ambiguous or multi-number input rather than fabricating a value. See
    gaik.software_components.extractor.schema._clean_decimal_string for the
    full policy this mirrors."""
    if not isinstance(v, str):
        return v
    s = v.strip()
    if not s:
        return None
    s = _CURRENCY_NOISE_RE.sub("", s).strip()
    if not s:
        return None
    if not _SINGLE_AMOUNT_RE.match(s):
        return None
    return s.replace(",", "")


DecimalField = Annotated[
    Decimal, WithJsonSchema({"type": "string"}), BeforeValidator(_clean_decimal_string)
]
OptionalDecimalField = Annotated[
    Decimal | None,
    WithJsonSchema({"anyOf": [{"type": "string"}, {"type": "null"}]}),
    BeforeValidator(_clean_decimal_string),
]
'''


def _normalize_explicit_default(
    f: FieldSpec,
) -> tuple[bool, str | int | float | Decimal | bool | None]:
    """Resolve whether ``f`` carries a *usable* explicit default for its type.

    ``FieldSpec.default`` is always a string (or ``None``), regardless of
    ``field_type``, because the requirements-parsing LLM can only express a
    default as text. A general instruction such as "leave unmentioned fields
    empty" is sometimes parsed into ``has_explicit_default=True, default=""``
    even for numeric, boolean, or list fields, where an empty string is not a
    valid value for the annotated type. Left unchecked this produces fields
    like ``int = Field(default='')`` that Pydantic v2 does not validate at
    build time (no ``validate_default=True``) but fails to revalidate later
    (``model_validate_json`` -> ``int('')`` -> ``ValidationError``).

    This is the single place that decides whether a declared default should
    actually be honored, so :func:`create_extraction_model` and
    :func:`_resolve_fallback` can never disagree. Returns
    ``(effective_has_explicit_default, effective_default)``; when the first
    element is ``False`` the second is meaningless and callers must apply the
    type's normal (non-explicit-default) fallback policy, exactly as if
    ``f.has_explicit_default`` had been ``False`` to begin with.
    """
    if not f.has_explicit_default:
        return False, None

    raw = f.default

    if f.field_type in ("str", "date"):
        # Already the field's native type -- including "", the documented
        # "missing" sentinel for text fields.
        return True, raw if raw is not None else ""

    if raw is None or raw == "":
        # Not a real default for any non-text type; treat as unset so the
        # caller falls through to the type's own empty-value fallback.
        return False, None

    if f.field_type in ("int", "float", "decimal"):
        try:
            if f.field_type == "int":
                return True, int(raw)
            if f.field_type == "float":
                value = float(raw)
                # float("nan"/"inf"/"-inf") all parse without raising, but a
                # non-finite default silently corrupts JSON round-tripping:
                # NaN serializes as `null` (indistinguishable from "unset"),
                # and both fail model_validate_json on the way back in.
                if not math.isfinite(value):
                    return False, None
                return True, value
            # Reuse the same conservative cleaner extraction values go
            # through, so a stated default like "9.99 EUR" is handled the
            # same way an extracted value would be, rather than raising here.
            cleaned = _clean_decimal_string(raw)
            if cleaned is None:
                return False, None
            value = Decimal(cleaned)
            if not value.is_finite():
                return False, None
            return True, value
        except (ValueError, ArithmeticError):
            return False, None

    if f.field_type == "bool":
        lowered = raw.strip().lower()
        if lowered == "true":
            return True, True
        if lowered == "false":
            return True, False
        return False, None

    # list[str] / list[dict]: a scalar string is never a valid list default;
    # do not invent comma-splitting or other parsing rules for it.
    return False, None


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
        annotated: object = py_type

        if f.field_type == "str" and f.pattern:
            annotated = Annotated[str, constr(pattern=f.pattern)]

        has_default, default = _normalize_explicit_default(f)

        if f.enum:
            if has_default:
                if default not in f.enum:
                    f.enum.append(default)
                annotated = Literal[tuple(f.enum)]  # type: ignore[misc,call-arg]
            else:
                values = [""] + f.enum if "" not in f.enum else f.enum
                annotated = Literal[tuple(values)]  # type: ignore[misc,call-arg]

        # Numeric and boolean fields have no natural "empty" value the way
        # ""/[] serve str/list fields, so a missing default -- whether never
        # declared, or an explicit default discarded as type-incompatible by
        # _normalize_explicit_default -- widens the annotation to accept None
        # instead, mirroring the pre-existing numeric-fallback policy.
        #
        # For bool specifically this is a deliberate, separate behavior
        # decision (not just a side effect of the default-type fix above):
        # a plain non-nullable `bool` field with no default used to build as
        # Pydantic-required, while _resolve_fallback's post-processing
        # fallback for a missing key is None regardless of type -- and in
        # VisionExtractor.extract(), _post_process() (which calls
        # apply_field_policies) runs BEFORE the final _validate_result()
        # against the original extraction_model. So a vision response that
        # genuinely omits a bool key gets patched to None by
        # apply_field_policies and then fails that final validation unless
        # the annotation itself is nullable. Widening bool here fixes it at
        # the source. (DataExtractor's OpenAI/.parse() path and
        # ProviderClient.chat_parsed() both validate strictly before
        # apply_field_policies ever runs, so they don't depend on
        # apply_field_policies's fallback value -- but they still benefit
        # from this same annotation change, since a missing key against an
        # optional-with-default field is accepted by model_validate without
        # needing the key present at all.)
        uses_none_fallback = (
            (f.field_type in NUMERIC_FIELD_TYPES or f.field_type == "bool")
            and not has_default
            and not f.nullable
        )

        if f.field_type == "decimal":
            # See the "Decimal field safety" block above _normalize_explicit_default
            # for why Decimal needs its own JSON Schema override + cleaner.
            # Nullability is decided by the exact same condition as every
            # other type (below); a field with a valid explicit default stays
            # non-nullable, matching str/enum/numeric behavior -- this branch
            # must not hardcode `Decimal | None` unconditionally. It also
            # resolves nullability itself rather than falling through to the
            # generic widening below: `(Annotated[Decimal | None, ...]) |
            # None` double-wraps into `Optional[Annotated[...]]`, which
            # pydantic still validates correctly but which field.annotation
            # then reports in a shape neither schema-persistence writer's
            # annotation-repr helper can unwrap -- breaking schema save/load
            # (see save_schema_to_python / _save_schema_to_python).
            is_nullable = f.nullable or uses_none_fallback
            annotated = OptionalDecimalField if is_nullable else DecimalField
        elif f.nullable or uses_none_fallback:
            annotated = annotated | None

        if has_default:
            default_val = default
        elif f.nullable:
            default_val = None
        elif uses_none_fallback:
            default_val = None
        elif f.field_type in ("list[str]", "list[dict]"):
            default_val = []
        elif f.enum:
            default_val = ""
        else:
            default_val = ...

        if f.field_type in ("list[str]", "list[dict]") and default_val == []:
            field_defs[f.field_name] = (
                annotated,
                Field(default_factory=list, description=f.description),
            )
        else:
            field_defs[f.field_name] = (
                annotated,
                Field(default=default_val, description=f.description),
            )

    suffix = "_Extraction"
    base_name = sanitize_model_name(requirements.use_case_name, suffix=suffix)
    model_name = base_name + suffix

    DynamicModel = create_model(  # noqa: N806
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
        "%Y-%m-%d",  # ISO: 2024-04-25
        "%d/%m/%Y",  # European: 25/04/2024
        "%d-%m-%Y",  # European with dash: 25-04-2024
        "%d.%m.%Y",  # European with dot: 25.04.2024
        "%m/%d/%Y",  # US: 04/25/2024
        "%m-%d-%Y",  # US with dash: 04-25-2024
        "%Y/%m/%d",  # ISO with slash: 2024/04/25
        "%Y.%m.%d",  # ISO with dot: 2024.04.25
        "%B %d, %Y",  # Full month: April 25, 2024
        "%d %B %Y",  # Day first: 25 April 2024
        "%b %d, %Y",  # Short month: Apr 25, 2024
        "%d %b %Y",  # Day first short: 25 Apr 2024
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
            if isinstance(value, str) and not value.strip():
                result[key] = value
            else:
                # FieldSpec.format comes from an LLM-facing schema and must not
                # be trusted blindly. A value such as "date" is a valid
                # strftime literal and would collapse every parsed date to the
                # word "date". Only formats recognized by our deterministic
                # detector may override the caller's default.
                date_format = (
                    spec.format
                    if spec.format in SUPPORTED_DATE_OUTPUT_FORMATS
                    else default_date_format
                )
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
        default = field_info.default
        if is_required:
            if description:
                print(f'    {field_name}: {type_str} = Field(description="{description}")')
            else:
                print(f"    {field_name}: {type_str}")
        else:
            from pydantic_core import PydanticUndefined

            if default is PydanticUndefined and field_info.default_factory is not None:
                default_repr = repr(field_info.default_factory())
            else:
                default_repr = repr(default)
            if description:
                print(
                    f"    {field_name}: {type_str} = "
                    f'Field(default={default_repr}, description="{description}")'
                )
            else:
                print(f"    {field_name}: {type_str} = {default_repr}")


# -----------------------------------------------------------------------------
# Post-processing: deterministic field policy enforcement
# -----------------------------------------------------------------------------


def _resolve_fallback(field: FieldSpec):
    has_default, default = _normalize_explicit_default(field)
    if has_default:
        return default
    if field.field_type in ("str", "date"):
        return ""
    if field.field_type in ("list[str]", "list[dict]"):
        return []
    return None


def apply_field_policies(data: dict, requirements: ExtractionRequirements) -> dict:
    spec_by_name = {f.field_name: f for f in requirements.fields}
    output = {}

    for name, field in spec_by_name.items():
        if name not in data:
            if field.required_in_output:
                output[name] = _resolve_fallback(field)
            continue

        value = data[name]

        if value is None:
            if field.nullable:
                output[name] = None
                continue
            value = _resolve_fallback(field)

        if field.field_type in NUMERIC_FIELD_TYPES and isinstance(value, str) and not value.strip():
            value = _resolve_fallback(field)

        if field.enum and value not in field.enum:
            value = _resolve_fallback(field)

        output[name] = value

    for name, value in data.items():
        if name not in output:
            output[name] = value

    return output


def _map_over_composite(
    data: dict,
    requirements: CompositeExtractionRequirements,
    per_record: Callable[[dict, ExtractionRequirements], dict],
) -> dict:
    """Apply a flat per-record post-processor across a parent-with-children record.

    ``per_record`` runs once on the parent's own (scalar) fields, then once per
    item in each recognised child container using *that container's* own
    requirements. Applying the parent specs to child items would be wrong: it
    injects the parent's required fields into every child row.

    A container that was demoted to a ``list[str]`` parent field (see
    ``parse_nested_requirements``) is absent from ``children``, so it stays with
    the parent and is policed as the scalar list it now is. Any key belonging to
    neither side passes through untouched.
    """
    child_by_name = {c.container_name: c.requirements for c in requirements.children}

    parent_only = {k: v for k, v in data.items() if k not in child_by_name}
    output = per_record(parent_only, requirements.parent_requirements)

    for name, child_req in child_by_name.items():
        if name not in data:
            continue
        value = data[name]
        if isinstance(value, list):
            output[name] = [
                per_record(item, child_req) if isinstance(item, dict) else item for item in value
            ]
        else:
            output[name] = value

    return output


def apply_composite_field_policies(
    data: dict, requirements: CompositeExtractionRequirements
) -> dict:
    """``apply_field_policies`` for a ``parent_with_nested_list`` record.

    Policies are enforced against the parent requirements for the parent's own
    fields and against each child container's requirements for its items.
    """
    return _map_over_composite(data, requirements, apply_field_policies)


def normalize_composite_extracted_data(
    data: dict, requirements: CompositeExtractionRequirements
) -> dict:
    """``normalize_extracted_data`` for a ``parent_with_nested_list`` record."""
    return _map_over_composite(data, requirements, normalize_extracted_data)


# -----------------------------------------------------------------------------
# REUSABLE CLASS INTERFACE
# -----------------------------------------------------------------------------


@dataclass
class SchemaGenerationResult:
    """Structured return value from :meth:`SchemaGenerator.generate_schema_with_usage`.

    Attributes:
        schema: The generated Pydantic model class (same object that
            :meth:`SchemaGenerator.generate_schema` returns).
        requirements: Parsed field specifications. For parent_with_nested_list
            schemas this is a CompositeExtractionRequirements object containing
            separate parent and child requirements.
        structure_analysis: Whether the schema is flat or nested, plus
            the structure-detection reasoning.
        usage: Aggregated token usage across the underlying LLM calls
            (typically 2 — structure detection + requirement parsing).
            ``None`` when none of the responses carried a usage payload.
        duration_s: Wall-clock seconds the schema generation took.
        model: Resolved model identifier the calls used.
    """

    schema: type[BaseModel]
    requirements: ExtractionRequirements | CompositeExtractionRequirements
    structure_analysis: StructureAnalysis
    usage: UsageRecord | None
    duration_s: float
    model: str


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

        # Or call generate_schema_with_usage() to also receive token /
        # latency / cost in the return value.
    """

    def __init__(
        self,
        config: dict,
        model: str | None = None,
        *,
        temperature: float | None = 0.0,
        reasoning_effort: str | None = None,
    ):
        """
        Initialize the SchemaGenerator.

        Args:
            config: Provider configuration from get_llm_config(), or a legacy
                OpenAI configuration dict from get_openai_config().
            model: Optional model name override
            temperature: Sampling temperature for every schema-generation call.
                Defaults to ``0.0`` so the same requirements yield the same
                schema. ``None`` omits the parameter from the request.
            reasoning_effort: Reasoning effort for a gpt-5.x reasoning
                deployment; not sent by default, since the non-reasoning models
                reject it. The two settings are coupled — a reasoning
                deployment accepts an explicit temperature only at effort
                ``"none"``, so run it either as ``reasoning_effort="none"``
                (determinism kept) or as an active effort with
                ``temperature=None``. See :func:`_parse_with`.
        """
        self.config = config
        self.model = model if model else self.config["model"]
        self.temperature = temperature
        self.reasoning_effort = reasoning_effort
        self.client = build_compat_client(self.config)
        self.extraction_model = None
        self.item_requirements = None
        self.structure_analysis = None
        # Side-channel attributes populated by both generate_schema()
        # and generate_schema_with_usage(). Useful for callers who do
        # not want to switch methods just to read usage.
        self.last_usage: UsageRecord | None = None
        self.last_duration_s: float = 0.0

    def analyze_structure(self, user_requirements: str) -> StructureAnalysis:
        """
        Analyze if the requirements need nested or flat structure.

        Args:
            user_requirements: Natural language description of extraction task

        Returns:
            StructureAnalysis with structure type and descriptions
        """
        self.structure_analysis = detect_structure_type(
            user_requirements,
            client=self.client,
            model=self.model,
            temperature=self.temperature,
            reasoning_effort=self.reasoning_effort,
            config=self.config,
        )
        return self.structure_analysis

    def _generate_schema_inner(
        self, user_requirements: str
    ) -> tuple[type[BaseModel], UsageRecord | None, float]:
        """Run schema generation and capture aggregated usage + latency.

        Returns ``(model, usage, duration_s)``. Internal helper shared by
        :meth:`generate_schema` and :meth:`generate_schema_with_usage`.
        """
        usage_sink: list[dict[str, int]] = []
        with measure_duration() as elapsed:
            (
                self.extraction_model,
                self.item_requirements,
                self.structure_analysis,
            ) = parse_nested_requirements(
                user_requirements,
                client=self.client,
                model=self.model,
                temperature=self.temperature,
                reasoning_effort=self.reasoning_effort,
                config=self.config,
                _usage_sink=usage_sink,
            )
        duration_s = round(elapsed(), 3)

        # Aggregate usage dicts across the (typically 2) LLM calls.
        if usage_sink:
            totals = {
                "input_tokens": sum(u.get("input_tokens", 0) for u in usage_sink),
                "output_tokens": sum(u.get("output_tokens", 0) for u in usage_sink),
                "thinking_tokens": sum(u.get("thinking_tokens", 0) for u in usage_sink),
                "total_tokens": sum(u.get("total_tokens", 0) for u in usage_sink),
            }
            usage = (
                build_usage_record("openai", self.model, totals, duration_s)
                if totals["total_tokens"] > 0
                else None
            )
        else:
            usage = None

        self.last_usage = usage
        self.last_duration_s = duration_s
        return self.extraction_model, usage, duration_s

    def generate_schema(self, user_requirements: str) -> type[BaseModel]:
        """
        Generate Pydantic schema from natural language requirements.

        Args:
            user_requirements: Natural language description of fields to extract

        Returns:
            Generated Pydantic model class (nested or flat).

        After the call, ``generator.last_usage`` and
        ``generator.last_duration_s`` expose token usage and wall-clock
        latency without having to switch to
        :meth:`generate_schema_with_usage`.
        """
        print("Generating schema from requirements...")
        self._generate_schema_inner(user_requirements)

        # Print the generated Pydantic model
        print("\n" + "=" * 80)
        print("GENERATED PYDANTIC MODEL")
        print("=" * 80)
        print_pydantic_schema(self.extraction_model, title="Extraction Schema")

        return self.extraction_model

    def generate_schema_with_usage(self, user_requirements: str) -> SchemaGenerationResult:
        """
        Generate schema and report token usage + latency + cost.

        Same input as :meth:`generate_schema`; returns a
        :class:`SchemaGenerationResult` aggregating usage across the
        underlying LLM calls (structure detection + requirement parsing).
        """
        print("Generating schema from requirements...")
        schema, usage, duration_s = self._generate_schema_inner(user_requirements)

        print("\n" + "=" * 80)
        print("GENERATED PYDANTIC MODEL")
        print("=" * 80)
        print_pydantic_schema(schema, title="Extraction Schema")

        return SchemaGenerationResult(
            schema=schema,
            requirements=self.item_requirements,
            structure_analysis=self.structure_analysis,
            usage=usage,
            duration_s=duration_s,
            model=self.model,
        )

    def get_schema_info(self) -> dict:
        """
        Get information about the generated schema.

        Returns:
            Dict with schema information
        """
        if not self.extraction_model:
            return {"error": "No schema generated yet. Call generate_schema() first."}

        requirements = self.item_requirements
        if isinstance(requirements, CompositeExtractionRequirements):
            fields = {
                "parent": [f.field_name for f in requirements.parent_requirements.fields],
            }
            for child in requirements.children:
                fields[child.container_name] = [f.field_name for f in child.requirements.fields]
            field_count = len(requirements.parent_requirements.fields) + sum(
                len(child.requirements.fields) for child in requirements.children
            )
        else:
            fields = [f.field_name for f in requirements.fields] if requirements else []
            field_count = len(requirements.fields) if requirements else 0

        return {
            "model_name": self.extraction_model.__name__,
            "structure_type": self.structure_analysis.structure_type
            if self.structure_analysis
            else "unknown",
            "fields": fields,
            "field_count": field_count,
        }
