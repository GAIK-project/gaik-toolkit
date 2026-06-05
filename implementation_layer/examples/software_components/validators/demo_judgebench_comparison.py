"""Naive vs research-backed prompt comparison on JudgeBench.

Why this script exists
----------------------
The toolkit's research-backed judge prompt (integer Likert + CoT +
bias-mitigation, following the HuggingFace LLM Judge cookbook) sits in
``gaik.software_components.validators.llm_judge``. Citing the literature
is not the same as proving the design was worth it. This script runs
the same model with two prompt variants — a naive ``"Score 1-10, pick
a winner"`` baseline and the research-backed prompt — on a public,
peer-reviewed pairwise dataset (``ScalerLab/JudgeBench``, MIT,
arXiv 2410.12784) and reports which one agrees with ground truth more
often.

The script is intentionally **a one-file research utility, not a public
API**. It lives under ``examples/`` rather than the package itself so
production users do not pull in the JudgeBench harness, the
``datasets`` dep, or the parallel text-only provider plumbing. Anyone
who wants to reproduce the empirical comparison can just run this
file. Anyone who wants to plug their own pairwise data through it can
copy and adapt it.

Usage::

    cd gaik-toolkit
    pip install -e ".[evaluators,llm-judge]"
    pip install "datasets>=2.14"   # script-level dep (NOT a toolkit extra)

    # Quick smoke (10 rows, ~$0.05)
    python implementation_layer/examples/software_components/validators/demo_judgebench_comparison.py --n 10

    # Full benchmark (50 rows, ~$0.20-0.30 with Gemini Flash)
    python implementation_layer/examples/software_components/validators/demo_judgebench_comparison.py \
        --n 50 --provider google \
        --out implementation_layer/examples/software_components/validators/judgebench-comparison/

Provider env vars (only those for the chosen provider are required)::

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
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ── Prompts ──────────────────────────────────────────────────────────

NAIVE_PAIRWISE_SYSTEM = """\
You are a judge. Read the question and the two candidate responses, then
score each on a scale of 1-10 and pick the winner.

Output JSON only, no prose, no markdown fences:
{"score_a": <int 1-10>, "score_b": <int 1-10>, "winner": "a" | "b" | "tie"}
"""


# Research-backed counterpart, mirroring the design of the toolkit's
# `validators.llm_judge.prompts.build_system_prompt` (vision-based) but
# adapted for text-pairwise inputs. References:
#   - HuggingFace LLM Judge cookbook: integer Likert > continuous floats
#   - arXiv 2411.15594 (Survey on LLM-as-a-Judge): anti-verbosity guidance
#   - "Justice or Prejudice" (OpenReview 2024): position-bias mitigation
#     (handled at the harness level via swap-and-average)
RESEARCH_PAIRWISE_SYSTEM = """\
You compare two candidate responses ("a" and "b") to the SAME question.
Decide which is more correct.

Quality rules:
  - Score on factual / logical correctness, not on phrasing, formatting,
    or response length. A concise correct answer beats a wordy one.
  - Stay grounded in the question and the visible content of the responses;
    do not bring in outside speculation.
  - Do not reward authority signals (confident tone, citations, lists) when
    the underlying claim is wrong.

Likert scale (per response, integer 1-5):
  1 — Critical mismatch: response is blatantly wrong or misses the question.
  2 — Significant error: an important step or fact is wrong.
  3 — Partial: some aspects right, some wrong, or answer ambiguous.
  4 — Mostly correct: minor formatting / notation difference; reasoning sound.
  5 — Perfect match: complete and correct answer.

For each judgement, FIRST write the reason describing what you compared
and saw, THEN assign the integer scores and the winner. This
evaluation-before-judgement ordering produces calibrated ratings instead
of snap decisions.

Output ONLY a JSON object, no prose, no markdown fences:
{
  "reason": "<≤30 words on the key difference>",
  "score_a": <integer 1-5>,
  "score_b": <integer 1-5>,
  "winner": "a" | "b" | "tie"
}
"""


def build_user_prompt(question: str, response_a: str, response_b: str) -> str:
    return (
        f"Question:\n{question.strip()}\n\n"
        f"Response A:\n{response_a.strip()}\n\n"
        f"Response B:\n{response_b.strip()}\n\n"
        "Now score each response and emit your JSON judgement."
    )


PromptVariant = Literal["naive", "research"]


# ── Result dataclasses ───────────────────────────────────────────────


@dataclass
class PairResult:
    pair_id: str
    prompt: PromptVariant
    predicted_winner: Literal["A>B", "B>A", "tie"]
    score_a: int
    score_b: int
    reason: str
    swap_consistent: bool
    raw_first: str
    raw_second: str | None
    input_tokens: int
    output_tokens: int
    duration_s: float
    cost_usd: float


@dataclass
class PromptScore:
    prompt: PromptVariant
    n: int = 0
    correct: int = 0
    ties: int = 0
    swap_inconsistent: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_duration_s: float = 0.0
    total_cost_usd: float = 0.0
    score_distribution: dict[int, int] = field(default_factory=dict)

    @property
    def accuracy(self) -> float:
        return self.correct / self.n if self.n else 0.0

    @property
    def position_bias_rate(self) -> float:
        return self.swap_inconsistent / self.n if self.n else 0.0

    @property
    def mean_cost_usd(self) -> float:
        return self.total_cost_usd / self.n if self.n else 0.0

    @property
    def mean_duration_s(self) -> float:
        return self.total_duration_s / self.n if self.n else 0.0


@dataclass
class BenchmarkReport:
    dataset: str
    split: str
    n_rows: int
    model: str
    provider: str
    swap_and_average: bool
    prompts: list[PromptScore]
    per_pair_results: list[PairResult]


# ── Pricing (subset; reuses toolkit's table) ──────────────────────────

# Per-million-token rates in USD. Scoped to the models the script runs;
# extend as needed.
_PRICING_PER_M: dict[str, tuple[float, float]] = {
    "gemini-3-flash-preview": (0.30, 2.50),
    "gemini-3.1-flash-lite-preview": (0.10, 0.40),
    "gpt-5.4-mini": (0.40, 1.60),
    "gpt-5.4": (1.25, 10.00),
    "gpt-5.5": (1.25, 10.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
}


def _cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    if model not in _PRICING_PER_M:
        return 0.0
    in_rate, out_rate = _PRICING_PER_M[model]
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000.0


# ── Harness ──────────────────────────────────────────────────────────


class JudgeBenchmarkHarness:
    """Compare prompt variants against a pairwise text dataset.

    Defined inline rather than imported so the script is self-contained.
    Reuses provider configuration helpers from the toolkit's
    multimodal_parser to avoid a parallel env-var contract.
    """

    DEFAULT_MODELS: dict[str, str] = {
        "openai": "gpt-5.4-mini",
        "azure": "gpt-5.4-mini",
        "anthropic": "claude-haiku-4-5-20251001",
        "google": "gemini-3-flash-preview",
    }

    def __init__(
        self,
        provider: Literal["openai", "azure", "anthropic", "google"] = "google",
        model: str | None = None,
        use_azure: bool = True,
        use_vertexai: bool = True,
        max_tokens: int = 2048,
        reasoning_effort: str | None = "low",
    ) -> None:
        if provider not in ("openai", "azure", "anthropic", "google"):
            raise ValueError(f"Unknown provider: {provider!r}")
        self.provider = provider
        self.model = model or self.DEFAULT_MODELS[provider]
        self.use_azure = use_azure
        self.use_vertexai = use_vertexai
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort

    # ── Public API ────────────────────────────────────────────────

    def run(
        self,
        rows: Iterable[dict],
        *,
        prompts: tuple[PromptVariant, ...] = ("naive", "research"),
        swap_and_average: bool = True,
        dataset_name: str = "<custom>",
        split: str = "<custom>",
    ) -> BenchmarkReport:
        scores: dict[PromptVariant, PromptScore] = {p: PromptScore(prompt=p) for p in prompts}
        per_pair: list[PairResult] = []

        rows_list = list(rows)
        for i, row in enumerate(rows_list):
            for prompt in prompts:
                logger.info(
                    "[%s/%s] %s prompt on %s",
                    i + 1,
                    len(rows_list),
                    prompt,
                    row.get("pair_id"),
                )
                result = self._judge_one(row, prompt, swap_and_average=swap_and_average)
                per_pair.append(result)
                _accumulate(scores[prompt], result, row["label"])

        return BenchmarkReport(
            dataset=dataset_name,
            split=split,
            n_rows=len(rows_list),
            model=self.model,
            provider=self.provider,
            swap_and_average=swap_and_average,
            prompts=list(scores.values()),
            per_pair_results=per_pair,
        )

    @classmethod
    def load_judgebench(
        cls,
        n: int = 50,
        split: Literal["gpt", "claude"] = "gpt",
        seed: int = 0,
    ) -> tuple[list[dict], str, str]:
        """Load *n* rows from ScalerLab/JudgeBench (MIT)."""
        try:
            from datasets import load_dataset
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "JudgeBench loader needs the 'datasets' package. "
                "Install with: pip install 'datasets>=2.14'"
            ) from exc

        ds = load_dataset("ScalerLab/JudgeBench", split=split)
        ds = ds.shuffle(seed=seed).select(range(min(n, len(ds))))
        rows: list[dict] = []
        for r in ds:
            rows.append(
                {
                    "pair_id": r["pair_id"],
                    "question": r["question"],
                    "response_a": r["response_A"],
                    "response_b": r["response_B"],
                    "label": r["label"],
                }
            )
        return rows, "ScalerLab/JudgeBench", split

    # ── Internal: one judge pass ──────────────────────────────────

    def _judge_one(
        self,
        row: dict,
        prompt: PromptVariant,
        *,
        swap_and_average: bool,
    ) -> PairResult:
        system = NAIVE_PAIRWISE_SYSTEM if prompt == "naive" else RESEARCH_PAIRWISE_SYSTEM

        raw1, in1, out1, dur1 = self._call(
            system,
            build_user_prompt(row["question"], row["response_a"], row["response_b"]),
        )
        winner1, sa1, sb1, reason1 = _parse(raw1)

        if not swap_and_average:
            return PairResult(
                pair_id=row["pair_id"],
                prompt=prompt,
                predicted_winner=_to_label(winner1),
                score_a=sa1,
                score_b=sb1,
                reason=reason1,
                swap_consistent=True,
                raw_first=raw1,
                raw_second=None,
                input_tokens=in1,
                output_tokens=out1,
                duration_s=dur1,
                cost_usd=_cost_usd(self.model, in1, out1),
            )

        raw2, in2, out2, dur2 = self._call(
            system,
            build_user_prompt(row["question"], row["response_b"], row["response_a"]),
        )
        winner_swapped, sa_swapped, sb_swapped, reason2 = _parse(raw2)
        winner2 = "b" if winner_swapped == "a" else "a" if winner_swapped == "b" else "tie"
        sa2, sb2 = sb_swapped, sa_swapped

        consistent = winner1 == winner2
        winner_final = winner1 if consistent else "tie"
        reason_final = (
            reason1 if consistent else f"Disagreement under swap: '{reason1}' vs '{reason2}'"
        )

        return PairResult(
            pair_id=row["pair_id"],
            prompt=prompt,
            predicted_winner=_to_label(winner_final),
            score_a=int(round((sa1 + sa2) / 2)),
            score_b=int(round((sb1 + sb2) / 2)),
            reason=reason_final,
            swap_consistent=consistent,
            raw_first=raw1,
            raw_second=raw2,
            input_tokens=in1 + in2,
            output_tokens=out1 + out2,
            duration_s=dur1 + dur2,
            cost_usd=_cost_usd(self.model, in1 + in2, out1 + out2),
        )

    def _call(self, system: str, user: str) -> tuple[str, int, int, float]:
        provider_call = {
            "openai": self._call_openai,
            "azure": self._call_openai,
            "anthropic": self._call_anthropic,
            "google": self._call_google,
        }[self.provider]
        t0 = time.perf_counter()
        text, in_tok, out_tok = provider_call(system, user)
        return text, in_tok, out_tok, time.perf_counter() - t0

    def _call_openai(self, system: str, user: str) -> tuple[str, int, int]:
        from gaik.software_components.parsers.multimodal_parser.config import (
            create_openai_client,
            get_openai_config,
        )

        client = create_openai_client(get_openai_config(use_azure=self.use_azure))
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_completion_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
        }
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort
        resp = client.chat.completions.create(**kwargs)
        text = resp.choices[0].message.content or ""
        usage = resp.usage
        return (
            text,
            getattr(usage, "prompt_tokens", 0) or 0,
            getattr(usage, "completion_tokens", 0) or 0,
        )

    def _call_anthropic(self, system: str, user: str) -> tuple[str, int, int]:
        from gaik.software_components.parsers.multimodal_parser.config import (
            create_claude_client,
            get_claude_config,
        )

        client = create_claude_client(get_claude_config(use_azure=self.use_azure))
        resp = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
        return text, resp.usage.input_tokens, resp.usage.output_tokens

    def _call_google(self, system: str, user: str) -> tuple[str, int, int]:
        from google import genai
        from google.genai import types

        if self.use_vertexai:
            client = genai.Client(
                vertexai=True,
                project=os.environ["GOOGLE_VERTEXAI_PROJECT"],
                location=os.environ.get("GOOGLE_VERTEXAI_LOCATION", "global"),
            )
        else:
            api_key = os.environ.get("GOOGLE_GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            if not api_key:
                raise RuntimeError("Set GOOGLE_VERTEXAI_PROJECT or GOOGLE_GEMINI_API_KEY")
            client = genai.Client(api_key=api_key)

        # Disable internal thinking so the prompt-design effect is what we measure
        thinking_config = types.ThinkingConfig(thinking_budget=0)
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            max_output_tokens=self.max_tokens,
            thinking_config=thinking_config,
        )
        resp = client.models.generate_content(
            model=self.model,
            contents=user,
            config=config,
        )
        text = resp.text or ""
        usage = resp.usage_metadata
        in_tok = getattr(usage, "prompt_token_count", 0) or 0
        out_tok = getattr(usage, "candidates_token_count", 0) or 0
        return text, in_tok, out_tok


# ── Helpers ──────────────────────────────────────────────────────────


def _parse(raw: str) -> tuple[Literal["a", "b", "tie"], int, int, str]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.lstrip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.rstrip("`").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Could not decode judge response: %s", text[:200])
        return ("tie", 0, 0, "")
    winner_raw = str(data.get("winner", "tie")).lower()
    if winner_raw not in ("a", "b", "tie"):
        winner_raw = "tie"
    winner: Literal["a", "b", "tie"] = winner_raw  # type: ignore[assignment]
    return (
        winner,
        _safe_int(data.get("score_a", 0)),
        _safe_int(data.get("score_b", 0)),
        str(data.get("reason", "")),
    )


def _safe_int(v: object) -> int:
    try:
        return int(round(float(v)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _to_label(winner: Literal["a", "b", "tie"]) -> Literal["A>B", "B>A", "tie"]:
    return {"a": "A>B", "b": "B>A", "tie": "tie"}[winner]


def _accumulate(score: PromptScore, result: PairResult, gold_label: str) -> None:
    score.n += 1
    if result.predicted_winner == gold_label:
        score.correct += 1
    if result.predicted_winner == "tie":
        score.ties += 1
    if not result.swap_consistent:
        score.swap_inconsistent += 1
    score.total_input_tokens += result.input_tokens
    score.total_output_tokens += result.output_tokens
    score.total_duration_s += result.duration_s
    score.total_cost_usd += result.cost_usd
    for s in (result.score_a, result.score_b):
        score.score_distribution[s] = score.score_distribution.get(s, 0) + 1


# ── CLI / reporting ──────────────────────────────────────────────────


def _print_leaderboard(report: BenchmarkReport) -> None:
    print(f"\n=== JudgeBench comparison: {report.dataset} ({report.split}, n={report.n_rows}) ===")
    print(f"Model: {report.provider}/{report.model}")
    print(f"Swap-and-average: {report.swap_and_average}\n")
    header = f"{'Prompt':<10} {'Accuracy':>10} {'Position-bias':>15} {'Mean cost':>12} {'Mean latency':>14}"
    print(header)
    print("-" * len(header))
    for s in report.prompts:
        print(
            f"{s.prompt:<10} "
            f"{s.accuracy * 100:>8.1f} % "
            f"{s.position_bias_rate * 100:>13.1f} % "
            f"{s.mean_cost_usd:>10.4f} $ "
            f"{s.mean_duration_s:>12.2f} s"
        )
    print()
    for s in report.prompts:
        dist = ", ".join(f"{k}:{v}" for k, v in sorted(s.score_distribution.items()))
        print(f"  {s.prompt:<10} score histogram → {dist}")


def _leaderboard_md(report: BenchmarkReport) -> str:
    lines = [
        "# JudgeBench prompt comparison",
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
            f"| `{s.prompt}` | {s.accuracy * 100:.1f}% | {s.position_bias_rate * 100:.1f}% | "
            f"{s.ties} | {s.mean_cost_usd:.4f} | {s.mean_duration_s:.2f} |"
        )
    lines.append("")
    lines.append("## Score distribution (per response, summed across rows)")
    lines.append("")
    for s in report.prompts:
        dist = ", ".join(f"`{k}` × {v}" for k, v in sorted(s.score_distribution.items()))
        lines.append(f"- `{s.prompt}`: {dist}")
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--n", type=int, default=10, help="Number of rows to evaluate (default 10)")
    parser.add_argument(
        "--split",
        choices=["gpt", "claude"],
        default="gpt",
        help="JudgeBench split (gpt = 350 rows, claude = 270 rows)",
    )
    parser.add_argument(
        "--provider",
        default="google",
        choices=["openai", "azure", "anthropic", "google"],
    )
    parser.add_argument("--model", default=None, help="Override default model id")
    parser.add_argument(
        "--no-swap",
        action="store_true",
        help="Disable swap-and-average; halves cost but loses position-bias check",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional output dir for leaderboard.md / summary.json",
    )
    args = parser.parse_args()

    print(f"Loading JudgeBench split={args.split} (n={args.n}) ...")
    rows, dataset_name, split = JudgeBenchmarkHarness.load_judgebench(n=args.n, split=args.split)
    print(f"Loaded {len(rows)} rows from {dataset_name}.")

    bench = JudgeBenchmarkHarness(provider=args.provider, model=args.model)
    print(f"Judge: {bench.provider}/{bench.model}")
    print(f"Swap-and-average: {not args.no_swap}")
    print("Prompts: naive (1-10) vs research-backed (Likert 1-5 + CoT + bias-mit)\n")

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
            json.dumps(asdict(report), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (args.out / "leaderboard.md").write_text(_leaderboard_md(report), encoding="utf-8")
        print(f"\nWrote {args.out / 'leaderboard.md'} and {args.out / 'summary.json'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
