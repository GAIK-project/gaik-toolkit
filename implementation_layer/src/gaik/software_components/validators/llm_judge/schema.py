"""Dataclasses for LLM-as-judge validator results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Severity = Literal["ok", "suspect", "wrong"]


@dataclass
class ValidationFlag:
    """A single judge observation about an extracted field.

    `item_index = -1` is reserved for document-level observations such as
    "the extractor returned 2 items but the PDF has 14".
    """

    item_index: int
    field: str
    severity: Severity
    confidence: float = 0.0
    reason: str = ""
    suggested_value: str | None = None


@dataclass
class ValidationRubric:
    """Per-call instructions appended to the judge's user prompt.

    Consumers (e.g. an OC builder pipeline) hand in vendor-specific check
    sentences. The toolkit stays vendor-agnostic.
    """

    vendor_id: str | None = None
    field_checks: list[str] = field(default_factory=list)
    item_level_checks: list[str] = field(default_factory=list)
    custom_system_suffix: str | None = None


@dataclass
class JudgeUsage:
    """Token-usage + cost record for a single judge call.

    Mirrors the shape of `gaik.software_components.parsers.multimodal_parser.usage.UsageRecord`
    but is defined locally to avoid a hard dep on the parser package.
    """

    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    duration_s: float = 0.0
    cost_usd: float = 0.0


@dataclass
class ValidationResult:
    """Aggregate result from one `LLMJudge.validate(...)` call."""

    flags: list[ValidationFlag]
    raw_judge_text: str
    usage: JudgeUsage
