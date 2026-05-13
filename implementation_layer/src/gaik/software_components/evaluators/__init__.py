"""Evaluation suite for GAIK pipelines.

Reusable evaluators that run a dataset through a pipeline and compute aggregate
quality metrics. Composes on top of the v2 LLMJudge so LLM-graded metrics
share the same Likert / panel / few-shot machinery as the validator.

Core building blocks
~~~~~~~~~~~~~~~~~~~~

- :class:`EvaluationItem` / :class:`EvaluationDataset` — minimal IO format
  with ``from_jsonl()``, ``from_csv()``, ``from_list()`` constructors.
- :class:`ExtractionEvaluator` — field-level Precision / Recall / F1 plus
  hallucination rate against a ground-truth dict. Optional ``judge`` argument
  enables LLM-graded *semantic* matching for free-text fields.
- :class:`RAGEvaluator` — RAGAS-style metrics (faithfulness, answer
  relevance, context precision, context recall) computed via LLMJudge.
- :class:`BatchEvaluationRunner` — runs any callable pipeline over an
  :class:`EvaluationDataset` and feeds outputs to an evaluator.

Example::

    from gaik.software_components.validators import LLMJudge
    from gaik.software_components.evaluators import (
        EvaluationDataset, ExtractionEvaluator,
    )

    dataset = EvaluationDataset.from_jsonl("eval/extractions.jsonl")
    evaluator = ExtractionEvaluator()
    result = evaluator.evaluate_dataset(dataset, extracted_outputs=my_outputs)
    print(result.aggregate)
"""

from .dataset import EvaluationDataset, EvaluationItem
from .extraction_evaluator import (
    ExtractionEvaluationResult,
    ExtractionEvaluator,
    ExtractionItemResult,
    ExtractionMetrics,
)
from .rag_evaluator import (
    RAGEvaluationResult,
    RAGEvaluator,
    RAGItemResult,
    RAGMetrics,
)
from .runner import BatchEvaluationRunner, RunnerResult

__all__ = [
    # Data shapes
    "EvaluationItem",
    "EvaluationDataset",
    # Extraction
    "ExtractionEvaluator",
    "ExtractionItemResult",
    "ExtractionMetrics",
    "ExtractionEvaluationResult",
    # RAG
    "RAGEvaluator",
    "RAGItemResult",
    "RAGMetrics",
    "RAGEvaluationResult",
    # Runner
    "BatchEvaluationRunner",
    "RunnerResult",
]

__version__ = "0.1.0"

try:
    from .rag_response_evaluator import (
        CorrectnessScore,
        DEFAULT_PAIRWISE_SPEC,
        DEFAULT_SCORING_SPEC,
        PairwiseComparison,
        PairwiseRanking,
        PairwiseSpec,
        PairwiseVerdict,
        ProgressEvent,
        RAGPairwiseEvalResult,
        RAGResponseAggregate,
        RAGResponseEvalResult,
        RAGResponseEvaluator,
        ScoringSpec,
    )
    __all__ += [
        "RAGResponseEvaluator",
        "RAGResponseEvalResult",
        "RAGResponseAggregate",
        "ScoringSpec",
        "CorrectnessScore",
        "DEFAULT_SCORING_SPEC",
        "RAGPairwiseEvalResult",
        "PairwiseRanking",
        "PairwiseComparison",
        "PairwiseSpec",
        "PairwiseVerdict",
        "DEFAULT_PAIRWISE_SPEC",
        "ProgressEvent",
    ]
except ImportError:
    pass
