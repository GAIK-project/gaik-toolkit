"""Run the naive-vs-research-backed prompt comparison on JudgeBench.

This is the empirical companion to the prose claims in the LLM-as-judge
documentation: it loads ``ScalerLab/JudgeBench`` from HuggingFace
(open dataset, MIT licence, peer-reviewed paper), runs the same model
under two prompt variants — a naive 1-10 scoring prompt and the
research-backed Likert + CoT + bias-mitigation prompt — and reports
which one agrees with the dataset's ground-truth labels more often.

Usage::

    cd gaik-toolkit
    pip install -e ".[evaluators,llm-judge]"

    # Quick smoke (10 rows, ~$0.05)
    python implementation_layer/examples/software_components/validators/demo_judgebench_comparison.py --n 10

    # Full benchmark (50 rows, ~$0.20-0.30 with Gemini Flash)
    python implementation_layer/examples/software_components/validators/demo_judgebench_comparison.py --n 50 --out results/judgebench-comparison/

Provider env vars (only the ones for the chosen provider are required)::

    GOOGLE_VERTEXAI_PROJECT, GOOGLE_VERTEXAI_LOCATION, GOOGLE_APPLICATION_CREDENTIALS
    AZURE_API_KEY, AZURE_RESOURCE_NAME, AZURE_API_VERSION, AZURE_DEPLOYMENT
    ANTHROPIC_API_KEY (or Foundry: ANTHROPIC_FOUNDRY_RESOURCE)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--n", type=int, default=10, help="Number of rows to evaluate (default 10)")
    parser.add_argument(
        "--split",
        choices=["gpt", "claude"],
        default="gpt",
        help="JudgeBench split to use (gpt = 350 rows, claude = 270 rows)",
    )
    parser.add_argument(
        "--provider",
        default="google",
        choices=["openai", "azure", "anthropic", "google"],
        help="Judge provider (default google)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override the default model id for the chosen provider",
    )
    parser.add_argument(
        "--no-swap",
        action="store_true",
        help="Disable swap-and-average; halves the cost but loses position-bias check",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional output directory for leaderboard.md / summary.json / per-row dumps",
    )
    args = parser.parse_args()

    # Lazy import so --help works without the toolkit installed.
    from gaik.software_components.validators.llm_judge import (
        BenchmarkReport,
        JudgeBenchmark,
        report_to_dict,
    )

    print(f"Loading JudgeBench split={args.split} (n={args.n}) ...")
    rows, dataset_name, split = JudgeBenchmark.load_judgebench(n=args.n, split=args.split)
    print(f"Loaded {len(rows)} rows from {dataset_name}.")

    bench = JudgeBenchmark(model_provider=args.provider, model=args.model)
    print(f"Judge: {bench.model_provider}/{bench.model}")
    print(f"Swap-and-average: {not args.no_swap}")
    print(f"Prompts: naive (1-10) vs research-backed (Likert 1-5 + CoT + bias-mit)")
    print()

    report = bench.run(
        rows,
        prompts=("naive", "research"),
        swap_and_average=not args.no_swap,
        dataset_name=dataset_name,
        split=split,
    )

    _print_leaderboard(report)

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "summary.json").write_text(
            json.dumps(report_to_dict(report), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (args.out / "leaderboard.md").write_text(
            _leaderboard_md(report),
            encoding="utf-8",
        )
        print(f"\nWrote {args.out / 'leaderboard.md'} and {args.out / 'summary.json'}")

    return 0


def _print_leaderboard(report) -> None:
    print(f"\n=== JudgeBench comparison: {report.dataset} ({report.split}, n={report.n_rows}) ===")
    print(f"Model: {report.provider}/{report.model}")
    print(f"Swap-and-average: {report.swap_and_average}")
    print()
    header = f"{'Prompt':<10} {'Accuracy':>10} {'Position-bias':>15} {'Mean cost':>12} {'Mean latency':>14}"
    print(header)
    print("-" * len(header))
    for s in report.prompts:
        print(
            f"{s.prompt:<10} "
            f"{s.accuracy*100:>8.1f} % "
            f"{s.position_bias_rate*100:>13.1f} % "
            f"{s.mean_cost_usd:>10.4f} $ "
            f"{s.mean_duration_s:>12.2f} s"
        )
    print()
    for s in report.prompts:
        dist = ", ".join(f"{k}:{v}" for k, v in sorted(s.score_distribution.items()))
        print(f"  {s.prompt:<10} score histogram → {dist}")


def _leaderboard_md(report) -> str:
    lines = [
        f"# JudgeBench prompt comparison",
        "",
        f"- **Dataset**: [{report.dataset}](https://hf.co/datasets/{report.dataset}) (split `{report.split}`)",
        f"- **Rows**: {report.n_rows}",
        f"- **Judge**: `{report.provider}/{report.model}`",
        f"- **Position-bias mitigation**: swap-and-average = `{report.swap_and_average}`",
        "",
        "## Aggregate scores",
        "",
        "| Prompt | Accuracy | Position-bias flips | Ties | Mean cost (USD) | Mean latency (s) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for s in report.prompts:
        lines.append(
            f"| `{s.prompt}` | {s.accuracy*100:.1f}% | {s.position_bias_rate*100:.1f}% | "
            f"{s.ties} | {s.mean_cost_usd:.4f} | {s.mean_duration_s:.2f} |"
        )
    lines.append("")
    lines.append("## Score distribution (per response, summed across rows)")
    lines.append("")
    for s in report.prompts:
        dist = ", ".join(f"`{k}` × {v}" for k, v in sorted(s.score_distribution.items()))
        lines.append(f"- `{s.prompt}`: {dist}")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append(
        "- The naive prompt asks for a 1-10 score; LLMs tend to oversaturate at the high "
        "end of wide continuous scales, while integer Likert 1-5 forces discrimination."
    )
    lines.append(
        "- Position-bias rate is the fraction of rows where the predicted winner flipped "
        "when responses A and B were swapped. Lower is better."
    )
    lines.append(
        "- Accuracy is the fraction of rows where the predicted winner matched the "
        "ground-truth label after swap-and-averaging (ties count against accuracy)."
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
