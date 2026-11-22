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
        means, and a per-item dump for inspection. ``n_items`` is the size of
        the dataset. Pearson r and both means are over the items the judge
        scored; an item with no score (no flag for ``field_filter``, flags
        without a score, or a reply that could not be read in full) is left
        out of them, not counted as 0 on the 1-5 scale. Its ``per_item`` entry
        has ``"scored": False`` (its ``"judge_score"`` stays 0.0, which is no
        score) and, for a reply not read in full, the ``"judge_error"``; such a
        reply is also left out of the severity agreement. A warning says how
        many items were left out.
    """
    rubric = rubric or ValidationRubric(scoring_mode="likert_1_5")
    if rubric.scoring_mode == "severity":
        logger.warning(
            "calibrate_against_human_labels with scoring_mode='severity' "
            "cannot compute a meaningful Pearson r — the judge gives no scores. "
            "Switch to scoring_mode='likert_1_5'."
        )

    per_item: list[dict] = []
    for item in dataset:
        result = judge.validate(item.source_pages, item.extracted, rubric)
        relevant = (
            [f for f in result.flags if f.field == field_filter] if field_filter else result.flags
        )

        scores = [f.score for f in relevant if f.score]
        judge_score = sum(scores) / len(scores) if scores else None

        judge_error = result.judge_error
        judge_severity: Severity | None
        if judge_error:
            # Some or all of the reply could not be read: the flag left out may be the one
            # that matters, so the item has no verdict (as a panel leaves such a judge out).
            judge_score = None
            judge_severity = None
        elif relevant:
            judge_severity = max((f.severity for f in relevant), key=lambda s: _SEVERITY_RANK[s])
        else:
            judge_severity = "ok"

        per_item.append(
            {
                "human_score": item.human_score,
                # 0.0 as before for an unscored item; "scored" tells it apart.
                "judge_score": judge_score if judge_score is not None else 0.0,
                "scored": judge_score is not None,
                "human_severity": item.human_severity,
                "judge_severity": judge_severity,
                "judge_error": judge_error,
                "note": item.note,
                "n_flags": len(relevant),
                "cost_usd": result.usage.cost_usd,
            }
        )

    n = len(per_item)
    scored = [p for p in per_item if p["scored"]]
    if len(scored) < n:
        logger.warning(
            "%d of %d calibration items have no judge score and are left out of "
            "Pearson r and the means",
            n - len(scored),
            n,
        )
    judge_scores = [p["judge_score"] for p in scored]
    human_scores = [float(p["human_score"]) for p in scored]
    pearson = _pearson(judge_scores, human_scores) if len(scored) > 1 else None

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
        mean_judge_score=sum(judge_scores) / len(scored) if scored else 0.0,
        mean_human_score=sum(human_scores) / len(scored) if scored else 0.0,
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
