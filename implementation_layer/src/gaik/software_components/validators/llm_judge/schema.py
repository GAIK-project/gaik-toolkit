"""Dataclasses for LLM-as-judge validator results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Severity = Literal["ok", "suspect", "wrong"]

ScoringMode = Literal["severity", "likert_1_5", "additive"]
"""Scoring mode for the judge.

- ``"severity"`` (default): three-class severity only (ok / suspect / wrong).
  Backward-compatible mode; ``ValidationFlag.score`` will stay 0.
- ``"likert_1_5"``: integer Likert 1-5 alongside severity. HuggingFace
  cookbook reports ~30 % better human-correlation than continuous
  scales — recommended for new evaluations.
- ``"additive"``: same 1-5 surface, but each point is awarded for one
  atomic criterion satisfied (see ``ValidationRubric.evaluation_aspects``).
"""


@dataclass
class ValidationFlag:
    """A single judge observation about an extracted field.

    ``item_index = -1`` is reserved for document-level observations such as
    "the extractor returned 2 items but the PDF has 14".
    """

    item_index: int
    field: str
    severity: Severity
    score: int = 0
    reason: str = ""
    suggested_value: str | None = None


@dataclass
class FewShotExample:
    """A reference example to calibrate the judge.

    HuggingFace cookbook recommends 1-2 examples; more than that gives
    diminishing returns and inflates token cost.

    Attributes:
        extracted: An extractor's structured output (mirrors what the judge
            will receive at validate-time).
        expected_flags: The flags a well-calibrated judge should produce.
        description: Optional human-readable label for the example.
    """

    extracted: list[dict] | dict
    expected_flags: list[ValidationFlag]
    description: str = ""


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
    few_shot_examples: list[FewShotExample] = field(default_factory=list)
    scoring_mode: ScoringMode = "severity"
    evaluation_aspects: list[str] = field(default_factory=list)


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
    """Aggregate result from one ``LLMJudge.validate(...)`` call."""

    flags: list[ValidationFlag]
    raw_judge_text: str
    usage: JudgeUsage


@dataclass
class JudgePanelResult:
    """Aggregate result from one ``LLMJudgePanel.validate(...)`` call.

    Attributes:
        per_judge: Each judge's individual result.
        aggregated_flags: Majority-vote severity per ``(item_index, field)``,
            median Likert score across judges. See
            :func:`gaik.software_components.validators.llm_judge.panel._aggregate_flags`.
        agreement_score: Fraction of ``(item_index, field)`` keys where ALL
            judges produced the same severity. ``1.0`` = full agreement,
            ``0.0`` = total disagreement.
        total_cost_usd: Sum of per-judge call costs.
        total_duration_s: Sum of per-judge wall times (sequential execution).
    """

    per_judge: list[ValidationResult]
    aggregated_flags: list[ValidationFlag]
    agreement_score: float
    total_cost_usd: float
    total_duration_s: float


@dataclass
class CalibrationItem:
    """One human-labeled example for judge calibration.

    Used by ``calibrate_against_human_labels`` in
    :mod:`gaik.software_components.validators.llm_judge.calibration`.

    Attributes:
        source_pages: Page-image PNGs (same shape the judge will see).
        extracted: Extractor output to validate.
        human_score: Reference 1-5 Likert score from a human rater.
        human_severity: Optional reference severity for the worst issue
            (``"ok"``, ``"suspect"``, or ``"wrong"``).
        note: Free-form note about why the human rated this way.
    """

    source_pages: list[bytes]
    extracted: list[dict] | dict
    human_score: int
    human_severity: Severity | None = None
    note: str = ""


@dataclass
class CalibrationReport:
    """Calibration metrics from running a judge over a labeled dataset.

    HuggingFace cookbook reports ~0.84 Pearson correlation between a
    well-tuned Likert judge and human raters. ``__str__`` flags whether
    the current judge meets that bar.
    """

    n_items: int
    pearson_r: float | None
    severity_agreement_rate: float
    mean_judge_score: float
    mean_human_score: float
    per_item: list[dict]

    def __str__(self) -> str:  # pragma: no cover - human-readable summary
        ref = 0.84
        if self.pearson_r is None:
            pr = "N/A"
            verdict = ""
        else:
            pr = f"{self.pearson_r:.3f}"
            verdict = (
                " ✓ at HF reference"
                if self.pearson_r >= ref
                else f" (HF reference {ref:.2f})"
            )
        return (
            f"CalibrationReport(n={self.n_items}, "
            f"pearson_r={pr}{verdict}, "
            f"severity_agreement={self.severity_agreement_rate:.1%}, "
            f"mean_judge={self.mean_judge_score:.2f}, "
            f"mean_human={self.mean_human_score:.2f})"
        )


@dataclass
class HallucinationFlag:
    """One field whose extracted value is not supported by the source.

    Attributes:
        field: The exact JSON key of the offending field.
        value: The (string-rendered) value the extractor returned.
        severity: ``"wrong"`` for clear hallucinations, ``"suspect"`` when
            the model is unsure but the value seems unsupported. ``"ok"``
            never appears here — the report only carries flagged fields.
        reason: Short (≤25 word) explanation citing what the source does
            or doesn't say.
    """

    field: str
    value: str
    severity: Severity
    reason: str = ""


@dataclass
class HallucinationReport:
    """Aggregate result from one ``LLMJudge.detect_hallucinations(...)`` call.

    Use case: schema-agnostic post-extraction scrub. Given a source document
    (transcript / parsed text) and an extractor's structured output, the
    judge identifies fields whose values were not stated in the source and
    likely came from training-data context or eager-completion bias.

    Empty fields are never flagged. The report only contains entries the
    caller may want to clear / re-prompt.

    Attributes:
        flags: One :class:`HallucinationFlag` per problem field. Empty when
            the extractor's output is grounded.
        raw_judge_text: The judge's untouched response (useful for
            debugging or re-parsing with relaxed rules).
        usage: Token + cost record for the call.
    """

    flags: list[HallucinationFlag]
    raw_judge_text: str
    usage: JudgeUsage


@dataclass
class TextJudgement:
    """Result of a text-vs-text semantic-equivalence judgement.

    Use this for "is the extracted free-text value the same fact as
    the expected one?" decisions where there is no source document to
    consult — only two strings to compare. See
    :meth:`gaik.software_components.validators.llm_judge.LLMJudge.judge_text_pair`.

    Attributes:
        equivalent: ``True`` when the two values carry the same factual
            information (ignoring case, whitespace, morphology,
            paraphrasing). ``False`` for any meaningful divergence.
        severity: ``"ok"`` when equivalent, ``"suspect"`` for partial /
            ambiguous matches, ``"wrong"`` for clear divergence.
        score: Likert 1-5 (1 = clear divergence, 5 = identical meaning).
            ``score >= 4`` is the conventional cut-off for "equivalent".
        reason: Short (≤20 words) explanation of the verdict.
        usage: Token + cost record for the call.
    """

    equivalent: bool
    severity: Severity
    score: int
    reason: str
    usage: JudgeUsage


@dataclass
class PairwiseResult:
    """Result of a pairwise A-vs-B comparison with optional position-bias mitigation.

    Attributes:
        winner: ``"a"``, ``"b"``, or ``"tie"``. With ``swap_and_average=True``
            and the two passes disagreeing, the winner is forced to ``"tie"``.
        score_a: Likert 1-5 score for option A. Averaged across both passes
            when ``swap_and_average=True``.
        score_b: Likert 1-5 score for option B.
        reason: Short explanation. With swap-disagreement, includes both
            passes' reasons.
        swap_consistent: ``True`` when both passes agreed on the winner
            (or when ``swap_and_average=False``).
        raw_first_pass: Raw judge JSON for the first pass.
        raw_second_pass: Raw judge JSON for the swapped pass; ``None`` when
            ``swap_and_average=False``.
        usage: One :class:`JudgeUsage` per pass.
    """

    winner: Literal["a", "b", "tie"]
    score_a: int
    score_b: int
    reason: str
    swap_consistent: bool
    raw_first_pass: str
    raw_second_pass: str | None
    usage: list[JudgeUsage]
