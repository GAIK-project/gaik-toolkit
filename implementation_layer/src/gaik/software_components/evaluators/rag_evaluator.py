"""RAGAS-style RAG evaluator built on top of GAIK's LLMJudge v2.

Computes four standard RAG quality metrics, each on a 1-5 Likert scale (mean
across items, normalized to 0-1 in the aggregate):

- **faithfulness** — does the answer stay grounded in the retrieved context?
  Penalizes hallucinations.
- **answer_relevance** — does the answer actually address the question?
- **context_precision** — were the retrieved passages relevant to the
  question? (signal-to-noise of the retriever)
- **context_recall** — when ``ground_truth`` is provided, does the retrieved
  context contain the information needed to answer? (retriever miss-rate)

Each metric is graded by a separate LLMJudge call with a focused rubric. The
judge runs in ``scoring_mode="likert_1_5"`` so we get integer 1-5 scores
which average cleanly across items.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gaik.software_components.validators.llm_judge import (
        LLMJudge,
    )

logger = logging.getLogger(__name__)


@dataclass
class RAGMetrics:
    """Aggregate RAG quality metrics, all in [0.0, 1.0]."""

    faithfulness: float
    answer_relevance: float
    context_precision: float
    context_recall: float | None = None

    def __str__(self) -> str:  # pragma: no cover - human-readable
        cr = (
            f"context_recall={self.context_recall:.3f}"
            if self.context_recall is not None
            else "context_recall=N/A (no ground truth)"
        )
        return (
            f"RAGMetrics(faithfulness={self.faithfulness:.3f}, "
            f"answer_relevance={self.answer_relevance:.3f}, "
            f"context_precision={self.context_precision:.3f}, "
            f"{cr})"
        )


@dataclass
class RAGItemResult:
    """Per-item RAG evaluation outcome."""

    query: str
    answer: str
    context: list[str]
    ground_truth: str | None
    faithfulness_score: int
    answer_relevance_score: int
    context_precision_score: int
    context_recall_score: int | None
    reasons: dict[str, str] = field(default_factory=dict)
    cost_usd: float = 0.0


@dataclass
class RAGEvaluationResult:
    """Aggregate RAG evaluation across a dataset."""

    per_item: list[RAGItemResult]
    aggregate: RAGMetrics
    cost_usd: float = 0.0
    duration_s: float = 0.0


class RAGEvaluator:
    """Grade RAG outputs (query → answer + context) on four quality dimensions.

    Args:
        judge: An :class:`LLMJudge` instance (any provider). The same judge
            is reused for every metric; supply a panel-aware judge if you
            want cross-model averaging.
        skip_context_recall: When ``True`` (default), context_recall is
            skipped for items without a ``ground_truth``. Set to ``False``
            to error on missing ground truth.
    """

    def __init__(
        self,
        judge: LLMJudge,
        *,
        skip_context_recall: bool = True,
    ) -> None:
        self.judge = judge
        self.skip_context_recall = skip_context_recall

    # ── Public API ────────────────────────────────────────────────

    def evaluate_item(
        self,
        query: str,
        answer: str,
        context: list[str],
        ground_truth: str | None = None,
    ) -> RAGItemResult:
        """Grade one (query, answer, context) tuple."""
        faith_score, faith_reason, faith_cost = self._grade(
            "faithfulness",
            query=query,
            answer=answer,
            context=context,
        )
        relev_score, relev_reason, relev_cost = self._grade(
            "answer_relevance",
            query=query,
            answer=answer,
            context=context,
        )
        prec_score, prec_reason, prec_cost = self._grade(
            "context_precision",
            query=query,
            answer=answer,
            context=context,
        )

        recall_score: int | None = None
        recall_reason = ""
        recall_cost = 0.0
        if ground_truth is not None:
            recall_score, recall_reason, recall_cost = self._grade(
                "context_recall",
                query=query,
                answer=answer,
                context=context,
                ground_truth=ground_truth,
            )
        elif not self.skip_context_recall:
            raise ValueError(
                "context_recall requires ground_truth when skip_context_recall=False"
            )

        total_cost = faith_cost + relev_cost + prec_cost + recall_cost
        return RAGItemResult(
            query=query,
            answer=answer,
            context=list(context),
            ground_truth=ground_truth,
            faithfulness_score=faith_score,
            answer_relevance_score=relev_score,
            context_precision_score=prec_score,
            context_recall_score=recall_score,
            reasons={
                "faithfulness": faith_reason,
                "answer_relevance": relev_reason,
                "context_precision": prec_reason,
                "context_recall": recall_reason,
            },
            cost_usd=total_cost,
        )

    def evaluate_dataset(
        self,
        items: list[RAGItemResult] | list[dict],
    ) -> RAGEvaluationResult:
        """Aggregate already-evaluated items, OR evaluate raw dicts in-place.

        Each dict must have keys ``query``, ``answer``, ``context``, and
        optionally ``ground_truth``.
        """
        per_item: list[RAGItemResult] = []
        for raw in items:
            if isinstance(raw, RAGItemResult):
                per_item.append(raw)
            else:
                per_item.append(
                    self.evaluate_item(
                        query=raw["query"],
                        answer=raw["answer"],
                        context=raw["context"],
                        ground_truth=raw.get("ground_truth"),
                    )
                )

        aggregate = _aggregate(per_item)
        total_cost = sum(r.cost_usd for r in per_item)
        return RAGEvaluationResult(
            per_item=per_item,
            aggregate=aggregate,
            cost_usd=total_cost,
        )

    # ── Internal ──────────────────────────────────────────────────

    def _grade(
        self,
        metric: str,
        *,
        query: str,
        answer: str,
        context: list[str],
        ground_truth: str | None = None,
    ) -> tuple[int, str, float]:
        from gaik.software_components.validators.llm_judge import ValidationRubric

        rubric = ValidationRubric(
            scoring_mode="likert_1_5",
            evaluation_aspects=[_ASPECT[metric]],
            field_checks=[_PROMPT[metric]],
        )

        # The judge expects source_pages + extracted JSON. We pack the
        # query / answer / context as the "extracted" payload and pass an
        # empty image — the prompt explicitly tells the judge to ignore
        # images and grade text only.
        extracted = {
            "query": query,
            "answer": answer,
            "context": context,
        }
        if ground_truth is not None:
            extracted["ground_truth"] = ground_truth

        try:
            result = self.judge.validate(
                source_pages=[b""],
                extracted=extracted,
                rubric=rubric,
            )
        except Exception:  # pragma: no cover - judge / network failure
            logger.exception("RAG judge call failed for metric %s", metric)
            return 0, "judge call failed", 0.0

        if not result.flags:
            return 0, "judge returned no flags", result.usage.cost_usd
        flag = result.flags[0]
        return flag.score, flag.reason or "graded", result.usage.cost_usd


_ASPECT: dict[str, str] = {
    "faithfulness": (
        "Does the answer stay grounded in the retrieved context, "
        "without inventing facts?"
    ),
    "answer_relevance": "Does the answer actually address the user's question?",
    "context_precision": (
        "Were the retrieved passages relevant to the question (low noise)?"
    ),
    "context_recall": (
        "Does the retrieved context contain the information needed to "
        "answer per the ground truth?"
    ),
}

_PROMPT: dict[str, str] = {
    "faithfulness": (
        "Score 1-5 how faithful the 'answer' is to the 'context'. "
        "Penalize hallucinations and unsupported claims."
    ),
    "answer_relevance": (
        "Score 1-5 how directly the 'answer' addresses the 'query'. "
        "Penalize off-topic or evasive answers."
    ),
    "context_precision": (
        "Score 1-5 how relevant the 'context' passages are to the 'query'. "
        "Penalize noise / off-topic chunks."
    ),
    "context_recall": (
        "Score 1-5 how well the 'context' covers the information needed to "
        "produce 'ground_truth'. Penalize missing key facts."
    ),
}


def _aggregate(per_item: list[RAGItemResult]) -> RAGMetrics:
    if not per_item:
        return RAGMetrics(0.0, 0.0, 0.0, None)

    n = len(per_item)
    faith = sum(r.faithfulness_score for r in per_item) / (5 * n)
    relev = sum(r.answer_relevance_score for r in per_item) / (5 * n)
    prec = sum(r.context_precision_score for r in per_item) / (5 * n)

    recall_scores = [
        r.context_recall_score for r in per_item if r.context_recall_score is not None
    ]
    recall = sum(recall_scores) / (5 * len(recall_scores)) if recall_scores else None

    return RAGMetrics(
        faithfulness=faith,
        answer_relevance=relev,
        context_precision=prec,
        context_recall=recall,
    )
