"""LLM-as-Judge Likert-1-5 scoring demo.

Shows the difference between the v1 "severity-only" mode and the new
``scoring_mode="likert_1_5"`` mode that returns an integer 1-5 alongside the
severity. HuggingFace cookbook reports ~30 % better human-correlation when
moving from float scales to integer Likert.

Also demonstrates few-shot calibration via ``ValidationRubric.few_shot_examples``
(1-2 examples is the cookbook sweet spot — more give diminishing returns).

Requires the same Google credentials as ``demo_llm_judge.py`` and a sample PDF
at ``examples/software_components/validators/sample_po.pdf``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.validators import (  # noqa: E402
    FewShotExample,
    LLMJudge,
    ValidationFlag,
    ValidationRubric,
)

SAMPLE_PDF = Path(__file__).parent / "sample_po.pdf"


def render_pages_to_png(pdf_path: Path, dpi: int = 150) -> list[bytes]:
    import fitz  # pymupdf

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

    extracted = [
        {"item_index": 0, "item_number": "0010", "quantity": "940"},
        {"item_index": 1, "item_number": "0020", "quantity": "947"},
    ]

    # One few-shot example pinning the "blatant unit confusion" pattern.
    few_shot = FewShotExample(
        description="Quantity from PER column instead of ordered quantity",
        extracted=[
            {"item_index": 0, "item_number": "0001", "quantity": "1"},
        ],
        expected_flags=[
            ValidationFlag(
                item_index=0,
                field="quantity",
                severity="wrong",
                score=1,
                reason="Document shows ordered qty 1500 in line-total column, not unit-price '15'",
                suggested_value="1500",
            ),
        ],
    )

    rubric = ValidationRubric(
        vendor_id="acme-supply",
        scoring_mode="likert_1_5",
        evaluation_aspects=[
            "Quantity is the ordered amount, not the unit price",
            "Quantity is integer units, not a decimal portion of another value",
        ],
        field_checks=[
            "Watch for confusion between unit price and line quantity columns.",
        ],
        few_shot_examples=[few_shot],
    )

    result = judge.validate(source_pages=pages, extracted=extracted, rubric=rubric)

    print(f"Provider: {result.usage.provider} / {result.usage.model}")
    print(f"Cost:     ${result.usage.cost_usd:.4f}")
    print(f"Flags ({len(result.flags)}):")
    for flag in result.flags:
        suggestion = f" -> {flag.suggested_value!r}" if flag.suggested_value else ""
        score = f" {flag.score}/5" if flag.score else ""
        print(
            f"  [{flag.severity:7s}{score}] item {flag.item_index}"
            f" field={flag.field}{suggestion}"
        )
        print(f"      {flag.reason}")


if __name__ == "__main__":
    main()
