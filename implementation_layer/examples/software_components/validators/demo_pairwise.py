"""LLM-as-Judge pairwise A/B comparison demo.

Compares two extractor outputs against the same source document and reports
which is more faithful — with position-bias mitigation. GPT-4-class judges
flip their decision ~40 % of the time when A/B order is swapped (Justice or
Prejudice, OpenReview 2024); ``swap_and_average=True`` runs the comparison
twice and only declares a winner when both passes agree.

Useful for:
  - A/B testing prompt variants ("does the new prompt produce better extractions?").
  - Comparing two extractor models on the same document.
  - Picking between human-corrected and machine output.

Requires Google credentials (or change the ``model_provider`` argument).
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.validators import (  # noqa: E402
    LLMJudge,
    compare_pairwise,
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

    judge = LLMJudge(
        model_provider="google",
        model="gemini-3-flash-preview",
        use_vertexai=True,
    )

    pages = render_pages_to_png(SAMPLE_PDF)

    # A: clearly wrong (took the PER value)
    extracted_a = [
        {"item_index": 0, "item_number": "0010", "quantity": "940"},
        {"item_index": 1, "item_number": "0020", "quantity": "947"},
    ]
    # B: corrected to ordered quantities
    extracted_b = [
        {"item_index": 0, "item_number": "0010", "quantity": "4279"},
        {"item_index": 1, "item_number": "0020", "quantity": "1947"},
    ]

    result = compare_pairwise(
        judge=judge,
        source_pages=pages,
        extracted_a=extracted_a,
        extracted_b=extracted_b,
        swap_and_average=True,
    )

    print(f"Winner:           {result.winner}")
    print(f"Score A:          {result.score_a}/5")
    print(f"Score B:          {result.score_b}/5")
    print(f"Swap-consistent:  {result.swap_consistent}")
    print(f"Reason:           {result.reason}")
    total_cost = sum(u.cost_usd for u in result.usage)
    total_dur = sum(u.duration_s for u in result.usage)
    print(f"Cost (2 passes):  ${total_cost:.4f}")
    print(f"Wall time:        {total_dur:.1f}s")


if __name__ == "__main__":
    main()
