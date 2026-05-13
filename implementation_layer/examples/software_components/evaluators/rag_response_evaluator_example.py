"""RAGResponseEvaluator demo — referenced + pairwise modes on synthetic data.

Runs two evaluations against synthetic RAG outputs:

1. **Referenced**: scores each candidate column against a reference answer on
   the default 4+1 rubric (coverage, contradiction, relevance, precision,
   overall) and saves a scored CSV + plots.
2. **Pairwise**: drops the reference column and judges every C(N,2) pair of
   candidates per question, pools wins, and reports a system ranking.

Configure your provider via standard GAIK env vars (Azure shown here):

    AZURE_API_KEY=...
    AZURE_ENDPOINT=https://...openai.azure.com/
    AZURE_DEPLOYMENT=gpt-5.1
    AZURE_API_VERSION=2025-03-01-preview
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.evaluators import (  # noqa: E402
    ProgressEvent,
    RAGResponseEvaluator,
)


SAMPLE_DF = pd.DataFrame(
    [
        {
            "question": "What are the standard working hours for full-time employees in Finland?",
            "reference": (
                "Standard regular working hours are 8 hours per day and 40 hours per week. "
                "Collective agreements may set lower limits, commonly 7.5 hours per day."
            ),
            "concise_rag_response": (
                "Full-time work in Finland is normally 8 hours per day and 40 hours per week. "
                "Collective agreements often reduce this to 7.5 hours per day."
            ),
            "vague_rag_response": (
                "Employees in Finland typically work a normal workweek, but the exact number "
                "of hours depends on the situation and agreement."
            ),
            "wrong_rag_response": (
                "Full-time employees in Finland work 6 hours per day, 30 hours per week. "
                "There are no collective agreement variations."
            ),
        },
        {
            "question": "How much annual leave does a Finnish employee accrue after one full year of service?",
            "reference": (
                "Under the Annual Holidays Act, an employee with at least one year of "
                "continuous service accrues 2.5 weekday holidays per accrual month, "
                "i.e. 30 weekday holidays per full holiday year."
            ),
            "concise_rag_response": (
                "After one year of service, employees accrue 2.5 weekday holidays per accrual "
                "month, totalling 30 weekday holidays per holiday year."
            ),
            "vague_rag_response": (
                "Employees in Finland get a reasonable amount of holiday after working for a "
                "year, generally several weeks."
            ),
            "wrong_rag_response": (
                "After one year of service, employees get 2 weekday holidays per month, "
                "or 20 weekday holidays a year."
            ),
        },
        {
            "question": "What is the statutory notice period when an employer terminates a contract of an employee with 8 years of service?",
            "reference": (
                "Under the Employment Contracts Act, when the employer terminates the contract "
                "of an employee with 4-8 years of continuous service, the notice period is "
                "4 months. For 8-12 years it is 5 months."
            ),
            "concise_rag_response": (
                "For 8 years of continuous service, the employer's notice period is 5 months "
                "under the Employment Contracts Act."
            ),
            "vague_rag_response": (
                "There is a notice period that depends on how long the employee has worked; "
                "longer service means a longer notice period."
            ),
            "wrong_rag_response": (
                "The employer's notice period for 8 years of service is 2 weeks."
            ),
        },
    ]
)


def _progress(ev: ProgressEvent) -> None:
    print(f"  [{ev.mode}] {ev.done}/{ev.total}  ({ev.elapsed_s:.1f}s)")


def main() -> None:
    evaluator = RAGResponseEvaluator(max_concurrency=3)

    # --- Referenced mode --------------------------------------------------
    print("\n=== Referenced mode ===")
    result = evaluator.evaluate(SAMPLE_DF, on_progress=_progress)

    print("\nPer-system aggregates:")
    for agg in result.per_system:
        print(
            f"  {agg.system}: n={agg.n}  composite={agg.composite:.3f}  "
            f"divergence={agg.divergence:.3f}  violations={agg.constraint_violations}"
        )
        for k, v in agg.norms.items():
            print(f"    {k:<24}  norm={v:.3f}  mean={agg.means[k]:.2f}")

    with tempfile.TemporaryDirectory() as tmp:
        evaluator.save(result, tmp)
        print(f"\nReferenced outputs written to: {tmp}")
        for p in sorted(Path(tmp).iterdir()):
            print(f"  {p.name}  ({p.stat().st_size} bytes)")

    # --- Pairwise mode ----------------------------------------------------
    print("\n=== Pairwise mode (reference dropped) ===")
    pairwise_df = SAMPLE_DF.drop(columns=["reference"])
    p_result = evaluator.evaluate_pairwise(
        pairwise_df,
        swap_and_average=True,
        on_progress=_progress,
        random_seed=42,
    )

    print("\nRanking:")
    for r in p_result.ranking:
        print(
            f"  rank={r.rank}  {r.system}: wins={r.wins}/{r.losses}/{r.ties} (W/L/T)  "
            f"win_rate={r.win_rate:.2f}"
        )
        for k, v in r.aspect_means.items():
            print(f"    {k:<14}  mean={v:.2f}/5")

    with tempfile.TemporaryDirectory() as tmp:
        evaluator.save(p_result, tmp)
        print(f"\nPairwise outputs written to: {tmp}")
        for p in sorted(Path(tmp).iterdir()):
            print(f"  {p.name}  ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
