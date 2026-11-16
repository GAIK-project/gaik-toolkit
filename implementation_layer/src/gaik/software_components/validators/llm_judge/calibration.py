"""Calibration of LLM-judge against a human-labeled ground-truth dataset.

HuggingFace cookbook (https://huggingface.co/learn/cookbook/llm_judge) reports
~0.84 Pearson correlation between a Likert-1-to-4 judge prompt and human raters
on FeedbackQA. Use :func:`calibrate_against_human_labels` to verify your rubric
reaches a similar bar on your own data before deploying.

Workflow:
    1. Hand-label 30 examples from your domain on the same 1-5 Likert scale
       used by ``ValidationRubric(scoring_mode="likert_1_5")``.
    2. Wrap them in :class:`CalibrationItem` instances.
    3. Call :func:`calibrate_against_human_labels`. The returned
       :class:`CalibrationReport` has Pearson r and severity-agreement rate.

Pure-Python implementation of Pearson correlation — no pandas / numpy hard
dep. ``CalibrationReport.per_item`` retains raw judge vs. human pairs so you
can post-process with pandas if you want a Spearman rho or a full residual plot.
"""

from __future__ import annotations

import logging

from .llm_judge import LLMJudge
from .schema import (
    CalibrationItem,
    CalibrationReport,
    Severity,
    ValidationRubric,
)

logger = logging.getLogger(__name__)

_SEVERITY_RANK: dict[str, int] = {"ok": 0, "suspect": 1, "wrong": 2}


def calibrate_against_human_labels(
    judge: LLMJudge,
    dataset: list[CalibrationItem],
    rubric: ValidationRubric | None = None,
    field_filter: str | None = None,
) -> CalibrationReport:
    """Run *judge* over *dataset* and report agreement with human scores.

    Args:
        judge: The :class:`LLMJudge` to calibrate.
        dataset: Human-labeled :class:`CalibrationItem` list. Aim for 30+
            items for a stable Pearson estimate.
        rubric: Rubric for the judge. If ``None``, defaults to
            ``ValidationRubric(scoring_mode="likert_1_5")``. The rubric MUST
            have ``scoring_mode != "severity"`` for a meaningful Pearson r.
        field_filter: If given, only flags matching this field name
            participate in the per-item judge score (averaged across them).
            Otherwise all flags participate.

    Returns:
        :class:`CalibrationReport` with Pearson r, severity-agreement rate,
        means, and a per-item dump for inspection.
    """
    rubric = rubric or ValidationRubric(scoring_mode="likert_1_5")
    if rubric.scoring_mode == "severity":
        logger.warning(
            "calibrate_against_human_labels with scoring_mode='severity' "
            "cannot compute a meaningful Pearson r — judge scores will be 0. "
            "Switch to scoring_mode='likert_1_5'."
        )

    per_item: list[dict] = []
    for item in dataset:
        result = judge.validate(item.source_pages, item.extracted, rubric)
        relevant = (
            [f for f in result.flags if f.field == field_filter] if field_filter else result.flags
        )

        scores = [f.score for f in relevant if f.score]
        judge_error = getattr(result, "judge_error", None)
        # An unreadable response, or one with no scored flag for this field,
        # has no judge score: it is reported per item and left out of r, the
        # severity agreement and the means, instead of counting as 0 / "ok".
        skipped_reason: str | None = None
        if judge_error:
            skipped_reason = "judge_error"
        elif not scores:
            skipped_reason = "no scored flag"
        judge_score: float | None = sum(scores) / len(scores) if scores else None

        judge_severity: Severity | None
        if judge_error:
            judge_severity = None
        elif relevant:
            judge_severity = max((f.severity for f in relevant), key=lambda s: _SEVERITY_RANK[s])
        else:
            judge_severity = "ok"

        per_item.append(
            {
                "human_score": item.human_score,
                "judge_score": None if skipped_reason else judge_score,
                "human_severity": item.human_severity,
                "judge_severity": judge_severity,
                "note": item.note,
                "n_flags": len(relevant),
                "cost_usd": result.usage.cost_usd,
                "skipped": skipped_reason,
                "judge_error": judge_error,
            }
        )

    skipped = [p for p in per_item if p["skipped"]]
    if skipped:
        logger.warning(
            "calibrate_against_human_labels: %d of %d items have no judge score "
            "(unreadable response or no scored flag) and are left out of r and the means",
            len(skipped),
            len(per_item),
        )

    n = len(per_item)
    scored = [p for p in per_item if not p["skipped"]]
    judge_scores = [p["judge_score"] for p in scored]
    human_scores = [float(p["human_score"]) for p in scored]
    n_scored = len(scored)
    pearson = _pearson(judge_scores, human_scores) if n_scored > 1 else None

    sev_compared = [
        p for p in per_item if p["human_severity"] is not None and p["judge_severity"] is not None
    ]
    sev_agree = (
        sum(1 for p in sev_compared if p["human_severity"] == p["judge_severity"])
        / len(sev_compared)
        if sev_compared
        else 0.0
    )

    return CalibrationReport(
        n_items=n,
        pearson_r=pearson,
        severity_agreement_rate=sev_agree,
        mean_judge_score=sum(judge_scores) / n_scored if n_scored else 0.0,
        mean_human_score=sum(human_scores) / n_scored if n_scored else 0.0,
        per_item=per_item,
    )


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pure-Python Pearson correlation. Returns ``None`` when undefined."""
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    den_x = (sum((x - mean_x) ** 2 for x in xs)) ** 0.5
    den_y = (sum((y - mean_y) ** 2 for y in ys)) ** 0.5
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)
