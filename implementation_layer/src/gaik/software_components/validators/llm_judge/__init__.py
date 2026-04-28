"""LLM-as-Judge Validator

Multi-provider LLM-as-judge validator for structured-extraction outputs.
Feeds page images plus an extractor's JSON to a vision-capable LLM (OpenAI,
Azure OpenAI, Anthropic, or Google Gemini) and asks it to flag fields whose
value does not match the document.

Main Classes:
    - LLMJudge: validate page images + extractor output against ground-truth document

Result types:
    - ValidationFlag: one per field observation
    - ValidationRubric: optional vendor-specific check sentences
    - ValidationResult: flags + raw judge text + token / cost usage
    - JudgeUsage: per-call usage record (mirrors UsageRecord shape)

Example:
    >>> from gaik.software_components.validators.llm_judge import (
    ...     LLMJudge, ValidationRubric,
    ... )
    >>> judge = LLMJudge(model_provider="google", model="gemini-3-flash-preview")
    >>> result = judge.validate(
    ...     source_pages=[png_bytes_page1],
    ...     extracted=[{"item_index": 0, "quantity": "940"}],
    ...     rubric=ValidationRubric(
    ...         vendor_id="copper-brass",
    ...         field_checks=["Quantity is integer pounds before decimal"],
    ...     ),
    ... )
    >>> for flag in result.flags:
    ...     print(flag.field, flag.severity, flag.reason)
"""

from .llm_judge import DEFAULT_MODELS, LLMJudge, parse_judge_flags
from .pricing import JUDGE_PRICING_PER_M, compute_judge_cost_usd, lookup_judge_price
from .prompts import JUDGE_SYSTEM_PROMPT, build_user_prompt
from .schema import (
    JudgeUsage,
    ValidationFlag,
    ValidationResult,
    ValidationRubric,
)

__all__ = [
    "LLMJudge",
    "ValidationFlag",
    "ValidationRubric",
    "ValidationResult",
    "JudgeUsage",
    "DEFAULT_MODELS",
    "JUDGE_PRICING_PER_M",
    "JUDGE_SYSTEM_PROMPT",
    "build_user_prompt",
    "compute_judge_cost_usd",
    "lookup_judge_price",
    "parse_judge_flags",
]

__version__ = "0.1.0"
