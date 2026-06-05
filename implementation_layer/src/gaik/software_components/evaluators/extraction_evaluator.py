"""Field-level extraction evaluator.

Computes Precision / Recall / F1 over an expected vs. extracted dict pair,
plus a hallucination rate (extracted fields not present in the expected).

Two matching modes:

- **Exact** (default): values are compared after light normalization
  (strip whitespace, case-insensitive). Fast, deterministic, no LLM cost.
- **Semantic** (``judge`` arg): uses :class:`LLMJudge` to grade ambiguous
  free-text fields on a Likert 1-5 scale; ``score >= 4`` counts as a match.
  Slower and costs tokens but tolerates paraphrasing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from .dataset import EvaluationDataset

if TYPE_CHECKING:
    from gaik.software_components.validators.llm_judge import (
        LLMJudge,
    )

logger = logging.getLogger(__name__)

MatchMode = Literal["exact", "semantic"]


@dataclass
class FieldVerdict:
    """Per-field evaluation outcome."""

    field: str
    expected: Any
    extracted: Any
    matched: bool
    is_hallucination: bool = False
    is_missing: bool = False
    score: int = 0
    reason: str = ""


@dataclass
class ExtractionMetrics:
    """Aggregate Precision / Recall / F1 + hallucination rate."""

    precision: float
    recall: float
    f1: float
    hallucination_rate: float
    n_correct: int
    n_expected: int
    n_extracted: int

    def __str__(self) -> str:  # pragma: no cover - human-readable
        return (
            f"ExtractionMetrics(P={self.precision:.3f}, R={self.recall:.3f}, "
            f"F1={self.f1:.3f}, hallucination={self.hallucination_rate:.3f}, "
            f"correct={self.n_correct}/{self.n_expected}, "
            f"extracted={self.n_extracted})"
        )


@dataclass
class ExtractionItemResult:
    """Per-item evaluation outcome."""

    expected: dict
    extracted: dict
    verdicts: list[FieldVerdict]
    metrics: ExtractionMetrics


@dataclass
class ExtractionEvaluationResult:
    """Aggregate result over the whole dataset."""

    per_item: list[ExtractionItemResult]
    aggregate: ExtractionMetrics
    cost_usd: float = 0.0
    duration_s: float = 0.0


class ExtractionEvaluator:
    """Evaluate structured extractor outputs against ground-truth dicts.

    Args:
        match_mode: ``"exact"`` (default) or ``"semantic"``. ``semantic``
            requires ``judge`` to be set.
        judge: Optional :class:`LLMJudge` used to grade ambiguous field
            matches in ``semantic`` mode. Re-uses the v2 Likert rubric.
        case_insensitive: When ``True`` (default), exact comparisons fold case.
        strip_whitespace: When ``True`` (default), exact comparisons strip
            leading/trailing whitespace.
    """

    def __init__(
        self,
        *,
        match_mode: MatchMode = "exact",
        judge: LLMJudge | None = None,
        case_insensitive: bool = True,
        strip_whitespace: bool = True,
    ) -> None:
        if match_mode == "semantic" and judge is None:
            raise ValueError("match_mode='semantic' requires a judge instance")
        self.match_mode = match_mode
        self.judge = judge
        self.case_insensitive = case_insensitive
        self.strip_whitespace = strip_whitespace

    # ── Public API ────────────────────────────────────────────────

    def evaluate_item(self, expected: dict, extracted: dict) -> ExtractionItemResult:
        """Evaluate a single (expected, extracted) pair."""
        if not isinstance(expected, dict) or not isinstance(extracted, dict):
            raise TypeError("expected and extracted must both be dict")

        verdicts: list[FieldVerdict] = []

        # Walk expected fields → matched / missing
        for key, exp_val in expected.items():
            ext_val = extracted.get(key, _MISSING)
            if ext_val is _MISSING:
                verdicts.append(
                    FieldVerdict(
                        field=key,
                        expected=exp_val,
                        extracted=None,
                        matched=False,
                        is_missing=True,
                        reason="Field missing from extractor output",
                    )
                )
            else:
                verdicts.append(self._compare(key, exp_val, ext_val))

        # Walk extractor-only fields → hallucinations
        for key, ext_val in extracted.items():
            if key not in expected:
                verdicts.append(
                    FieldVerdict(
                        field=key,
                        expected=None,
                        extracted=ext_val,
                        matched=False,
                        is_hallucination=True,
                        reason="Field not in expected schema",
                    )
                )

        metrics = _compute_metrics(verdicts)
        return ExtractionItemResult(
            expected=expected,
            extracted=extracted,
            verdicts=verdicts,
            metrics=metrics,
        )

    def evaluate_dataset(
        self,
        dataset: EvaluationDataset,
        extracted_outputs: list[dict],
    ) -> ExtractionEvaluationResult:
        """Evaluate a full dataset given pipeline outputs.

        Args:
            dataset: :class:`EvaluationDataset` — ``item.expected`` must be a
                ``dict`` for each item.
            extracted_outputs: One pipeline output ``dict`` per item, in the
                same order as ``dataset.items``.

        Returns:
            :class:`ExtractionEvaluationResult` with per-item details and a
            micro-averaged aggregate ``ExtractionMetrics``.
        """
        if len(dataset) != len(extracted_outputs):
            raise ValueError(
                f"dataset length ({len(dataset)}) != extracted_outputs length "
                f"({len(extracted_outputs)})"
            )

        per_item: list[ExtractionItemResult] = []
        for item, extracted in zip(dataset, extracted_outputs, strict=True):
            if not isinstance(item.expected, dict):
                raise TypeError("ExtractionEvaluator requires item.expected to be a dict")
            per_item.append(self.evaluate_item(item.expected, extracted))

        aggregate = _aggregate_micro(per_item)
        cost_usd = 0.0  # judge-graded matches would charge here in semantic mode
        return ExtractionEvaluationResult(
            per_item=per_item,
            aggregate=aggregate,
            cost_usd=cost_usd,
        )

    # ── Internal ──────────────────────────────────────────────────

    def _compare(self, field_name: str, expected: Any, extracted: Any) -> FieldVerdict:
        if self._exact_eq(expected, extracted):
            return FieldVerdict(
                field=field_name,
                expected=expected,
                extracted=extracted,
                matched=True,
                score=5,
                reason="exact match",
            )

        if self.match_mode == "semantic" and self.judge is not None:
            score, reason = self._semantic_match(field_name, expected, extracted)
            return FieldVerdict(
                field=field_name,
                expected=expected,
                extracted=extracted,
                matched=score >= 4,
                score=score,
                reason=reason,
            )

        return FieldVerdict(
            field=field_name,
            expected=expected,
            extracted=extracted,
            matched=False,
            reason="value differs",
        )

    def _exact_eq(self, a: Any, b: Any) -> bool:
        if isinstance(a, str) and isinstance(b, str):
            if self.strip_whitespace:
                a = a.strip()
                b = b.strip()
            if self.case_insensitive:
                return a.casefold() == b.casefold()
            return a == b
        return a == b

    def _semantic_match(self, field_name: str, expected: Any, extracted: Any) -> tuple[int, str]:
        """Use ``LLMJudge.judge_text_pair`` to grade ambiguous matches on a 1-5 Likert scale.

        Replaces an older empty-bytes ``validate(source_pages=[b""])`` workaround
        with a clean text-only call. Returns ``(score, reason)`` where
        ``score >= 4`` is the conventional "equivalent" cut-off.
        """
        assert self.judge is not None
        try:
            judgement = self.judge.judge_text_pair(
                extracted_text=str(extracted) if extracted is not None else "",
                expected_text=str(expected) if expected is not None else "",
                field_name=field_name,
            )
        except ValueError:
            # Both sides empty — caller should have short-circuited already.
            return 5, "both empty"
        except Exception:  # pragma: no cover - judge / network failure
            logger.exception(
                "Semantic match judge call failed for field %r; falling back to non-match",
                field_name,
            )
            return 0, "judge call failed"
        return judgement.score, judgement.reason or "judge graded"


_MISSING = object()


def _compute_metrics(verdicts: list[FieldVerdict]) -> ExtractionMetrics:
    n_expected = sum(1 for v in verdicts if not v.is_hallucination)
    n_extracted = sum(1 for v in verdicts if not v.is_missing)
    n_correct = sum(1 for v in verdicts if v.matched)
    n_hallucination = sum(1 for v in verdicts if v.is_hallucination)

    precision = n_correct / n_extracted if n_extracted else 0.0
    recall = n_correct / n_expected if n_expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    hallucination_rate = n_hallucination / n_extracted if n_extracted else 0.0

    return ExtractionMetrics(
        precision=precision,
        recall=recall,
        f1=f1,
        hallucination_rate=hallucination_rate,
        n_correct=n_correct,
        n_expected=n_expected,
        n_extracted=n_extracted,
    )


def _aggregate_micro(per_item: list[ExtractionItemResult]) -> ExtractionMetrics:
    total_correct = sum(r.metrics.n_correct for r in per_item)
    total_expected = sum(r.metrics.n_expected for r in per_item)
    total_extracted = sum(r.metrics.n_extracted for r in per_item)
    total_hallucination = sum(sum(1 for v in r.verdicts if v.is_hallucination) for r in per_item)

    precision = total_correct / total_extracted if total_extracted else 0.0
    recall = total_correct / total_expected if total_expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    hallucination_rate = total_hallucination / total_extracted if total_extracted else 0.0
    return ExtractionMetrics(
        precision=precision,
        recall=recall,
        f1=f1,
        hallucination_rate=hallucination_rate,
        n_correct=total_correct,
        n_expected=total_expected,
        n_extracted=total_extracted,
    )
