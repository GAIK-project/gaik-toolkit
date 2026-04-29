"""LLM-as-Judge Panel (jury) demo.

Runs three judges (Gemini + Claude + GPT-5.4-mini) over the same extractor
output and aggregates them via majority vote. Useful when:

  - You want to mitigate single-model self-preference bias
    (arXiv 2604.22891 — judges score familiar outputs more leniently).
  - You want an explicit ``agreement_score`` to gate downstream actions
    (e.g., only auto-confirm when all judges agreed it was "ok").

Cost: roughly 3× a single-judge call. Latency is sequential — total time
is the sum of the three calls.

Requires:
  - ``GOOGLE_VERTEXAI_PROJECT`` (+ ``GOOGLE_APPLICATION_CREDENTIALS``)
  - ``ANTHROPIC_API_KEY`` (or Foundry equivalent on Azure)
  - ``AZURE_*`` or ``OPENAI_API_KEY``
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.validators import (  # noqa: E402
    LLMJudge,
    LLMJudgePanel,
    ValidationRubric,
)

SAMPLE_PDF = Path(__file__).parent / "sample_po.pdf"


def render_pages_to_png(pdf_path: Path, dpi: int = 150) -> list[bytes]:
    import fitz

    doc = fitz.open(pdf_path)
    matrix = fitz.Matrix(dpi / 72, dpi / 72)
    pages = [page.get_pixmap(matrix=matrix, alpha=False).tobytes("png") for page in doc]
    doc.close()
    return pages


def main() -> None:
    if not SAMPLE_PDF.exists():
        print(f"Missing {SAMPLE_PDF}. Copy a PDF in to run this demo.")
        return

    panel = LLMJudgePanel(
        judges=[
            LLMJudge(model_provider="google", model="gemini-3-flash-preview", use_vertexai=True),
            LLMJudge(model_provider="anthropic", model="claude-haiku-4-5-20251001"),
            LLMJudge(model_provider="azure", model="gpt-5.4-mini", use_azure=True),
        ]
    )

    pages = render_pages_to_png(SAMPLE_PDF)
    extracted = [
        {"item_index": 0, "item_number": "0010", "quantity": "940"},
        {"item_index": 1, "item_number": "0020", "quantity": "947"},
    ]
    rubric = ValidationRubric(
        vendor_id="copper-brass",
        scoring_mode="likert_1_5",
        field_checks=[
            "Quantity is integer pounds before the decimal — '4,279.940 LB' = 4279.",
        ],
    )

    result = panel.validate(source_pages=pages, extracted=extracted, rubric=rubric)

    print("=== Per-judge results ===")
    for r, j in zip(result.per_judge, panel.judges, strict=True):
        print(f"\n[{j.model_provider}/{j.model}] cost=${r.usage.cost_usd:.4f}, dur={r.usage.duration_s:.1f}s")
        for flag in r.flags:
            suggestion = f" -> {flag.suggested_value!r}" if flag.suggested_value else ""
            score = f" {flag.score}/5" if flag.score else ""
            print(f"  [{flag.severity:7s}{score}] item {flag.item_index} field={flag.field}{suggestion}")

    print("\n=== Aggregated (majority vote, ties → worst severity) ===")
    print(f"Agreement: {result.agreement_score:.1%}")
    print(f"Total cost: ${result.total_cost_usd:.4f} (3 judges)")
    for flag in result.aggregated_flags:
        suggestion = f" -> {flag.suggested_value!r}" if flag.suggested_value else ""
        score = f" median {flag.score}/5" if flag.score else ""
        print(f"  [{flag.severity:7s}{score}] item {flag.item_index} field={flag.field}{suggestion}")


if __name__ == "__main__":
    main()
