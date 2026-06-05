"""
Single-pass vision extraction: PDF/image → structured data in one LLM call.
"""

from __future__ import annotations

import importlib.util
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Union, get_args, get_origin

import requests
from pydantic import BaseModel, Field, create_model
from pydantic_core import PydanticUndefined

from gaik.observability import UsageRecord, build_usage_record
from gaik.software_components.extractor import (
    CompositeExtractionRequirements,
    ExtractionRequirements,
    SchemaGenerator,
)
from gaik.software_components.extractor.schema import (
    NUMERIC_FIELD_TYPES,
    apply_field_policies,
    normalize_extracted_data,
)
from gaik.software_components.parsers.multimodal_parser.config import (
    create_claude_client,
    create_openai_client,
    get_google_access_token,
    get_openai_config,
)
from gaik.software_components.parsers.multimodal_parser.multimodal_parser import (
    _encode_pdf_base64,
    _extract_claude_usage,
    _extract_google_usage,
    _extract_openai_usage,
)

from .prompts import SYSTEM_PROMPTS, USER_PROMPTS, VERIFICATION_PROMPT

ModelProvider = Literal["openai", "claude", "google"]
ReasoningEffort = Literal["low", "medium", "high"]
RequirementsSpec = ExtractionRequirements | CompositeExtractionRequirements

# ---------------------------------------------------------------------------
# Supported file types
# ---------------------------------------------------------------------------

SUPPORTED_MIME_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".bmp": "image/bmp",
}


def _detect_mime_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext not in SUPPORTED_MIME_TYPES:
        raise ValueError(
            f"Unsupported file type '{ext}'. Supported: {sorted(SUPPORTED_MIME_TYPES)}"
        )
    return SUPPORTED_MIME_TYPES[ext]


def _is_pdf(path: Path) -> bool:
    return path.suffix.lower() == ".pdf"


# ---------------------------------------------------------------------------
# Verification helpers
# ---------------------------------------------------------------------------


class VerifiableField(BaseModel):
    """Base model for a field wrapped with verification metadata.

    Each field in a wrapped extraction model is represented as a subclass of
    VerifiableField with a typed ``value`` attribute. Use ``include_verification=True``
    on VisionExtractor to enable wrapping automatically at runtime.
    """

    confidence_score: float = Field(ge=0.01, le=1.0)
    confidence_reason: str = Field(max_length=400)


def _wrap_model_for_verification(model: type[BaseModel]) -> type[BaseModel]:
    """Wrap each scalar field of a Pydantic model in a {value, confidence_score, reasoning} envelope.

    For list[BaseModel] fields, wraps the item model recursively so that verification
    metadata appears on each row's scalar fields, not at the container level.
    """
    wrapped_fields: dict = {}
    for fname, finfo in model.model_fields.items():
        annotation = finfo.annotation
        outer_field = Field(description=finfo.description)
        if get_origin(annotation) is list:
            args = get_args(annotation)
            if args and isinstance(args[0], type) and issubclass(args[0], BaseModel):
                # list[ItemModel] — recursively wrap the item model
                wrapped_item = _wrap_model_for_verification(args[0])
                wrapped_fields[fname] = (list[wrapped_item], outer_field)
            else:
                # list of scalars — pass through
                if finfo.default_factory is not None:
                    scalar_list_field = Field(
                        default_factory=finfo.default_factory,
                        description=finfo.description,
                    )
                elif finfo.is_required():
                    scalar_list_field = Field(description=finfo.description)
                else:
                    scalar_list_field = Field(
                        default=finfo.default,
                        description=finfo.description,
                    )
                wrapped_fields[fname] = (annotation, scalar_list_field)
        else:
            if finfo.default is PydanticUndefined and finfo.default_factory is not None:
                value_field = Field(
                    default_factory=finfo.default_factory,
                    description=finfo.description,
                )
            elif finfo.is_required():
                value_field = Field(description=finfo.description)
            else:
                value_field = Field(default=finfo.default, description=finfo.description)

            verifiable = create_model(
                f"{fname}_Verifiable",
                __base__=VerifiableField,
                value=(annotation, value_field),
            )
            wrapped_fields[fname] = (verifiable, outer_field)

    return create_model(
        f"{model.__name__}_Verifiable",
        __config__=model.model_config,
        **wrapped_fields,
    )


def _unwrap_verification(result_dict: dict) -> tuple[dict, dict]:
    """Split a wrapped LLM result into flat data + per-field verification metadata.

    Handles both flat models and nested list[BaseModel] structures recursively.
    """
    data: dict = {}
    verification: dict = {}
    for fname, wrapped in result_dict.items():
        if isinstance(wrapped, list) and wrapped and isinstance(wrapped[0], dict):
            # list[ItemModel] — recurse into each row
            item_data_list, item_ver_list = [], []
            for item in wrapped:
                item_data, item_ver = _unwrap_verification(item)
                item_data_list.append(item_data)
                item_ver_list.append(item_ver)
            data[fname] = item_data_list
            if any(item_ver_list):
                verification[fname] = item_ver_list
        elif isinstance(wrapped, dict) and "value" in wrapped and "confidence_score" in wrapped:
            data[fname] = wrapped["value"]
            verification[fname] = {
                "confidence_score": wrapped["confidence_score"],
                "confidence_reason": wrapped.get("confidence_reason", ""),
            }
        else:
            data[fname] = wrapped
    return data, verification


def _combine_with_verification(data: dict, verification: dict) -> dict:
    """Recursively merge post-processed data with verification metadata.

    Scalar fields: {"field": "val"} + {"field": {confidence_score, confidence_reason}}
                   → {"field": {"value": "val", "confidence_score": ..., "confidence_reason": ...}}

    List fields:   each row is combined recursively.
    """
    result: dict = {}
    for field, value in data.items():
        if field not in verification:
            result[field] = value
        elif isinstance(value, list) and isinstance(verification[field], list):
            combined_rows = []
            for i, row in enumerate(value):
                row_ver = verification[field][i] if i < len(verification[field]) else {}
                combined_rows.append(
                    _combine_with_verification(row, row_ver) if isinstance(row, dict) else row
                )
            result[field] = combined_rows
        else:
            result[field] = {"value": value, **verification[field]}
    return result


# ---------------------------------------------------------------------------
# Schema strict-mode helper
# ---------------------------------------------------------------------------


def _make_schema_strict(schema: dict) -> dict:
    """Make a JSON schema compatible with OpenAI strict mode.

    Recursively ensures every object node has all its properties listed in
    required and additionalProperties=false — replicating what
    client.beta.chat.completions.parse() does internally but for the
    Responses API which requires an explicit raw schema.
    """
    schema = schema.copy()
    if "$ref" in schema:
        # OpenAI strict JSON schema rejects sibling keywords next to $ref
        # (for example {"$ref": "...", "description": "..."}).
        return {"$ref": schema["$ref"]}
    if schema.get("type") == "object" and "properties" in schema:
        schema["required"] = list(schema["properties"].keys())
        schema["additionalProperties"] = False
        schema["properties"] = {k: _make_schema_strict(v) for k, v in schema["properties"].items()}
    if "$defs" in schema:
        schema["$defs"] = {k: _make_schema_strict(v) for k, v in schema["$defs"].items()}
    if schema.get("type") == "array" and "items" in schema:
        schema["items"] = _make_schema_strict(schema["items"])
    return schema


_GEMINI_UNSUPPORTED_KEYS = frozenset(
    {
        "additionalProperties",
        "title",
        "default",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "pattern",
        "$schema",
        "definitions",
    }
)


def _prepare_google_schema(schema: dict) -> dict:
    """Prepare a JSON schema for Gemini's responseSchema.

    Three passes:
    1. Inline all $ref/$defs so no references remain.
    2. Normalize Pydantic anyOf nullable schemas into Gemini-compatible
       nullable schemas.
    3. Strip keywords that Gemini does not support (additionalProperties,
       title, minimum/maximum, maxLength, etc.).
    """
    inlined = _inline_schema_refs(schema)
    normalized = _normalize_gemini_schema(inlined)
    return _strip_gemini_unsupported(normalized)


def _normalize_gemini_schema(schema: dict) -> dict:
    """Normalize Pydantic JSON Schema shapes for Gemini responseSchema."""
    if "anyOf" in schema:
        branches = schema["anyOf"]
        if not isinstance(branches, list):
            raise ValueError("Gemini responseSchema only supports list-valued anyOf.")

        non_null_branches = [
            branch
            for branch in branches
            if not (isinstance(branch, dict) and branch.get("type") == "null")
        ]
        null_branch_count = len(branches) - len(non_null_branches)

        if null_branch_count == 1 and len(non_null_branches) == 1:
            branch = non_null_branches[0]
            if not isinstance(branch, dict):
                raise ValueError("Gemini responseSchema nullable anyOf branch must be an object.")
            normalized_branch = _normalize_gemini_schema(branch)
            normalized_branch["nullable"] = True

            for key, value in schema.items():
                if key == "anyOf" or key in _GEMINI_UNSUPPORTED_KEYS:
                    continue
                if key not in normalized_branch:
                    normalized_branch[key] = _normalize_schema_value(value)
            return normalized_branch

        if _is_pydantic_decimal_anyof(non_null_branches):
            normalized_branch = _normalize_gemini_schema({"type": "number"})
            if null_branch_count == 1:
                normalized_branch["nullable"] = True

            for key, value in schema.items():
                if key == "anyOf" or key in _GEMINI_UNSUPPORTED_KEYS:
                    continue
                if key not in normalized_branch:
                    normalized_branch[key] = _normalize_schema_value(value)
            return normalized_branch

        raise ValueError(
            "Gemini responseSchema does not support this anyOf union shape. "
            "Only Optional[T] / T | None schemas are supported."
        )

    result = {}
    for key, value in schema.items():
        result[key] = _normalize_schema_value(value)
    return result


def _is_pydantic_decimal_anyof(branches: list) -> bool:
    """Return True for Pydantic Decimal schemas: number OR decimal string."""
    if len(branches) != 2 or not all(isinstance(branch, dict) for branch in branches):
        return False

    types = {branch.get("type") for branch in branches}
    if types != {"number", "string"}:
        return False

    string_branch = next(branch for branch in branches if branch.get("type") == "string")
    return "pattern" in string_branch


def _normalize_schema_value(value):
    if isinstance(value, dict):
        return _normalize_gemini_schema(value)
    if isinstance(value, list):
        return [
            _normalize_gemini_schema(item) if isinstance(item, dict) else item for item in value
        ]
    return value


def _strip_gemini_unsupported(schema: dict) -> dict:
    result = {}
    for key, value in schema.items():
        if key in _GEMINI_UNSUPPORTED_KEYS:
            continue
        if key == "enum" and isinstance(value, list) and "" in value:
            # Gemini rejects empty strings in enum arrays. Drop the enum constraint
            # entirely so the model can still output '' when a field is absent.
            # apply_field_policies() will normalise any out-of-range values after
            # the call.
            continue
        if isinstance(value, dict):
            result[key] = _strip_gemini_unsupported(value)
        elif isinstance(value, list):
            result[key] = [
                _strip_gemini_unsupported(i) if isinstance(i, dict) else i for i in value
            ]
        else:
            result[key] = value
    return result


def _inline_schema_refs(schema: dict) -> dict:
    """Inline all $ref references so no $defs remain in the schema.

    Gemini's responseSchema rejects $ref / $defs — every type must be fully
    inlined. Replaces each {"$ref": "#/$defs/Name"} with the definition it
    points to, then drops the top-level $defs section.
    """
    defs = schema.get("$defs", {})

    def resolve(node: dict) -> dict:
        if "$ref" in node:
            ref = node["$ref"]
            if ref.startswith("#/$defs/"):
                name = ref[len("#/$defs/") :]
                if name in defs:
                    return resolve(dict(defs[name]))
            return node
        result = {}
        for key, value in node.items():
            if key == "$defs":
                continue
            elif isinstance(value, dict):
                result[key] = resolve(value)
            elif isinstance(value, list):
                result[key] = [resolve(i) if isinstance(i, dict) else i for i in value]
            else:
                result[key] = value
        return result

    return resolve(schema)


# ---------------------------------------------------------------------------
# Schema persistence helpers  (same pattern as extraction_example_4.py)
# ---------------------------------------------------------------------------


def _save_schema_to_python(model: type[BaseModel], path: Path) -> None:
    """Generate and save a Pydantic model as a standalone Python module.

    Generates Python source directly from model_fields using repr() for every
    string value, so quotes, umlauts, and other special characters in field
    descriptions and Literal values are always escaped correctly.
    """

    def ann_repr(ann) -> str:
        origin = get_origin(ann)
        if origin is list:
            args = get_args(ann)
            return f"list[{ann_repr(args[0])}]" if args else "list"
        if origin is Literal:
            args = get_args(ann)
            return f"Literal[{', '.join(repr(a) for a in args)}]"
        if origin is Union:
            args = get_args(ann)
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1 and type(None) in args:
                return f"Optional[{ann_repr(non_none[0])}]"
            return f"Union[{', '.join(ann_repr(a) for a in args)}]"
        try:
            import types as _t

            if isinstance(ann, _t.UnionType):
                args = get_args(ann)
                non_none = [a for a in args if a is not type(None)]
                if len(non_none) == 1 and type(None) in args:
                    return f"Optional[{ann_repr(non_none[0])}]"
                return f"Union[{', '.join(ann_repr(a) for a in args)}]"
        except AttributeError:
            pass
        if ann is type(None):
            return "None"
        if hasattr(ann, "__name__"):
            return ann.__name__
        return repr(ann)

    # Collect models in dependency order (nested item models before their container)
    seen: set = set()
    ordered: list[type[BaseModel]] = []

    def collect(m: type[BaseModel]) -> None:
        if m in seen:
            return
        seen.add(m)
        for finfo in m.model_fields.values():
            if get_origin(finfo.annotation) is list:
                args = get_args(finfo.annotation)
                if args and isinstance(args[0], type) and issubclass(args[0], BaseModel):
                    collect(args[0])
        ordered.append(m)

    collect(model)

    class_blocks: list[str] = []
    for m in ordered:
        lines: list[str] = [f"class {m.__name__}(BaseModel):"]
        doc = (m.__doc__ or "").strip()
        if doc:
            lines.append(f'    """{doc}"""')
        lines.append("    model_config = ConfigDict(extra='forbid')")
        lines.append("")
        for fname, finfo in m.model_fields.items():
            field_args: list[str] = []
            if finfo.description:
                field_args.append(f"description={repr(finfo.description)}")
            if finfo.default_factory is not None:
                factory = finfo.default_factory
                factory_name = getattr(factory, "__name__", None)
                if factory_name in {"list", "dict", "set"}:
                    field_args.append(f"default_factory={factory_name}")
                else:
                    field_args.append(f"default={repr(factory())}")
            elif not finfo.is_required():
                field_args.append(f"default={repr(finfo.default)}")
            if field_args:
                lines.append(
                    f"    {fname}: {ann_repr(finfo.annotation)} = Field({', '.join(field_args)})"
                )
            else:
                lines.append(f"    {fname}: {ann_repr(finfo.annotation)}")
        class_blocks.append("\n".join(lines))

    header = (
        '"""Auto-generated schema — do not edit manually."""\n\n'
        "import decimal\n"
        "from decimal import Decimal\n"
        "from typing import List, Literal, Optional, Union\n\n"
        "from pydantic import BaseModel, ConfigDict, Field\n\n"
    )
    path.write_text(header + "\n\n".join(class_blocks) + "\n", encoding="utf-8")


def _save_requirements(requirements: RequirementsSpec, model_name: str, path: Path) -> None:
    if isinstance(requirements, CompositeExtractionRequirements):
        payload = {
            "model_name": model_name,
            "requirements_type": "parent_with_nested_list",
            "requirements": requirements.model_dump(),
        }
    else:
        payload = {
            "model_name": model_name,
            "requirements_type": "extraction",
            "requirements": requirements.model_dump(),
        }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_saved_schema(path: Path, model_name: str) -> type[BaseModel]:
    spec = importlib.util.spec_from_file_location("_vision_saved_schema", path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return getattr(module, model_name)


def _load_saved_requirements(path: Path) -> tuple[str, RequirementsSpec]:
    data = json.loads(path.read_text(encoding="utf-8"))
    requirements_type = data.get("requirements_type", "extraction")
    if requirements_type == "parent_with_nested_list":
        raw = data["requirements"]
        # Migrate old single-child format (child_container_name / child_requirements)
        # to the new children list format.
        if "child_container_name" in raw and "children" not in raw:

            raw = {
                "parent_requirements": raw["parent_requirements"],
                "children": [
                    {
                        "container_name": raw["child_container_name"],
                        "container_description": "",
                        "requirements": raw["child_requirements"],
                    }
                ],
            }
        requirements = CompositeExtractionRequirements(**raw)
    else:
        requirements = ExtractionRequirements(**data["requirements"])
    return data["model_name"], requirements


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class VisionExtractionResult:
    """Result from :meth:`VisionExtractor.extract`."""

    data: dict
    verification: dict | None
    usage: UsageRecord | None
    duration_s: float
    model: str
    documents_processed: int


@dataclass
class RequirementsSuggestionResult:
    """Result from :meth:`VisionExtractor.suggest_requirements_with_usage`.

    Attributes:
        requirements_text: Natural-language description of which fields are
            worth extracting from this kind of document. Suitable as the
            ``user_requirements`` argument to :meth:`VisionExtractor.extract`
            or as input to :class:`~gaik.software_components.extractor.SchemaGenerator`.
        usage: Token usage for the single vision call, or ``None`` when the
            provider returned no usage payload.
        duration_s: Wall-clock seconds the vision call took.
        model: Resolved model identifier the call used.
        documents_processed: Number of input files sent in the call.
    """

    requirements_text: str
    usage: UsageRecord | None
    duration_s: float
    model: str
    documents_processed: int


# ---------------------------------------------------------------------------
# Requirements-suggestion meta-model + prompt
# ---------------------------------------------------------------------------


class _RequirementsSuggestion(BaseModel):
    """Internal meta-model for :meth:`VisionExtractor.suggest_requirements`.

    Runs the normal vision pipeline but, instead of extracting data, asks the
    model to *describe* the fields worth extracting as a single natural-language
    string. That string then feeds schema generation (or :meth:`extract`).
    """

    requirements_text: str = Field(
        description=(
            "A concise natural-language description of which fields to extract from "
            "this kind of document, suitable as input to a schema generator. List the "
            "top-level fields, and if the document has a repeating table, describe the "
            "per-line-item fields too. Format like a short spec, e.g. 'Top-level "
            "fields: ... For each line item: ...'."
        )
    )


_SUGGEST_REQUIREMENTS_PROMPT = (
    "You are helping a user set up a reusable document-extraction template. "
    "Look at the attached document(s) and propose which fields are worth extracting. "
    "Return a single natural-language description (requirements_text) suitable as input "
    "to a schema generator: list the top-level fields, and if there is a repeating "
    "table, describe the per-line-item fields too."
)


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------


class VisionExtractor:
    """Single-pass PDF/image → structured data via vision LLM.

    Supported input formats: .pdf, .png, .jpg, .jpeg, .gif, .webp, .tiff, .bmp

    All files are sent in one API call so the model sees the full context
    across related documents (e.g. a Purchase Order + multiple BOMs).

    Usage::

        extractor = VisionExtractor(model_provider="openai", use_azure=True)
        result = extractor.extract(
            file_paths=["PO.pdf", "BOM1.pdf", "BOM2.pdf"],
            user_requirements="Extract ...",
        )
        print(result.data)
    """

    def __init__(
        self,
        *,
        api_config: dict | None = None,
        model_provider: ModelProvider = "openai",
        model: str | None = None,
        reasoning_effort: ReasoningEffort = "medium",
        merge_table: bool = False,
        use_azure: bool = True,
        vertex_ai: bool = True,
        additional_instructions: str | None = None,
        include_verification: bool = False,
    ) -> None:
        self.model_provider = model_provider
        self.reasoning_effort = reasoning_effort
        self.merge_table = merge_table
        self.use_azure = use_azure
        self.additional_instructions = additional_instructions
        self.include_verification = include_verification

        if api_config:
            self.config = api_config
        elif model_provider == "openai":
            self.config = get_openai_config(use_azure=use_azure)
        elif model_provider == "claude":
            from gaik.software_components.parsers.multimodal_parser.config import (
                get_claude_config,
            )

            self.config = get_claude_config(use_azure=use_azure)
        elif model_provider == "google":
            from gaik.software_components.parsers.multimodal_parser.config import (
                get_google_config,
            )

            self.config = get_google_config(vertex_ai=vertex_ai)
        else:
            raise ValueError(f"Unknown model_provider '{model_provider}'")

        self.model = model if model else self.config["model"]

    # -- public API -----------------------------------------------------------

    def extract(
        self,
        *,
        file_paths: list[str | Path],
        user_requirements: str,
        extraction_model: type[BaseModel] | None = None,
        requirements: RequirementsSpec | None = None,
        schema_dir: str | Path | None = None,
    ) -> VisionExtractionResult:
        """Extract structured data from one or more PDFs/images in a single LLM call.

        Args:
            file_paths: PDF or image paths. All are sent in one call.
            user_requirements: Natural language description of what to extract.
            extraction_model: Pre-built Pydantic model (skips schema generation).
            requirements: Pre-built ExtractionRequirements (skips schema generation).
            schema_dir: Directory for schema persistence.
                        Loads schema.py + requirements.json if present; saves them
                        after generation if not.

        Schema resolution order:
            1. Both extraction_model and requirements passed → use directly.
            2. schema_dir set and files exist → load from disk.
            3. Otherwise → generate via SchemaGenerator (text LLM call).
        """
        if extraction_model is None or requirements is None:
            extraction_model, requirements = self._resolve_schema(user_requirements, schema_dir)

        llm_model = (
            _wrap_model_for_verification(extraction_model)
            if self.include_verification
            else extraction_model
        )

        file_path_list = [Path(p) for p in file_paths]
        t0 = time.perf_counter()
        result_dict, usage = self._extract(file_path_list, llm_model, user_requirements)
        duration_s = round(time.perf_counter() - t0, 3)

        result_dict = self._normalize_numeric_placeholders(result_dict, requirements)
        if self.include_verification:
            result_dict = self._validate_result(result_dict, llm_model)

        verification = None
        if self.include_verification:
            result_dict, verification = _unwrap_verification(result_dict)

        result_dict = self._post_process(result_dict, requirements)

        result_dict = self._validate_result(result_dict, extraction_model)

        if self.include_verification and verification:
            result_dict = _combine_with_verification(result_dict, verification)

        return VisionExtractionResult(
            data=result_dict,
            verification=verification,
            usage=usage,
            duration_s=duration_s,
            model=self.model,
            documents_processed=len(file_path_list),
        )

    # -- public API: requirements suggestion ----------------------------------

    def suggest_requirements(
        self,
        *,
        file_paths: list[str | Path],
        instructions: str = "",
    ) -> str:
        """Suggest extraction requirements from one or more sample documents.

        Runs a single vision pass over ``file_paths`` and, instead of extracting
        data, returns a natural-language description of which fields are worth
        extracting from this kind of document. The returned text is suitable as
        the ``user_requirements`` argument to :meth:`extract`, or as input to
        :class:`~gaik.software_components.extractor.SchemaGenerator`.

        This reuses the same provider/model configuration the extractor was
        constructed with, so it is provider-agnostic (openai/claude/google).
        ``include_verification`` is ignored for this call.

        Args:
            file_paths: PDF or image paths. All are sent in one call so the
                model can describe fields spanning related documents.
            instructions: Optional extra guidance appended to the prompt, e.g.
                "Focus on financial fields" or "Suggest fields in Finnish".

        Returns:
            The suggested requirements as a single natural-language string.
            Empty string if the model returned no text.

        Usage::

            extractor = VisionExtractor(model_provider="openai", use_azure=True)
            requirements = extractor.suggest_requirements(file_paths=["invoice.pdf"])
            result = extractor.extract(
                file_paths=["invoice.pdf"], user_requirements=requirements
            )
        """
        return self.suggest_requirements_with_usage(
            file_paths=file_paths, instructions=instructions
        ).requirements_text

    def suggest_requirements_with_usage(
        self,
        *,
        file_paths: list[str | Path],
        instructions: str = "",
    ) -> RequirementsSuggestionResult:
        """Suggest extraction requirements and report token usage + latency.

        Same input and behaviour as :meth:`suggest_requirements`; returns a
        :class:`RequirementsSuggestionResult` carrying the suggested text plus
        usage, duration, resolved model, and document count for the single
        vision call.
        """
        prompt = _SUGGEST_REQUIREMENTS_PROMPT
        if instructions.strip():
            prompt += f"\n\nAdditional user guidance to follow: {instructions.strip()}"

        file_path_list = [Path(p) for p in file_paths]
        t0 = time.perf_counter()
        result_dict, usage = self._extract(file_path_list, _RequirementsSuggestion, prompt)
        duration_s = round(time.perf_counter() - t0, 3)

        validated = _RequirementsSuggestion.model_validate(result_dict)
        return RequirementsSuggestionResult(
            requirements_text=validated.requirements_text,
            usage=usage,
            duration_s=duration_s,
            model=self.model,
            documents_processed=len(file_path_list),
        )

    # -- internal: dispatch ---------------------------------------------------

    @staticmethod
    def _validate_result(result_dict: dict, model: type[BaseModel]) -> dict:
        """Validate provider output against the expected Pydantic model."""
        return model.model_validate(result_dict).model_dump()

    @staticmethod
    def _normalize_numeric_placeholders(result_dict: dict, requirements: RequirementsSpec) -> dict:
        """Convert blank numeric placeholders to None before Pydantic validation."""

        def coerce_fields(data: dict, req: ExtractionRequirements) -> None:
            for field in req.fields:
                if field.field_type not in NUMERIC_FIELD_TYPES or field.field_name not in data:
                    continue

                value = data[field.field_name]
                if isinstance(value, dict) and "value" in value:
                    if isinstance(value["value"], str) and not value["value"].strip():
                        value["value"] = None
                elif isinstance(value, str) and not value.strip():
                    data[field.field_name] = None

        if isinstance(requirements, CompositeExtractionRequirements):
            coerce_fields(result_dict, requirements.parent_requirements)
            child_rows = result_dict.get(requirements.child_container_name)
            if isinstance(child_rows, list):
                for row in child_rows:
                    if isinstance(row, dict):
                        coerce_fields(row, requirements.child_requirements)
            return result_dict

        coerce_fields(result_dict, requirements)
        for value in result_dict.values():
            if isinstance(value, list):
                for row in value:
                    if isinstance(row, dict):
                        coerce_fields(row, requirements)
        return result_dict

    def _extract(
        self,
        file_paths: list[Path],
        extraction_model: type[BaseModel],
        user_requirements: str,
    ) -> tuple[dict, UsageRecord | None]:
        system_prompt = self._get_system_prompt()
        user_prompt = self._get_user_prompt(user_requirements)

        if self.model_provider == "openai":
            return self._call_openai(file_paths, system_prompt, user_prompt, extraction_model)
        elif self.model_provider == "claude":
            return self._call_claude(file_paths, system_prompt, user_prompt, extraction_model)
        elif self.model_provider == "google":
            return self._call_google(file_paths, system_prompt, user_prompt, extraction_model)
        raise ValueError(f"Unknown model_provider '{self.model_provider}'")

    # -- internal: provider calls ---------------------------------------------

    def _call_openai(
        self,
        file_paths: list[Path],
        system_prompt: str,
        user_prompt: str,
        extraction_model: type[BaseModel],
    ) -> tuple[dict, UsageRecord | None]:
        client = create_openai_client(self.config)

        content: list[dict] = []
        for fp in file_paths:
            mime = _detect_mime_type(fp)
            b64 = _encode_pdf_base64(fp)
            data_url = f"data:{mime};base64,{b64}"
            if _is_pdf(fp):
                content.append({"type": "input_file", "filename": fp.name, "file_data": data_url})
            else:
                content.append({"type": "input_image", "image_url": data_url})
        content.append({"type": "input_text", "text": user_prompt})

        t0 = time.perf_counter()
        response = client.responses.create(
            model=self.model,
            instructions=system_prompt,
            input=[{"role": "user", "content": content}],
            reasoning={"effort": self.reasoning_effort},
            text={
                "format": {
                    "type": "json_schema",
                    "name": extraction_model.__name__[:64],
                    "schema": _make_schema_strict(extraction_model.model_json_schema()),
                    "strict": True,
                }
            },
            max_output_tokens=32768,
        )
        elapsed = time.perf_counter() - t0

        result_dict = json.loads(response.output_text)
        usage_dict = _extract_openai_usage(response)
        usage = (
            build_usage_record("openai", self.model, usage_dict, elapsed)
            if usage_dict["total_tokens"] > 0
            else None
        )
        return result_dict, usage

    def _call_claude(
        self,
        file_paths: list[Path],
        system_prompt: str,
        user_prompt: str,
        extraction_model: type[BaseModel],
    ) -> tuple[dict, UsageRecord | None]:
        client = create_claude_client(self.config)

        content: list[dict] = []
        for fp in file_paths:
            mime = _detect_mime_type(fp)
            b64 = _encode_pdf_base64(fp)
            if _is_pdf(fp):
                content.append(
                    {
                        "type": "document",
                        "title": fp.name,
                        "source": {"type": "base64", "media_type": mime, "data": b64},
                    }
                )
            else:
                content.append(
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": mime, "data": b64},
                    }
                )
        content.append({"type": "text", "text": user_prompt})

        tool_schema = {
            "name": "extract_data",
            "description": "Extract structured data from the documents",
            "input_schema": extraction_model.model_json_schema(),
        }

        t0 = time.perf_counter()
        with client.messages.stream(
            model=self.model,
            max_tokens=32768,
            system=system_prompt,
            thinking={"type": "adaptive"},
            output_config={"effort": self.reasoning_effort},
            tools=[tool_schema],
            tool_choice={"type": "auto"},
            messages=[{"role": "user", "content": content}],
        ) as stream:
            response = stream.get_final_message()
        elapsed = time.perf_counter() - t0

        result_dict: dict = {}
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "extract_data":
                result_dict = block.input
                break
        if not result_dict:
            raise ValueError(
                f"Claude did not call the extract_data tool. Response: {response.content}"
            )

        usage_dict = _extract_claude_usage(response)
        usage = (
            build_usage_record("claude", self.model, usage_dict, elapsed)
            if usage_dict["total_tokens"] > 0
            else None
        )
        return result_dict, usage

    def _call_google(
        self,
        file_paths: list[Path],
        system_prompt: str,
        user_prompt: str,
        extraction_model: type[BaseModel],
    ) -> tuple[dict, UsageRecord | None]:
        parts: list[dict] = []
        for fp in file_paths:
            mime = _detect_mime_type(fp)
            parts.append({"inlineData": {"mimeType": mime, "data": _encode_pdf_base64(fp)}})
        parts.append({"text": user_prompt})

        is_vertex = self.config.get("vertex_ai", True)
        # Vertex AI REST API requires uppercase enum values (LOW/MEDIUM/HIGH);
        # Gemini direct API uses lowercase. Both are case-insensitive per spec,
        # but uppercase is the canonical form for Vertex AI Protobuf-backed enums.
        thinking_level = self.reasoning_effort.upper() if is_vertex else self.reasoning_effort

        body = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "USER", "parts": parts}],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": 32768,
                "thinkingConfig": {"thinkingLevel": thinking_level},
                "responseMimeType": "application/json",
                "responseSchema": _prepare_google_schema(extraction_model.model_json_schema()),
            },
        }

        if is_vertex:
            token = get_google_access_token(self.config)
            url = self.config["generate_content_url"]
            if "{model}" in url:
                url = url.replace("{model}", self.model)
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            }
        else:
            api_key = self.config["api_key"]
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/"
                f"models/{self.model}:generateContent?key={api_key}"
            )
            headers = {"Content-Type": "application/json; charset=utf-8"}

        t0 = time.perf_counter()
        resp = requests.post(url, headers=headers, json=body, timeout=(30, 300))
        resp.raise_for_status()
        elapsed = time.perf_counter() - t0

        payload = resp.json()
        candidates = payload.get("candidates", [])
        if not candidates:
            raise ValueError(f"Gemini response had no candidates: {payload}")

        candidate_parts = candidates[0].get("content", {}).get("parts", [])
        # Exclude thought blocks (present when includeThoughts=True) — they are
        # not JSON and must not be passed to json.loads.
        text_parts = [
            p.get("text", "") for p in candidate_parts if p.get("text") and not p.get("thought")
        ]
        if not text_parts:
            raise ValueError(f"Gemini response had no text parts: {payload}")

        result_dict = json.loads(text_parts[0])
        usage_dict = _extract_google_usage(payload)
        usage = (
            build_usage_record("google", self.model, usage_dict, elapsed)
            if usage_dict["total_tokens"] > 0
            else None
        )
        return result_dict, usage

    # -- internal: post-processing --------------------------------------------

    def _post_process(self, result_dict: dict, requirements: RequirementsSpec) -> dict:
        if isinstance(requirements, CompositeExtractionRequirements):
            child_keys = {c.container_name for c in requirements.children}
            parent_data = {k: v for k, v in result_dict.items() if k not in child_keys}
            parent_data = apply_field_policies(parent_data, requirements.parent_requirements)
            parent_data = normalize_extracted_data(parent_data, requirements.parent_requirements)

            for child in requirements.children:
                child_rows = result_dict.get(child.container_name, [])
                if isinstance(child_rows, list):
                    parent_data[child.container_name] = [
                        normalize_extracted_data(
                            apply_field_policies(row, child.requirements),
                            child.requirements,
                        )
                        if isinstance(row, dict)
                        else row
                        for row in child_rows
                    ]
                else:
                    parent_data[child.container_name] = child_rows

            return parent_data

        has_nested = False
        for key, value in list(result_dict.items()):
            if isinstance(value, list) and value and isinstance(value[0], dict):
                has_nested = True
                result_dict[key] = [apply_field_policies(item, requirements) for item in value]
        if not has_nested:
            result_dict = apply_field_policies(result_dict, requirements)

        for key, value in list(result_dict.items()):
            if isinstance(value, list) and value and isinstance(value[0], dict):
                result_dict[key] = [normalize_extracted_data(item, requirements) for item in value]
        result_dict = normalize_extracted_data(result_dict, requirements)
        return result_dict

    # -- internal: schema resolution ------------------------------------------

    def _resolve_schema(
        self,
        user_requirements: str,
        schema_dir: str | Path | None,
    ) -> tuple[type[BaseModel], RequirementsSpec]:
        if schema_dir is not None:
            schema_dir = Path(schema_dir)
            schema_path = schema_dir / "schema.py"
            req_path = schema_dir / "requirements.json"
            if schema_path.exists() and req_path.exists():
                print(f"Loading saved schema from {schema_dir}")
                model_name, requirements = _load_saved_requirements(req_path)
                extraction_model = _load_saved_schema(schema_path, model_name)
                return extraction_model, requirements

        schema_config = get_openai_config(use_azure=self.use_azure)
        gen = SchemaGenerator(config=schema_config)
        extraction_model = gen.generate_schema(user_requirements)
        requirements = gen.item_requirements

        if schema_dir is not None:
            schema_dir = Path(schema_dir)
            schema_dir.mkdir(parents=True, exist_ok=True)
            _save_schema_to_python(extraction_model, schema_dir / "schema.py")
            _save_requirements(
                requirements, extraction_model.__name__, schema_dir / "requirements.json"
            )
            print(f"Schema saved to {schema_dir}")

        return extraction_model, requirements

    # -- internal: prompt helpers ---------------------------------------------

    def _get_system_prompt(self) -> str:
        prompt = SYSTEM_PROMPTS[self.model_provider]
        if self.include_verification:
            prompt += "\n" + VERIFICATION_PROMPT
        return prompt

    def _get_user_prompt(self, user_requirements: str) -> str:
        prompt = USER_PROMPTS[self.model_provider].format(user_requirements=user_requirements)
        if self.merge_table:
            prompt = prompt.rstrip() + "\nIf a table is split across multiple pages, combine it.\n"
        if self.additional_instructions:
            prompt = prompt.rstrip() + "\n" + self.additional_instructions + "\n"
        return prompt
