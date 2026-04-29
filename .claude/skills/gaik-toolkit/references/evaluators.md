# Evaluators API Reference

Reusable evaluation suite for GAIK pipelines. Built on top of LLMJudge v2 so
LLM-graded metrics share the same Likert / panel / few-shot machinery.

**Source:** `gaik.software_components.evaluators`
**Install:** `pip install "gaik[evaluators]"` (pulls `gaik[llm-judge]`).

## Contents

- [EvaluationDataset / EvaluationItem](#evaluationdataset--evaluationitem) — IO format
- [ExtractionEvaluator](#extractionevaluator) — field-level P/R/F1 + hallucination rate
- [RAGEvaluator](#ragevaluator) — RAGAS-style metrics via LLMJudge
- [BatchEvaluationRunner](#batchevaluationrunner) — pipeline glue

---

## EvaluationDataset / EvaluationItem

```python
from gaik.software_components.evaluators import (
    EvaluationDataset, EvaluationItem,
)

dataset = EvaluationDataset.from_jsonl("eval/data.jsonl")
dataset = EvaluationDataset.from_csv("eval/data.csv")
dataset = EvaluationDataset.from_list([
    {"input": "doc-1.pdf", "expected": {"vendor": "Acme"}},
])
```

`EvaluationItem` fields: `input` (required), `expected`, `context`, `metadata`.
JSONL rows / CSV columns map straight onto these.

---

## ExtractionEvaluator

Field-level Precision / Recall / F1 + hallucination rate over an expected
vs. extracted dict pair.

```python
from gaik.software_components.evaluators import ExtractionEvaluator

evaluator = ExtractionEvaluator(match_mode="exact")  # or "semantic" with judge=
result = evaluator.evaluate_dataset(dataset, extracted_outputs)
print(result.aggregate)  # ExtractionMetrics(P=, R=, F1=, hallucination=...)
for r in result.per_item:
    for v in r.verdicts:  # FieldVerdict
        ...
```

Modes:
- `"exact"` (default) — strip + casefold then equality. No LLM cost.
- `"semantic"` — Likert 1-5 LLM grading; `score >= 4` counts as a match.
  Requires `judge=LLMJudge(...)`.

Aggregation is **micro-averaged** across fields (sum correct / sum extracted).

---

## RAGEvaluator

RAGAS-style metrics via LLMJudge. Each metric on a 1-5 Likert scale,
aggregated to 0-1.

```python
from gaik.software_components.evaluators import RAGEvaluator
from gaik.software_components.validators import LLMJudge

evaluator = RAGEvaluator(judge=LLMJudge(model_provider="google"))
result = evaluator.evaluate_dataset([
    {"query": "...", "answer": "...", "context": [...], "ground_truth": "..."},
])
print(result.aggregate)
# RAGMetrics(faithfulness=0.93, answer_relevance=0.95,
#            context_precision=0.88, context_recall=0.90)
```

| Metric | Question |
|---|---|
| `faithfulness` | Does the answer stay grounded in retrieved context? |
| `answer_relevance` | Does the answer address the user's question? |
| `context_precision` | Were retrieved passages relevant (low noise)? |
| `context_recall` | Does context cover the ground-truth answer? |

`context_recall` skipped when `ground_truth` is missing
(`skip_context_recall=True` default).

---

## BatchEvaluationRunner

Generic pipeline → outputs runner. Hand a callable
`pipeline: EvaluationItem -> Any` and a dataset.

```python
from gaik.software_components.evaluators import BatchEvaluationRunner

def pipeline(item):
    return DataExtractor(...).extract(item.input, schema=...).fields

runner = BatchEvaluationRunner(pipeline, on_error="skip")
runner_result = runner.run(dataset)
eval_result = ExtractionEvaluator().evaluate_dataset(dataset, runner_result.outputs)
```

`on_error="skip"` records failures in `RunnerResult.failures` instead of
re-raising.

---

## Import Patterns

```python
# Top-level convenience imports — all listed in evaluators/__init__.py
from gaik.software_components.evaluators import (
    EvaluationDataset, EvaluationItem,
    ExtractionEvaluator, ExtractionMetrics, ExtractionEvaluationResult,
    RAGEvaluator, RAGMetrics, RAGEvaluationResult,
    BatchEvaluationRunner, RunnerResult,
)
```

## Examples

- `implementation_layer/examples/software_components/evaluators/extraction_evaluator_example.py`
- `implementation_layer/examples/software_components/evaluators/rag_evaluator_example.py`
