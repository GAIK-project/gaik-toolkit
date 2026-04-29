"""LLM-as-Judge demo.

Renders a sample purchase-order PDF to PNG bytes via PyMuPDF, then asks the
``LLMJudge`` to validate a deliberately-buggy extractor output against the
document. Exercises the multi-provider switch by defaulting to Google Gemini
(winner of the Luvata judge benchmark).

Requires either:
    - ``GOOGLE_VERTEXAI_PROJECT`` + ``GOOGLE_APPLICATION_CREDENTIALS`` (preferred), or
    - ``GOOGLE_GEMINI_API_KEY`` (fallback)

Plus a small PDF at ``examples/software_components/validators/sample_po.pdf``.
The Luvata test corpus has compatible files at
``ParseBench/data-luvata/extraction-validation/cb-decimal-pounds-5400811766/source.pdf``
— copy it in to demo locally.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Allow running without `pip install -e .`
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.validators import (  # noqa: E402
    LLMJudge,
    ValidationRubric,
)

SAMPLE_PDF = Path(__file__).parent / "sample_po.pdf"


def render_pages_to_png(pdf_path: Path, dpi: int = 150) -> list[bytes]:
    """Render every page of *pdf_path* to PNG bytes using PyMuPDF."""
    import fitz  # pymupdf

    doc = fitz.open(pdf_path)
    matrix = fitz.Matrix(dpi / 72, dpi / 72)
    pages = [page.get_pixmap(matrix=matrix, alpha=False).tobytes("png") for page in doc]
    doc.close()
    return pages


def basic_example() -> None:
    if not SAMPLE_PDF.exists():
        print(
            f"Missing {SAMPLE_PDF.name}. Copy any PDF into "
            f"{SAMPLE_PDF.parent} and adjust the EXTRACTED block below."
        )
        return

    judge = LLMJudge(
        model_provider="google",
        model="gemini-3-flash-preview",
        use_vertexai=True,
    )

    pages = render_pages_to_png(SAMPLE_PDF)
    extracted = [
        # Deliberately-broken values — judge should flag them as wrong.
        {"item_index": 0, "item_number": "0010", "quantity": "940"},
        {"item_index": 1, "item_number": "0020", "quantity": "947"},
    ]
    rubric = ValidationRubric(
        vendor_id="copper-brass",
        scoring_mode="likert_1_5",
        field_checks=[
            "Quantity is integer pounds before the decimal — '4,279.940 LB' = 4279, not 940.",
            "Watch for the literal '1 LB' under PER column; it is not the ordered quantity.",
        ],
    )

    result = judge.validate(source_pages=pages, extracted=extracted, rubric=rubric)

    print(f"Provider: {result.usage.provider} / {result.usage.model}")
    print(f"Tokens: {result.usage.input_tokens} in, {result.usage.output_tokens} out")
    print(f"Cost:   ${result.usage.cost_usd:.4f}")
    print(f"Time:   {result.usage.duration_s:.1f}s")
    print(f"Flags ({len(result.flags)}):")
    for flag in result.flags:
        suggestion = f" -> {flag.suggested_value!r}" if flag.suggested_value else ""
        score = f" ({flag.score}/5)" if flag.score else ""
        print(
            f"  [{flag.severity:7s}{score}] item {flag.item_index} field={flag.field}"
            f"{suggestion}: {flag.reason}"
        )


if __name__ == "__main__":
    basic_example()
