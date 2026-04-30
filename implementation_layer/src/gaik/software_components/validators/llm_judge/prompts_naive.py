"""Naive vs research-backed prompt variants for the JudgeBenchmark harness.

The naive prompt is what most teams reach for first when they start using
"LLM-as-a-judge": ask for a 1-10 score, get a winner. It has no bias-
mitigation guidance, no explicit grounding rules, and no "evaluate first,
score second" Chain-of-Thought ordering. This module exposes the prompt
verbatim so the JudgeBenchmark can A/B-compare it against the research-
backed prompt that the rest of the toolkit uses.

Pair the prompts in this file with :class:`JudgeBenchmark.run_judgebench`
to measure how much the prompt-design choices in
:mod:`gaik.software_components.validators.llm_judge.prompts` are actually
worth on a public benchmark dataset.
"""

from __future__ import annotations

# ── Naive baseline (what people write before reading the research) ────

NAIVE_PAIRWISE_SYSTEM = """\
You are a judge. Read the question and the two candidate responses, then
score each on a scale of 1-10 and pick the winner.

Output JSON only, no prose, no markdown fences:
{"score_a": <int 1-10>, "score_b": <int 1-10>, "winner": "a" | "b" | "tie"}
"""


# ── Research-backed counterpart (Likert + bias-mit + CoT, text variant) ──
#
# This mirrors the design of pairwise._PAIRWISE_SYSTEM but is text-only
# (no document images) so it can be used on text-pairwise benchmarks like
# ScalerLab/JudgeBench. References:
#   - HuggingFace LLM Judge cookbook: integer Likert > continuous floats
#   - arXiv 2411.15594 (Survey on LLM-as-a-Judge): anti-verbosity guidance
#   - "Justice or Prejudice" (OpenReview 2024): position-bias mitigation
#     handled at the harness level via swap-and-average

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
    """Format a single pairwise comparison turn for the judge.

    Same shape regardless of prompt variant — only the system prompt
    changes between naive and research-backed runs.
    """
    return (
        f"Question:\n{question.strip()}\n\n"
        f"Response A:\n{response_a.strip()}\n\n"
        f"Response B:\n{response_b.strip()}\n\n"
        "Now score each response and emit your JSON judgement."
    )


__all__ = [
    "NAIVE_PAIRWISE_SYSTEM",
    "RESEARCH_PAIRWISE_SYSTEM",
    "build_user_prompt",
]
