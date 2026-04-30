"""Public-dataset benchmark harness for LLM-as-judge prompt comparison.

Why this exists
---------------
The rest of this package implements a research-backed judge prompt
(integer Likert + Chain-of-Thought ordering + bias-mitigation guidance,
following the HuggingFace LLM Judge cookbook). Citing the literature is
not the same as proving the design was worth it. This harness runs the
same model with two prompt variants — a naive ``"Score 1-10, pick a
winner"`` baseline and the research-backed prompt — on a public,
peer-reviewed dataset (`ScalerLab/JudgeBench
<https://hf.co/datasets/ScalerLab/JudgeBench>`_, MIT, arXiv 2410.12784)
and reports which one agrees with ground truth more often.

The harness is dataset-agnostic: any ``(question, response_a, response_b,
label)`` source can be plugged in. JudgeBench is just the default because
it is open, small enough to run cheaply (~$0.20 for 50 cases on Gemini
Flash), and has been used in published evaluations.

Output
------
Each ``run()`` produces a :class:`BenchmarkReport` with per-prompt
agreement-with-ground-truth, position-bias-flip rate, mean cost, mean
latency, and Likert-score distribution. The companion
``demo_judgebench_comparison.py`` writes the report as
``leaderboard.md`` + ``summary.json`` + per-row raw outputs.

What this is NOT
----------------
It is not vendor-specific (no client data here) and it is not a
substitute for the per-vendor calibration described in
:mod:`gaik.software_components.validators.llm_judge.calibration` —
calibration measures *judge vs human* agreement on your own data;
this harness measures *prompt design vs ground-truth* on a public
benchmark. They answer different questions.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Literal

from .pricing import compute_judge_cost_usd
from .prompts_naive import (
    NAIVE_PAIRWISE_SYSTEM,
    RESEARCH_PAIRWISE_SYSTEM,
    build_user_prompt,
)

logger = logging.getLogger(__name__)

PromptVariant = Literal["naive", "research"]
"""Which prompt template the harness should use for a given pass."""


# ── Result dataclasses ───────────────────────────────────────────────


@dataclass
class PairResult:
    """Outcome of a single (row × prompt) pass.

    ``predicted_winner`` is normalised to the same encoding as the
    dataset label (``"A>B"`` / ``"B>A"`` / ``"tie"``) so scoring logic
    can compare them directly.
    """

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
    """Aggregate stats for one prompt variant across all rows."""

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
    """Histogram of integer scores produced (key = score, value = count).
    Useful to show that naive 1-10 oversaturates at 8-10 while research
    Likert 1-5 spreads across the scale."""

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
    """Output of :meth:`JudgeBenchmark.run`. Serialisable via :func:`asdict`."""

    dataset: str
    split: str
    n_rows: int
    model: str
    provider: str
    swap_and_average: bool
    prompts: list[PromptScore]
    per_pair_results: list[PairResult]


# ── Harness ──────────────────────────────────────────────────────────


class JudgeBenchmark:
    """Compare prompt variants against a public pairwise-judgement dataset.

    Constructor arguments mirror :class:`LLMJudge` so consumers can swap
    judges easily. The harness does its own minimal text-only provider
    plumbing rather than going through ``LLMJudge.validate()`` because
    the latter requires page images.

    Args:
        model_provider: ``"openai"`` | ``"azure"`` | ``"anthropic"`` |
            ``"google"``. Default ``"google"`` (cheapest at scale).
        model: Model id (or Azure deployment name). Defaults to a
            sensible per-provider value.
        use_azure: Toggle Azure OpenAI vs OpenAI. Only meaningful when
            ``model_provider == "openai"``.
        use_vertexai: Toggle Vertex AI vs Generative Language API. Only
            meaningful when ``model_provider == "google"``.
        max_tokens: Output token cap. 256 is plenty for the JSON output.
        reasoning_effort: ``"low"`` / ``"medium"`` / ``"high"`` for
            reasoning models. Ignored otherwise. Defaults to ``"low"``
            so the prompt-design effect is not masked by extra thinking.
    """

    DEFAULT_MODELS: dict[str, str] = {
        "openai": "gpt-5.4-mini",
        "azure": "gpt-5.4-mini",
        "anthropic": "claude-haiku-4-5-20251001",
        "google": "gemini-3-flash-preview",
    }

    def __init__(
        self,
        model_provider: Literal["openai", "azure", "anthropic", "google"] = "google",
        model: str | None = None,
        use_azure: bool = True,
        use_vertexai: bool = True,
        max_tokens: int = 2048,
        reasoning_effort: str | None = "low",
    ) -> None:
        if model_provider not in ("openai", "azure", "anthropic", "google"):
            raise ValueError(
                f"Unknown model_provider: {model_provider!r}. "
                "Expected openai/azure/anthropic/google."
            )
        self.model_provider = model_provider
        self.model = model or self.DEFAULT_MODELS[model_provider]
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
        """Score *rows* under each prompt variant and return a report.

        Each row must look like::

            {
                "pair_id": "<unique id>",
                "question": "<text>",
                "response_a": "<text>",
                "response_b": "<text>",
                "label": "A>B" | "B>A",
            }

        The harness will call the model once (or twice with swap) per
        ``(row, prompt)`` combination.
        """
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
            provider=self.model_provider,
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
        """Load the first *n* rows from ``ScalerLab/JudgeBench`` (MIT).

        Returns ``(rows, dataset_name, split)``. Lazy-imports ``datasets``
        so callers without ``gaik[evaluators]`` get a clear error.
        """
        try:
            from datasets import load_dataset
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "JudgeBench loader needs the 'datasets' package. "
                "Install with: pip install 'gaik[evaluators]' "
                "or `pip install datasets>=2.14`."
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

        # Pass 1 — A in slot A, B in slot B
        raw1, in1, out1, dur1 = self._call(
            system,
            build_user_prompt(row["question"], row["response_a"], row["response_b"]),
        )
        winner1, sa1, sb1, reason1 = _parse(raw1)

        if not swap_and_average:
            predicted = _to_label(winner1)
            return PairResult(
                pair_id=row["pair_id"],
                prompt=prompt,
                predicted_winner=predicted,
                score_a=sa1,
                score_b=sb1,
                reason=reason1,
                swap_consistent=True,
                raw_first=raw1,
                raw_second=None,
                input_tokens=in1,
                output_tokens=out1,
                duration_s=dur1,
                cost_usd=compute_judge_cost_usd(self.model, in1, out1),
            )

        # Pass 2 — A and B swapped; map result back to the original frame
        raw2, in2, out2, dur2 = self._call(
            system,
            build_user_prompt(row["question"], row["response_b"], row["response_a"]),
        )
        winner_swapped, sa_swapped, sb_swapped, reason2 = _parse(raw2)
        winner2 = (
            "b" if winner_swapped == "a" else "a" if winner_swapped == "b" else "tie"
        )
        sa2, sb2 = sb_swapped, sa_swapped

        consistent = winner1 == winner2
        if consistent:
            winner_final = winner1
            reason_final = reason1
        else:
            winner_final = "tie"
            reason_final = f"Disagreement under swap: '{reason1}' vs '{reason2}'"

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
            cost_usd=compute_judge_cost_usd(self.model, in1 + in2, out1 + out2),
        )

    def _call(self, system: str, user: str) -> tuple[str, int, int, float]:
        """Dispatch to the correct provider with text-only payload."""
        provider_call = {
            "openai": self._call_openai,
            "azure": self._call_openai,
            "anthropic": self._call_anthropic,
            "google": self._call_google,
        }[self.model_provider]
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
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        )
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
            api_key = os.environ.get("GOOGLE_GEMINI_API_KEY") or os.environ.get(
                "GOOGLE_API_KEY"
            )
            if not api_key:
                raise RuntimeError(
                    "Set GOOGLE_VERTEXAI_PROJECT or GOOGLE_GEMINI_API_KEY"
                )
            client = genai.Client(api_key=api_key)

        # Gemini 3 family enables internal "thinking" by default which
        # eats the response token budget on long inputs. The benchmark
        # wants the prompt-design effect to be the variable; cap thinking
        # at minimum so we measure what the prompt actually elicits.
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


def report_to_dict(report: BenchmarkReport) -> dict:
    """Convenience for JSON serialisation. Pure-stdlib dataclass walk."""
    return asdict(report)


__all__ = [
    "JudgeBenchmark",
    "BenchmarkReport",
    "PromptScore",
    "PairResult",
    "PromptVariant",
    "report_to_dict",
]
