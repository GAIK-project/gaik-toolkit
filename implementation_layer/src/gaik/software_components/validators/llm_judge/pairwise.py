"""Pairwise A-vs-B comparison with position-bias mitigation (swap-and-average).

Why this exists: GPT-4-class judges flip their decision ~40 % of the time
when answer order is swapped (Justice or Prejudice, OpenReview 2024). The
standard fix is to run the comparison twice (A vs B, then B vs A) and only
report a winner when both passes agree — otherwise mark it a tie.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Literal

from .llm_judge import LLMJudge, _strip_json_fences
from .pricing import compute_judge_cost_usd
from .schema import JudgeUsage, PairwiseResult

logger = logging.getLogger(__name__)


_PAIRWISE_SYSTEM = """\
You compare two extractor outputs ("a" and "b") against the SAME source
document images. Decide which is more faithful to the document.

Rules:
  - Score each side on factual correctness vs. the document, not phrasing,
    formatting, or length. A concise correct value beats a wordy one.
  - Stay grounded in the visible document evidence; do not speculate.

Likert scale (per side):
  1 — Critical mismatch with the document.
  3 — Partial / mixed match.
  5 — Perfect match.

Output ONLY a JSON object, no prose, no markdown fences:
{
  "winner": "a" | "b" | "tie",
  "score_a": <integer 1-5>,
  "score_b": <integer 1-5>,
  "reason": "<≤30 words explaining the key difference>"
}
"""


def compare_pairwise(
    judge: LLMJudge,
    source_pages: list[bytes],
    extracted_a: list[dict] | dict,
    extracted_b: list[dict] | dict,
    swap_and_average: bool = True,
) -> PairwiseResult:
    """Compare two extractor outputs side-by-side, mitigating position bias.

    Args:
        judge: The :class:`LLMJudge` to use for both passes.
        source_pages: PNG-encoded document images.
        extracted_a: First candidate output.
        extracted_b: Second candidate output.
        swap_and_average: When ``True`` (default), runs the comparison twice
            with A and B swapped and only reports a winner when both passes
            agree — otherwise the result is a tie. Doubles cost and latency.

    Returns:
        :class:`PairwiseResult` with winner, per-side scores, the reason,
        a ``swap_consistent`` flag, raw JSON from each pass, and
        per-pass usage records.
    """
    raw1, in1, out1, dur1 = _one_pass(judge, source_pages, extracted_a, extracted_b)
    winner1, sa1, sb1, reason1 = _parse_pairwise(raw1)
    usage_first = _usage_of(judge, in1, out1, dur1)

    if not swap_and_average:
        return PairwiseResult(
            winner=winner1,
            score_a=sa1,
            score_b=sb1,
            reason=reason1,
            swap_consistent=True,
            raw_first_pass=raw1,
            raw_second_pass=None,
            usage=[usage_first],
        )

    # Second pass with A and B swapped — then map results back to original frame.
    raw2, in2, out2, dur2 = _one_pass(judge, source_pages, extracted_b, extracted_a)
    winner_swapped, sa_swapped, sb_swapped, reason2 = _parse_pairwise(raw2)
    if winner_swapped == "a":
        winner2: Literal["a", "b", "tie"] = "b"
    elif winner_swapped == "b":
        winner2 = "a"
    else:
        winner2 = "tie"
    sa2, sb2 = sb_swapped, sa_swapped

    swap_consistent = winner1 == winner2
    if swap_consistent:
        winner: Literal["a", "b", "tie"] = winner1
        reason = reason1
    else:
        winner = "tie"
        reason = f"Disagreement under swap: '{reason1}' vs '{reason2}'"
        logger.info(
            "Pairwise comparison flipped under position swap (first=%s, second=%s) — reporting tie",
            winner1,
            winner2,
        )

    usage_second = _usage_of(judge, in2, out2, dur2)
    return PairwiseResult(
        winner=winner,
        score_a=int(round((sa1 + sa2) / 2)),
        score_b=int(round((sb1 + sb2) / 2)),
        reason=reason,
        swap_consistent=swap_consistent,
        raw_first_pass=raw1,
        raw_second_pass=raw2,
        usage=[usage_first, usage_second],
    )


def _one_pass(
    judge: LLMJudge,
    source_pages: list[bytes],
    extracted_a: list[dict] | dict,
    extracted_b: list[dict] | dict,
) -> tuple[str, int, int, float]:
    """Run one pairwise call. Reuses the judge's provider plumbing with a custom system prompt."""
    payload = json.dumps({"a": extracted_a, "b": extracted_b}, indent=2, ensure_ascii=False)
    user_prompt = (
        "Two extractor outputs to compare against the source document images.\n\n"
        f"```json\n{payload}\n```\n\n"
        "Now decide which is more faithful and emit your JSON judgement."
    )
    t0 = time.perf_counter()
    raw_text, in_tok, out_tok = judge._dispatch(source_pages, user_prompt, _PAIRWISE_SYSTEM)
    duration = time.perf_counter() - t0
    return raw_text, in_tok, out_tok, duration


def _parse_pairwise(raw: str) -> tuple[Literal["a", "b", "tie"], int, int, str]:
    text = _strip_json_fences(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Could not decode pairwise judge response; first 200 chars: %s", text[:200])
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


def _usage_of(judge: LLMJudge, in_tok: int, out_tok: int, duration: float) -> JudgeUsage:
    return JudgeUsage(
        provider=judge.model_provider,
        model=judge.model,
        input_tokens=in_tok,
        output_tokens=out_tok,
        total_tokens=in_tok + out_tok,
        duration_s=duration,
        cost_usd=compute_judge_cost_usd(judge.model, in_tok, out_tok),
    )
