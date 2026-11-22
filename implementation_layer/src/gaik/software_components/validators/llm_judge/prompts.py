"""System and user prompts for the LLM-as-judge validator.

Layout follows the 2026 LLM-as-judge research consensus:
- HuggingFace cookbook (https://huggingface.co/learn/cookbook/llm_judge):
  integer Likert 1-5 outperforms float scales by ~30 % on human-correlation;
  CoT order ("evaluate first, score second") raises correlation further.
- arXiv 2411.15594 (Survey on LLM-as-a-Judge): explicit conciseness/anti-
  verbosity guidance reduces verbosity bias.
- arXiv 2510.12462 (Evaluating and Mitigating LLM-as-a-judge Bias): focus
  the judge on factual correctness, not surface form.

The judged content (the extractor output, the source text, the answer, the
reference and any context) goes only in the user message, each piece in its own
labelled block from :class:`~gaik.software_components.source_material.SourceMaterial`;
the rubric, the scales and the output format stay in the system message with
:data:`~gaik.software_components.source_material.SOURCE_MATERIAL_INSTRUCTION`, so
text in the judged content reads as data to assess, not as instructions to the judge.
"""

from __future__ import annotations

import json

from gaik.software_components.source_material import (
    SourceMaterial,
    with_source_material_instruction,
)

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
  these aspects:" in the rubric) that is fully satisfied for the field.
  The total is the score, capped at 5. If no aspects are listed, fall back
  to the standard 1-5 Likert scale described above.
"""

_BASE_SYSTEM = """\
You are a quality validator for structured extraction. You receive:
1. One or more page images from a source document.
2. A JSON snapshot of what an upstream extractor produced from that document,
   in the source material block labelled "answer".

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


def build_system_prompt(
    scoring_mode: ScoringMode = "severity",
    *,
    rubric: ValidationRubric | None = None,
) -> str:
    """Return the system prompt tailored to *scoring_mode*.

    The prompt ends with the source-material sentence. When ``rubric`` is
    given, its vendor, aspects, checks, suffix and few-shot examples follow
    it: they are the caller's instructions, so they belong here and not next
    to the judged output.
    """
    head = f"{_BASE_SYSTEM}{_BIAS_GUIDANCE}{_SEVERITY_SCALE}"
    if scoring_mode == "likert_1_5":
        prompt = f"{head}{_LIKERT_SCALE}{_OUTPUT_FORMAT_LIKERT}"
    elif scoring_mode == "additive":
        prompt = f"{head}{_ADDITIVE_SCALE}{_OUTPUT_FORMAT_LIKERT}"
    else:
        prompt = f"{head}{_OUTPUT_FORMAT_SEVERITY}"
    prompt = with_source_material_instruction(prompt)
    rubric_text = _render_rubric(rubric) if rubric is not None else ""
    return f"{prompt}\n\n{rubric_text}" if rubric_text else prompt


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


_TEXT_PAIR_SYSTEM = """\
You compare two short text values for semantic equivalence.

The EXTRACTED value is in the source material block labelled "answer", the
EXPECTED value in the block labelled "reference", and optional surrounding
text in the block labelled "context".

Decide whether the EXTRACTED value carries the same factual information
as the EXPECTED value, ignoring:
  - whitespace, casing, punctuation
  - morphological forms (Finnish noun cases, conjugation, etc.)
  - paraphrasing of the same fact
  - reasonable synonyms in the relevant domain

Mark them as NOT equivalent if:
  - the extracted text adds claims not in expected (or vice versa)
  - they refer to different entities, dates, quantities, or actions
  - one is empty and the other is not

Severity:
  - "ok"      — same fact, possibly different wording (score 4-5)
  - "suspect" — partial overlap, ambiguous, or one detail off (score 2-3)
  - "wrong"   — clear factual divergence or one side empty (score 1)

Likert score (integer 1-5):
  1 — Clear divergence (different fact, different entity, or empty vs non-empty).
  2 — Significant difference (overlapping topic but key detail wrong).
  3 — Partial / ambiguous.
  4 — Same fact, minor formatting or wording difference.
  5 — Identical meaning.

FIRST write the reason describing what you compared and saw, THEN assign
the score and severity. This evaluation-before-judgement order produces
calibrated ratings.

Respond with ONLY a JSON object (no prose, no markdown fences):
{
  "equivalent": true|false,
  "severity": "ok|suspect|wrong",
  "score": 1-5,
  "reason": "one short sentence (<=20 words)"
}
"""

TEXT_PAIR_SYSTEM_PROMPT = with_source_material_instruction(_TEXT_PAIR_SYSTEM)
"""System prompt for :meth:`LLMJudge.judge_text_pair`, with the source-material sentence."""


_HALLUCINATION_SYSTEM = """\
You are a hallucination detector for a structured-extraction output.

Given:
  1. A SOURCE document (e.g. an audio transcript or parsed text), in the
     source material block labelled "source".
  2. A JSON object with fields the upstream extractor produced, in the
     block labelled "answer".

Identify any field whose VALUE is NOT directly supported by the source.

A field is a hallucination when its value contains a fact, name, date,
quantity, label, or claim that the source does not state. Inferences
from domain context, default guesses, or "most likely" enum picks are
hallucinations.

A field is NOT a hallucination when:
  - the source explicitly states the same fact (even paraphrased)
  - the value is an empty string ""  (empty is never a hallucination)
  - the field is a soft default that matches the field's documented
    fallback rule (when the caller supplies one in the field hints)

For each flagged field, output:
  - "field":    the exact JSON key
  - "value":    the extracted value (string-rendered)
  - "severity": "wrong" (clearly hallucinated) or "suspect" (probably
                hallucinated but the source is partially ambiguous)
  - "reason":   why the value is unsupported, ≤25 words

FIRST list the reason describing what you compared and saw, THEN assign
the severity. This evaluation-before-judgement order avoids snap calls.

Respond with ONLY a JSON object, no prose, no markdown fences:
{
  "flags": [
    {"field": "priority", "value": "high",
     "severity": "wrong",
     "reason": "Source describes the issue but never assigns a priority level."}
  ]
}

If nothing is hallucinated, return {"flags": []}.
"""

HALLUCINATION_SYSTEM_PROMPT = with_source_material_instruction(_HALLUCINATION_SYSTEM)
"""System prompt for :meth:`LLMJudge.detect_hallucinations`, with the source-material sentence."""


def build_hallucination_system_prompt(field_descriptions: dict[str, str] | None = None) -> str:
    """:data:`HALLUCINATION_SYSTEM_PROMPT` followed by the caller's field rules, if any.

    ``field_descriptions`` is an optional ``{field_name: description}`` map
    that gives the judge per-field rules — e.g. "this field defaults to
    'turvallisuus' when the report type is unclear" — so the judge can
    distinguish a documented soft default from a true hallucination. The
    rules are the caller's instructions, so they go in the system message.
    """
    rules = _render_field_rules(field_descriptions)
    return f"{HALLUCINATION_SYSTEM_PROMPT}\n\n{rules}" if rules else HALLUCINATION_SYSTEM_PROMPT


def _one_line(text: str) -> str:
    return " ".join(str(text).split())


def _render_field_rules(field_descriptions: dict[str, str] | None) -> str:
    if not field_descriptions:
        return ""
    lines = ["Field rules (use these to decide what counts as 'unsupported'):"]
    for name, desc in field_descriptions.items():
        short = desc.replace("\n", " ").strip()
        if len(short) > 240:
            short = short[:237] + "..."
        lines.append(f"  - {_one_line(name)}: {short}")
    return "\n".join(lines)


def build_hallucination_prompt(
    source_text: str,
    extracted: dict,
    field_descriptions: dict[str, str] | None = None,
    *,
    material: SourceMaterial | None = None,
) -> str:
    """Assemble the user-side prompt for a hallucination-detector call.

    The source text (truncated by the caller if needed) and the extracted
    JSON are shown verbatim, each in its own block, labelled ``"source"``
    and ``"answer"``. ``field_descriptions``, when given, is rendered as
    field rules before the blocks, outside them. :meth:`LLMJudge.detect_hallucinations`
    does not pass it here: it puts the rules in the system message with
    :func:`build_hallucination_system_prompt`. Pass the call's ``material``
    so every block of the call shares its id.
    """
    material = material or SourceMaterial()
    extracted_json = json.dumps(extracted, indent=2, ensure_ascii=False)
    parts = [
        _render_field_rules(field_descriptions),
        "Flag any field value in the block labelled answer that the block "
        "labelled source does not support.",
        material.wrap(source_text, label="source"),
        material.wrap(extracted_json, label="answer"),
    ]
    return "\n\n".join(part for part in parts if part)


def build_text_pair_prompt(
    extracted_text: str,
    expected_text: str,
    field_name: str | None = None,
    context: str | None = None,
    *,
    material: SourceMaterial | None = None,
) -> str:
    """Assemble the user-side prompt for a text-vs-text equivalence call.

    Both values are shown verbatim, each in its own block: the extracted
    value labelled ``"answer"`` and the expected one ``"reference"``.
    ``context`` (e.g. the surrounding transcript) goes in a third block
    labelled ``"context"``. ``field_name`` is a hint from the caller's
    schema; it stays outside the blocks, on one line. Pass the
    call's ``material`` so every block of the call shares its id.
    """
    material = material or SourceMaterial()
    parts: list[str] = []
    name = _one_line(field_name)[:200] if field_name else ""
    if name:
        parts.append(f"Field: {name}")
    parts.append(
        "Decide whether the value in the block labelled answer is semantically "
        "equivalent to the value in the block labelled reference."
    )
    parts.append(material.wrap(expected_text, label="reference"))
    parts.append(material.wrap(extracted_text, label="answer"))
    if context:
        parts.append(material.wrap(context, label="context"))
    return "\n\n".join(parts)


def _render_rubric(rubric: ValidationRubric) -> str:
    """The rubric as check lists, followed by its few-shot examples."""
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

    body: list[str] = []
    rubric_block = "\n".join(lines).strip()
    if rubric_block:
        body.append(rubric_block)
    fewshot_block = _render_few_shot_block(rubric.few_shot_examples)
    if fewshot_block:
        body.append(fewshot_block)
    return "\n\n".join(body)


def build_user_prompt(
    extracted: list[dict] | dict,
    rubric: ValidationRubric | None = None,
    *,
    material: SourceMaterial | None = None,
) -> str:
    """Assemble the per-call user-side prompt: the task and the extractor output.

    The extracted JSON is shown verbatim inside one block labelled
    ``"answer"``. ``rubric``, when given, is rendered as check lists and
    few-shot examples before the block, outside it. :meth:`LLMJudge.validate`
    does not pass it here: it puts the rubric in the system message with
    :func:`build_system_prompt` (``rubric=``). Pass the call's ``material``
    so every block of the call shares its id.
    """
    material = material or SourceMaterial()
    extracted_json = json.dumps(extracted, indent=2, ensure_ascii=False)
    parts = [
        _render_rubric(rubric) if rubric is not None else "",
        "Compare the extractor output in the block labelled answer against the "
        "page images and emit your flags.",
        material.wrap(extracted_json, label="answer"),
    ]
    return "\n\n".join(part for part in parts if part)
