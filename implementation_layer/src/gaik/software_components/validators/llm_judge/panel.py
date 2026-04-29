"""LLM-as-judge panel — run multiple judges and aggregate via majority vote.

Why a panel?

- Single-judge bias: each model has its own self-preference bias (arXiv 2604.22891)
  and verbosity / position biases. Running 2-3 different providers as a panel
  averages these out.
- "When AIs Judge AIs" (arXiv 2508.02994) and the Survey on LLM-as-a-Judge
  (arXiv 2411.15594) both find ensemble judging closer to human ratings than
  single-judge configurations.

Recommendation: pair providers from different families. A useful default is
Gemini 3 Flash + Claude Haiku 4.5 + GPT-5.4-mini.
"""

from __future__ import annotations

from collections import Counter
from statistics import median

from .llm_judge import LLMJudge
from .schema import (
    JudgePanelResult,
    Severity,
    ValidationFlag,
    ValidationRubric,
)

_SEVERITY_RANK: dict[str, int] = {"ok": 0, "suspect": 1, "wrong": 2}


class LLMJudgePanel:
    """Run a panel of judges sequentially and aggregate the results.

    Args:
        judges: Two or more :class:`LLMJudge` instances. Diverse providers
            give the strongest debiasing effect.
    """

    def __init__(self, judges: list[LLMJudge]) -> None:
        if len(judges) < 2:
            raise ValueError("LLMJudgePanel requires at least 2 judges")
        self.judges = list(judges)

    def validate(
        self,
        source_pages: list[bytes],
        extracted: list[dict] | dict,
        rubric: ValidationRubric | None = None,
    ) -> JudgePanelResult:
        """Validate by running every judge and aggregating with majority vote.

        Args:
            source_pages: PNG-encoded page images.
            extracted: Extractor output (list[dict] or dict).
            rubric: Shared rubric. ``rubric.scoring_mode="likert_1_5"`` is
                recommended so the panel can compute a median score.

        Returns:
            :class:`JudgePanelResult` with each judge's output, aggregated
            flags, an agreement metric, and total cost / duration.
        """
        per_judge = [j.validate(source_pages, extracted, rubric) for j in self.judges]
        aggregated = _aggregate_flags([r.flags for r in per_judge])
        agreement = _agreement_score([r.flags for r in per_judge])
        total_cost = sum(r.usage.cost_usd for r in per_judge)
        total_duration = sum(r.usage.duration_s for r in per_judge)
        return JudgePanelResult(
            per_judge=per_judge,
            aggregated_flags=aggregated,
            agreement_score=agreement,
            total_cost_usd=total_cost,
            total_duration_s=total_duration,
        )


def _flag_key(flag: ValidationFlag) -> tuple[int, str]:
    return (flag.item_index, flag.field)


def _aggregate_flags(per_judge_flags: list[list[ValidationFlag]]) -> list[ValidationFlag]:
    """Majority-vote aggregation per ``(item_index, field)`` key.

    For each key:

    - severity = mode of severities; ties resolve to the worst severity
      (precaution: "wrong" > "suspect" > "ok") so the consumer doesn't
      miss issues a minority of judges flagged.
    - score = median of non-zero Likert scores.
    - reason = the reason from the first judge whose severity matched
      the winning severity.
    - suggested_value = first non-None across judges.
    """
    groups: dict[tuple[int, str], list[ValidationFlag]] = {}
    for flags in per_judge_flags:
        for f in flags:
            groups.setdefault(_flag_key(f), []).append(f)

    aggregated: list[ValidationFlag] = []
    for key, flags in groups.items():
        sev_counts = Counter(f.severity for f in flags)
        max_count = max(sev_counts.values())
        candidates = [s for s, c in sev_counts.items() if c == max_count]
        winning_severity: Severity = max(candidates, key=lambda s: _SEVERITY_RANK[s])  # type: ignore[arg-type]

        scores = [f.score for f in flags if f.score]
        agg_score = int(round(median(scores))) if scores else 0

        sample = next((f for f in flags if f.severity == winning_severity), flags[0])
        suggested = next((f.suggested_value for f in flags if f.suggested_value), None)

        aggregated.append(
            ValidationFlag(
                item_index=key[0],
                field=key[1],
                severity=winning_severity,
                score=agg_score,
                reason=sample.reason,
                suggested_value=suggested,
            )
        )
    return aggregated


def _agreement_score(per_judge_flags: list[list[ValidationFlag]]) -> float:
    """Fraction of ``(item_index, field)`` keys where ALL judges agreed on severity.

    Simple metric (no Cohen's kappa) — works without a hard pandas dependency.
    Returns 1.0 for full agreement, 0.0 for total disagreement, and 1.0 when
    no flags were emitted by any judge.
    """
    keys: dict[tuple[int, str], list[Severity]] = {}
    for flags in per_judge_flags:
        for f in flags:
            keys.setdefault(_flag_key(f), []).append(f.severity)
    if not keys:
        return 1.0
    n_full_agree = sum(1 for sevs in keys.values() if len(set(sevs)) == 1)
    return n_full_agree / len(keys)
