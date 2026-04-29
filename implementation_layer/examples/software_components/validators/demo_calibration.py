"""LLM-as-Judge calibration against human labels.

Skeleton showing how to verify your judge / rubric reaches the
HuggingFace-cookbook reference Pearson correlation (~0.84) with human raters
before you deploy it.

You provide ~30 hand-labeled examples (Likert 1-5 + optional severity),
:func:`calibrate_against_human_labels` runs the judge over all of them and
returns a :class:`CalibrationReport` with Pearson r and severity-agreement
rate.

This file uses placeholders so it can be edited offline; replace the
``CALIBRATION_DATA`` list with your own labeled examples to actually run it.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.validators import (  # noqa: E402
    CalibrationItem,
    LLMJudge,
    ValidationRubric,
    calibrate_against_human_labels,
)


def load_pages(pdf_path: Path) -> list[bytes]:
    import fitz

    doc = fitz.open(pdf_path)
    matrix = fitz.Matrix(150 / 72, 150 / 72)
    pages = [page.get_pixmap(matrix=matrix, alpha=False).tobytes("png") for page in doc]
    doc.close()
    return pages


# Replace these placeholders with your own labeled dataset (~30 items).
# Each item: a PDF path + extractor output + human Likert score 1-5.
CALIBRATION_DATA: list[tuple[Path, list[dict] | dict, int, str]] = [
    # (pdf_path, extracted_json, human_likert_1_to_5, optional_severity_label)
    # (Path("eval-data/po-001.pdf"), [...], 5, "ok"),
    # (Path("eval-data/po-002.pdf"), [...], 1, "wrong"),
    # ...
]


def main() -> None:
    if not CALIBRATION_DATA:
        print(
            "No calibration data configured. Edit CALIBRATION_DATA in this file\n"
            "to point at your hand-labeled extractor outputs."
        )
        return

    judge = LLMJudge(
        model_provider="google",
        model="gemini-3-flash-preview",
        use_vertexai=True,
    )

    rubric = ValidationRubric(
        scoring_mode="likert_1_5",
        field_checks=["Replace with your domain-specific check sentences"],
    )

    dataset: list[CalibrationItem] = []
    for pdf_path, extracted, human_score, severity in CALIBRATION_DATA:
        pages = load_pages(pdf_path)
        dataset.append(
            CalibrationItem(
                source_pages=pages,
                extracted=extracted,
                human_score=human_score,
                human_severity=severity if severity in ("ok", "suspect", "wrong") else None,  # type: ignore[arg-type]
                note=str(pdf_path.name),
            )
        )

    report = calibrate_against_human_labels(judge, dataset, rubric=rubric)
    print(report)
    print("\nPer-item:")
    for item in report.per_item:
        print(f"  human={item['human_score']:.0f}  judge={item['judge_score']:.2f}  {item['note']}")


if __name__ == "__main__":
    main()
