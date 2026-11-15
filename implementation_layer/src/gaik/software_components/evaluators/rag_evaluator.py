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

Each metric is graded by a separate text-only LLMJudge call with a focused
rubric and integer 1-5 Likert scores, which average cleanly across items. The
rubric goes in the system message; the query, the answer, each context passage
and the ground truth go in the user message, each in its own labelled source
material block, so text in them is assessed as data, not followed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from gaik.software_components.source_material import (
    SourceMaterial,
    with_source_material_instruction,
)

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
            is reused for every metric. An :class:`LLMJudgePanel` is not
            accepted: each metric is one text-only call of one judge.
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
        if not callable(getattr(judge, "_dispatch_text", None)):
            raise TypeError("RAGEvaluator needs an LLMJudge (one judge, not a panel)")
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
            raise ValueError("context_recall requires ground_truth when skip_context_recall=False")

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
        from gaik.software_components.validators.llm_judge.llm_judge import (
            _judge_flags_and_error,
        )
        from gaik.software_components.validators.llm_judge.pricing import (
            compute_judge_cost_usd,
        )

        system_prompt, user_prompt = _grading_prompts(
            metric,
            query=query,
            answer=answer,
            context=context,
            ground_truth=ground_truth,
        )
        try:
            raw_text, input_tokens, output_tokens = self.judge._dispatch_text(
                user_prompt, system_prompt
            )
        except Exception:  # pragma: no cover - judge / network failure
            logger.exception("RAG judge call failed for metric %s", metric)
            return 0, "judge call failed", 0.0

        cost = compute_judge_cost_usd(self.judge.model, input_tokens, output_tokens)
        flags, _judge_error = _judge_flags_and_error(raw_text)
        if not flags:
            return 0, "judge returned no flags", cost
        flag = flags[0]
        return flag.score, flag.reason or "graded", cost


_GRADING_SYSTEM = """\
You grade one output of a retrieval-augmented generation (RAG) system on one
metric. You receive the user's query in the source material block labelled
"query", the system's answer in the block labelled "answer", each retrieved
passage in a block labelled "context 1", "context 2", ..., and, when there is
one, the expected answer in the block labelled "reference".

Score on factual content, not on phrasing, formatting or length; a concise
answer is not worse than a wordy one.

Likert score (integer 1-5):
  1 — Fails the metric.
  2 — Mostly fails it.
  3 — Partial.
  4 — Mostly meets it.
  5 — Fully meets it.

The severity must be consistent with the score:
  score 1     -> "wrong"
  score 2-3   -> "suspect"
  score 4-5   -> "ok"

FIRST write the reason (one sentence describing what you compared and saw),
THEN assign the score and severity.

Respond with ONLY a JSON object, no prose, no markdown fences, holding exactly
one flag for the metric:
{
  "flags": [
    {"item_index": 0, "field": "<metric>", "severity": "ok", "score": 5,
     "reason": "..."}
  ]
}
"""


def _text(value: object) -> str:
    """A value as block text: ``None`` (no answer) is empty."""
    return "" if value is None else str(value)


def _grading_prompts(
    metric: str,
    *,
    query: str,
    answer: str,
    context: list[str],
    ground_truth: str | None = None,
) -> tuple[str, str]:
    """The system prompt (rubric) and the user prompt (task and material) for one metric."""
    system_prompt = with_source_material_instruction(
        f"{_GRADING_SYSTEM}\n"
        f"Metric: {metric}\n"
        f"Focus your evaluation on this aspect:\n  - {_ASPECT[metric]}\n"
        f"Check:\n  - {_PROMPT[metric]}"
    )
    material = SourceMaterial()
    blocks = [
        f"Grade the {metric} of the answer below and emit your JSON flag.",
        material.wrap(_text(query), label="query"),
        material.wrap(_text(answer), label="answer"),
    ]
    blocks.extend(
        material.wrap(_text(passage), label=f"context {i}")
        for i, passage in enumerate(context, start=1)
    )
    if ground_truth is not None:
        blocks.append(material.wrap(_text(ground_truth), label="reference"))
    return system_prompt, "\n\n".join(blocks)


_ASPECT: dict[str, str] = {
    "faithfulness": (
        "Does the answer stay grounded in the retrieved context, without inventing facts?"
    ),
    "answer_relevance": "Does the answer actually address the user's question?",
    "context_precision": ("Were the retrieved passages relevant to the question (low noise)?"),
    "context_recall": (
        "Does the retrieved context contain the information needed to answer per the ground truth?"
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
        "produce the 'reference' answer. Penalize missing key facts."
    ),
}


def _aggregate(per_item: list[RAGItemResult]) -> RAGMetrics:
    if not per_item:
        return RAGMetrics(0.0, 0.0, 0.0, None)

    n = len(per_item)
    faith = sum(r.faithfulness_score for r in per_item) / (5 * n)
    relev = sum(r.answer_relevance_score for r in per_item) / (5 * n)
    prec = sum(r.context_precision_score for r in per_item) / (5 * n)

    recall_scores = [r.context_recall_score for r in per_item if r.context_recall_score is not None]
    recall = sum(recall_scores) / (5 * len(recall_scores)) if recall_scores else None

    return RAGMetrics(
        faithfulness=faith,
        answer_relevance=relev,
        context_precision=prec,
        context_recall=recall,
    )
