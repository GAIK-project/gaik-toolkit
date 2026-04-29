"""ExtractionEvaluator demo — field-level Precision / Recall / F1 + hallucination rate.

This example doesn't hit any LLM provider — it runs entirely on synthetic
ground-truth and "extractor output" dicts so it can be smoke-tested in CI.

For real-world usage, plug ``DataExtractor.extract()`` into the
:class:`BatchEvaluationRunner` pipeline and pass its outputs to
``evaluator.evaluate_dataset(...)``.
"""

from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.evaluators import (  # noqa: E402
    BatchEvaluationRunner,
    EvaluationDataset,
    ExtractionEvaluator,
)


def main() -> None:
    # 5 hand-curated test cases — tiny but representative.
    dataset = EvaluationDataset.from_list(
        [
            {
                "input": "invoice-001.pdf",
                "expected": {
                    "vendor": "Acme",
                    "amount_eur": "1200.00",
                    "due_date": "2026-05-15",
                },
            },
            {
                "input": "invoice-002.pdf",
                "expected": {
                    "vendor": "Beta Oy",
                    "amount_eur": "850.50",
                    "due_date": "2026-05-20",
                },
            },
            {
                "input": "invoice-003.pdf",
                "expected": {
                    "vendor": "Cee Co",
                    "amount_eur": "2500.00",
                    "due_date": "2026-05-25",
                },
            },
        ]
    )

    # Pretend the extractor produced these outputs (one row per dataset item).
    extracted_outputs = [
        # Item 0: perfect
        {"vendor": "Acme", "amount_eur": "1200.00", "due_date": "2026-05-15"},
        # Item 1: amount wrong + extra hallucinated field
        {
            "vendor": "Beta Oy",
            "amount_eur": "85.50",
            "due_date": "2026-05-20",
            "iban": "FI21 1234 5600 0007 85",
        },
        # Item 2: missing due_date
        {"vendor": "Cee Co", "amount_eur": "2500.00"},
    ]

    evaluator = ExtractionEvaluator(match_mode="exact")
    result = evaluator.evaluate_dataset(dataset, extracted_outputs)

    print("=== Per-item ===\n")
    for i, r in enumerate(result.per_item):
        print(f"Item {i}: {r.metrics}")
        for v in r.verdicts:
            tag = (
                "OK   "
                if v.matched
                else "MISS "
                if v.is_missing
                else "HALLU"
                if v.is_hallucination
                else "WRONG"
            )
            print(
                f"  [{tag}] {v.field}: expected={v.expected!r}  extracted={v.extracted!r}"
            )
        print()

    print("=== Aggregate ===")
    print(result.aggregate)


def runner_example() -> None:
    """Show how the BatchEvaluationRunner glues a pipeline to the evaluator."""
    from gaik.software_components.evaluators import BatchEvaluationRunner

    dataset = EvaluationDataset.from_list(
        [
            {"input": "doc-A", "expected": {"x": "1"}},
            {"input": "doc-B", "expected": {"x": "2"}},
        ]
    )

    # Real-world pipeline would be e.g.:
    #     def pipeline(item):
    #         return DataExtractor(...).extract(item.input, schema=...).fields
    def fake_pipeline(item):
        # Toy "extractor" that gets it right half the time.
        return {"x": "1"}

    runner = BatchEvaluationRunner(fake_pipeline)
    runner_result = runner.run(dataset)
    print(
        f"\nRunner: {len(runner_result.outputs)} outputs, "
        f"{runner_result.total_duration_s:.3f}s total, "
        f"{runner_result.n_failures} failures"
    )

    eval_result = ExtractionEvaluator().evaluate_dataset(dataset, runner_result.outputs)
    print("Pipeline aggregate:", eval_result.aggregate)


if __name__ == "__main__":
    main()
    runner_example()
