"""System and user prompts for the LLM-as-judge validator."""

from __future__ import annotations

import json

from .schema import ValidationRubric

JUDGE_SYSTEM_PROMPT = """\
You are a quality validator for structured extraction. You receive:
1. One or more page images from a source document.
2. A JSON snapshot of what an upstream extractor produced from that document.

Your job: identify fields whose value in the JSON does NOT match the document.

For every field you can verify against the images, output one entry. Use these
severities:
  - "ok"      — value matches the document
  - "suspect" — value seems unlikely or partially wrong
  - "wrong"   — value clearly contradicts the document or a required value is empty

For each "wrong" or "suspect" entry, include a short reason (≤25 words) and,
where you can read it from the document, a suggested_value.

If items are MISSING from the JSON that you can see in the document, emit a
document-level entry with item_index=-1, field="_document.item_count", and
suggested_value = the count you observe in the document.

Respond with ONLY a JSON object, no prose, no markdown fences:
{
  "flags": [
    {"item_index": 0, "field": "quantity", "severity": "wrong",
     "confidence": 0.95, "reason": "Document shows 4279 LB",
     "suggested_value": "4279"},
    ...
  ]
}
"""


def build_user_prompt(extracted: list[dict] | dict, rubric: ValidationRubric | None) -> str:
    """Assemble the per-call user-side prompt block.

    The extracted JSON is shown verbatim. The rubric, if any, is rendered as
    bulleted check lists so the model can use them as a checklist.
    """
    rubric = rubric or ValidationRubric()

    lines: list[str] = []
    if rubric.vendor_id:
        lines.append(f"Vendor: {rubric.vendor_id}")
    if rubric.field_checks:
        lines.append("\nField-level checks:")
        lines.extend(f"  - {check}" for check in rubric.field_checks)
    if rubric.item_level_checks:
        lines.append("\nItem-level / document-level checks:")
        lines.extend(f"  - {check}" for check in rubric.item_level_checks)
    if rubric.custom_system_suffix:
        lines.append("\n" + rubric.custom_system_suffix)

    rubric_block = "\n".join(lines).strip()
    extracted_json = json.dumps(extracted, indent=2, ensure_ascii=False)

    body = []
    if rubric_block:
        body.append(rubric_block)
    body.append("\nExtractor output (JSON):")
    body.append(f"```json\n{extracted_json}\n```")
    body.append("\nNow compare against the page images and emit your flags.")
    return "\n".join(body)
