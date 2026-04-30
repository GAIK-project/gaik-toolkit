"""LLM-as-Judge Validator (v2, 2026-research-backed)

Multi-provider LLM-as-judge validator for structured-extraction outputs.
Feeds page images plus an extractor's JSON to a vision-capable LLM (OpenAI,
Azure OpenAI, Anthropic, or Google Gemini) and asks it to flag fields whose
value does not match the document.

v2 additions over the original validator:
    - Integer Likert 1-5 scoring (``ValidationFlag.score``); ~30 % better
      human-correlation than continuous scales (HuggingFace cookbook).
    - Few-shot examples in :class:`ValidationRubric` for domain calibration.
    - Per-aspect evaluation focus (``ValidationRubric.evaluation_aspects``).
    - Explicit bias-mitigation guidance in the system prompt
      (anti-verbosity, anti-formatting-bias).
    - :class:`LLMJudgePanel` for multi-judge majority-vote aggregation.
    - :func:`calibrate_against_human_labels` to verify Pearson correlation
      with a human-labeled dataset (~0.84 is the HF cookbook reference).
    - :func:`compare_pairwise` with swap-and-average position-bias mitigation.

Main classes:
    - :class:`LLMJudge`: single-judge validation
    - :class:`LLMJudgePanel`: multi-judge majority-vote validation

Result types:
    - :class:`ValidationFlag`: per-field observation (severity + Likert score)
    - :class:`ValidationRubric`: per-call instructions, few-shot, aspects
    - :class:`ValidationResult`: flags + raw judge text + usage
    - :class:`JudgeUsage`: per-call token / cost record
    - :class:`JudgePanelResult`: aggregated flags + agreement score
    - :class:`CalibrationItem`, :class:`CalibrationReport`: calibration utility
    - :class:`PairwiseResult`: A-vs-B comparison output
    - :class:`FewShotExample`: reference example for rubric

Example:
    >>> from gaik.software_components.validators.llm_judge import (
    ...     LLMJudge, ValidationRubric,
    ... )
    >>> judge = LLMJudge(model_provider="google", model="gemini-3-flash-preview")
    >>> result = judge.validate(
    ...     source_pages=[png_bytes_page1],
    ...     extracted=[{"item_index": 0, "quantity": "10"}],
    ...     rubric=ValidationRubric(
    ...         vendor_id="acme-supply",
    ...         scoring_mode="likert_1_5",
    ...         field_checks=["Quantity is the line-amount column, not the unit-price column"],
    ...     ),
    ... )
    >>> for flag in result.flags:
    ...     print(flag.field, flag.severity, flag.score, flag.reason)
"""

from .calibration import calibrate_against_human_labels
from .llm_judge import (
    DEFAULT_MODELS,
    LLMJudge,
    parse_judge_flags,
    parse_text_judgement,
)
from .pairwise import compare_pairwise
from .panel import LLMJudgePanel
from .pricing import JUDGE_PRICING_PER_M, compute_judge_cost_usd, lookup_judge_price
from .prompts import (
    JUDGE_SYSTEM_PROMPT,
    TEXT_PAIR_SYSTEM_PROMPT,
    build_system_prompt,
    build_text_pair_prompt,
    build_user_prompt,
)
from .schema import (
    CalibrationItem,
    CalibrationReport,
    FewShotExample,
    JudgePanelResult,
    JudgeUsage,
    PairwiseResult,
    ScoringMode,
    Severity,
    TextJudgement,
    ValidationFlag,
    ValidationResult,
    ValidationRubric,
)

__all__ = [
    # Judge classes
    "LLMJudge",
    "LLMJudgePanel",
    # Schema / data shapes
    "ValidationFlag",
    "ValidationRubric",
    "ValidationResult",
    "FewShotExample",
    "JudgePanelResult",
    "JudgeUsage",
    "CalibrationItem",
    "CalibrationReport",
    "PairwiseResult",
    "TextJudgement",
    "Severity",
    "ScoringMode",
    # Utilities
    "calibrate_against_human_labels",
    "compare_pairwise",
    "parse_judge_flags",
    "parse_text_judgement",
    # Pricing
    "DEFAULT_MODELS",
    "JUDGE_PRICING_PER_M",
    "compute_judge_cost_usd",
    "lookup_judge_price",
    # Prompt building blocks (advanced users)
    "JUDGE_SYSTEM_PROMPT",
    "TEXT_PAIR_SYSTEM_PROMPT",
    "build_system_prompt",
    "build_text_pair_prompt",
    "build_user_prompt",
]

__version__ = "0.3.1"
"""Sub-package marker (not the published toolkit version — that comes
from setuptools-scm git tags). 0.3.1 = patch over 0.3.0: research-utility
benchmark code moved out of the public API to
``examples/software_components/validators/demo_judgebench_comparison.py``.
The production-facing surface (LLMJudge, panel, calibration, pairwise)
is unchanged."""
