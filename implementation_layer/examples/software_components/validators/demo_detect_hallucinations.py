"""LLMJudge.detect_hallucinations() demo — schema-agnostic post-extraction scrub.

Given a source text and an extractor's structured output, the judge flags
any field whose value is not directly supported by the source. Drop the
flagged values to ``""`` to clean up hallucinated extraction outputs.

Use case: a generic alternative to handwritten keyword post-validators
(which need a separate config per schema).

Requires Azure OpenAI credentials (the default ``model_provider="azure"``):
    AZURE_API_KEY, AZURE_ENDPOINT, AZURE_DEPLOYMENT, AZURE_API_VERSION
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.validators import LLMJudge  # noqa: E402

# A short maintenance log entry — the kind of source text a structured
# extractor might be asked to summarise into JSON fields.
TRANSCRIPT = (
    "Maintenance round on 2025-09-12. The technician reported a coolant "
    "leak under unit B and applied an absorbent mat. The leak source was "
    "not identified during this visit."
)

# A typical extractor output: most fields grounded, two hallucinated
# (priority guessed from domain context, follow-up date invented).
EXTRACTED = {
    "report_date": "2025-09-12",
    "location": "unit B",
    "issue_type": "coolant leak",
    "actions_taken": "absorbent mat applied",
    "priority": "high",  # ← hallucinated: source never says priority
    "follow_up_date": "2025-09-15",  # ← hallucinated: source never says when
}

# Optional per-field rules teach the judge which "soft defaults" are
# documented (and therefore not hallucinations). Pass an empty dict when
# no such rules exist.
FIELD_RULES = {
    "priority": (
        "Return only if explicitly classified in the source "
        "(e.g. 'priority high', 'low priority'). Domain context is not enough."
    ),
}


def main() -> None:
    judge = LLMJudge(model_provider="azure")
    report = judge.detect_hallucinations(
        source_text=TRANSCRIPT,
        extracted=EXTRACTED,
        field_descriptions=FIELD_RULES,
    )
    print(f"Source:\n  {TRANSCRIPT}\n")
    print("Extractor output:")
    for k, v in EXTRACTED.items():
        print(f"  {k}: {v!r}")
    print()
    print(f"Judge flagged {len(report.flags)} hallucination(s):")
    for flag in report.flags:
        print(f"  - {flag.field} = {flag.value!r}  ({flag.severity})")
        print(f"    reason: {flag.reason}")
    print()
    print(
        f"Usage: {report.usage.input_tokens}+{report.usage.output_tokens} tokens, "
        f"${report.usage.cost_usd:.4f}, {report.usage.duration_s:.2f}s"
    )

    # Apply the scrub: clear flagged fields.
    cleaned = dict(EXTRACTED)
    for flag in report.flags:
        cleaned[flag.field] = ""

    print("\nCleaned extraction (after scrub):")
    for k, v in cleaned.items():
        marker = " ← cleared" if v == "" and EXTRACTED.get(k) else ""
        print(f"  {k}: {v!r}{marker}")


if __name__ == "__main__":
    main()
