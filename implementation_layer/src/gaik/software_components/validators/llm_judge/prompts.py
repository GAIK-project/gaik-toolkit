"""System and user prompts for the LLM-as-judge validator.

Layout follows the 2026 LLM-as-judge research consensus:
- HuggingFace cookbook (https://huggingface.co/learn/cookbook/llm_judge):
  integer Likert 1-5 outperforms float scales by ~30 % on human-correlation;
  CoT order ("evaluate first, score second") raises correlation further.
- arXiv 2411.15594 (Survey on LLM-as-a-Judge): explicit conciseness/anti-
  verbosity guidance reduces verbosity bias.
- arXiv 2510.12462 (Evaluating and Mitigating LLM-as-a-judge Bias): focus
  the judge on factual correctness, not surface form.
"""

from __future__ import annotations

import json

from .schema import FewShotExample, ScoringMode, ValidationFlag, ValidationRubric

_BIAS_GUIDANCE = """
Quality rules:
  - Score on factual correctness against the document, not on phrasing,
    formatting, or value length.
  - Do not reward verbosity: a concise correct value beats a wordy one.
  - Stay grounded in the visible document evidence; do not speculate.
"""

_SEVERITY_SCALE = """
Severity:
  - "ok"      — value matches the document
  - "suspect" — value seems unlikely or partially wrong
  - "wrong"   — value clearly contradicts the document or a required value is empty
"""

_LIKERT_SCALE = """
Likert score (integer 1-5):
  1 — Critical mismatch: value blatantly contradicts the document.
  2 — Significant error: an important detail is wrong or required value missing.
  3 — Partial: some aspects right, some wrong, or value ambiguous.
  4 — Mostly correct: minor formatting / notation difference; semantics match.
  5 — Perfect match: no observable difference.

The severity must be consistent with the score:
  score 1     -> "wrong"
  score 2-3   -> "suspect"
  score 4-5   -> "ok"
"""

_ADDITIVE_SCALE = """
Additive Likert score (integer 1-5):
  Award 1 point for each evaluation aspect (see "Focus your evaluation on
  these aspects:" in the user prompt) that is fully satisfied for the field.
  The total is the score, capped at 5. If no aspects are listed, fall back
  to the standard 1-5 Likert scale described above.
"""

_BASE_SYSTEM = """\
You are a quality validator for structured extraction. You receive:
1. One or more page images from a source document.
2. A JSON snapshot of what an upstream extractor produced from that document.

Your job: identify fields whose value in the JSON does NOT match the document.
"""

_OUTPUT_FORMAT_SEVERITY = """
For every field you can verify against the images, output one entry. For each
"wrong" or "suspect" entry, include a short reason (≤25 words) and, where you
can read it from the document, a suggested_value.

If items are MISSING from the JSON that you can see in the document, emit a
document-level entry with item_index=-1, field="_document.item_count", and
suggested_value = the count you observe in the document.

For each flag, FIRST write the reason describing what you compared and saw,
THEN assign the severity. This evaluation-before-judgement order avoids
snap decisions.

Respond with ONLY a JSON object, no prose, no markdown fences:
{
  "flags": [
    {"item_index": 0, "field": "quantity", "severity": "wrong",
     "reason": "Document shows 4279 LB but JSON says 940",
     "suggested_value": "4279"},
    ...
  ]
}
"""

_OUTPUT_FORMAT_LIKERT = """
For every field you can verify against the images, output one entry. For each
"wrong" or "suspect" entry, include a short reason (≤25 words) and, where you
can read it from the document, a suggested_value.

If items are MISSING from the JSON that you can see in the document, emit a
document-level entry with item_index=-1, field="_document.item_count", and
suggested_value = the count you observe in the document.

For each flag, FIRST write the reason (one sentence describing what you
compared and saw), THEN assign the score (1-5 integer) and severity. The
score MUST be between 1 and 5. This evaluation-before-judgement order
produces calibrated ratings.

Respond with ONLY a JSON object, no prose, no markdown fences:
{
  "flags": [
    {"item_index": 0, "field": "quantity", "severity": "wrong", "score": 1,
     "reason": "Document shows 4279 LB but JSON says 940",
     "suggested_value": "4279"},
    ...
  ]
}
"""


def build_system_prompt(scoring_mode: ScoringMode = "severity") -> str:
    """Return the system prompt tailored to *scoring_mode*."""
    if scoring_mode == "likert_1_5":
        return f"{_BASE_SYSTEM}{_BIAS_GUIDANCE}{_SEVERITY_SCALE}{_LIKERT_SCALE}{_OUTPUT_FORMAT_LIKERT}"
    if scoring_mode == "additive":
        return f"{_BASE_SYSTEM}{_BIAS_GUIDANCE}{_SEVERITY_SCALE}{_ADDITIVE_SCALE}{_OUTPUT_FORMAT_LIKERT}"
    return f"{_BASE_SYSTEM}{_BIAS_GUIDANCE}{_SEVERITY_SCALE}{_OUTPUT_FORMAT_SEVERITY}"


JUDGE_SYSTEM_PROMPT = build_system_prompt("severity")
"""Backward-compatible default system prompt (severity mode)."""


def _flag_dict(flag: ValidationFlag) -> dict:
    out: dict = {
        "item_index": flag.item_index,
        "field": flag.field,
        "severity": flag.severity,
        "reason": flag.reason,
    }
    if flag.score:
        out["score"] = flag.score
    if flag.suggested_value is not None:
        out["suggested_value"] = flag.suggested_value
    return out


def _render_few_shot_block(examples: list[FewShotExample]) -> str:
    if not examples:
        return ""
    blocks = ["Reference examples (use these to calibrate your judgements):"]
    for i, ex in enumerate(examples, start=1):
        extracted_json = json.dumps(ex.extracted, indent=2, ensure_ascii=False)
        flags_json = json.dumps(
            {"flags": [_flag_dict(f) for f in ex.expected_flags]},
            indent=2,
            ensure_ascii=False,
        )
        label = f" — {ex.description}" if ex.description else ""
        blocks.append(f"\nExample {i}{label}")
        blocks.append("Extractor output:")
        blocks.append(f"```json\n{extracted_json}\n```")
        blocks.append("Expected flags:")
        blocks.append(f"```json\n{flags_json}\n```")
    return "\n".join(blocks)


def build_user_prompt(extracted: list[dict] | dict, rubric: ValidationRubric | None) -> str:
    """Assemble the per-call user-side prompt block.

    The extracted JSON is shown verbatim. The rubric, if any, is rendered as
    bulleted check lists so the model can use them as a checklist. Few-shot
    examples and per-aspect focus lists are included when present.
    """
    rubric = rubric or ValidationRubric()

    lines: list[str] = []
    if rubric.vendor_id:
        lines.append(f"Vendor: {rubric.vendor_id}")
    if rubric.evaluation_aspects:
        lines.append("\nFocus your evaluation on these aspects:")
        lines.extend(f"  - {aspect}" for aspect in rubric.evaluation_aspects)
    if rubric.field_checks:
        lines.append("\nField-level checks:")
        lines.extend(f"  - {check}" for check in rubric.field_checks)
    if rubric.item_level_checks:
        lines.append("\nItem-level / document-level checks:")
        lines.extend(f"  - {check}" for check in rubric.item_level_checks)
    if rubric.custom_system_suffix:
        lines.append("\n" + rubric.custom_system_suffix)

    rubric_block = "\n".join(lines).strip()
    fewshot_block = _render_few_shot_block(rubric.few_shot_examples)
    extracted_json = json.dumps(extracted, indent=2, ensure_ascii=False)

    body: list[str] = []
    if rubric_block:
        body.append(rubric_block)
    if fewshot_block:
        body.append("\n" + fewshot_block)
    body.append("\nExtractor output (JSON):")
    body.append(f"```json\n{extracted_json}\n```")
    body.append("\nNow compare against the page images and emit your flags.")
    return "\n".join(body)
