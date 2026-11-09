"""Source Tracing example: VisionExtractor on a PDF, with evidence checked against the PDF.

Run it from any folder:

    python source_tracing_example.py              # PO.pdf
    python source_tracing_example.py PO2.pdf      # the two-page purchase order

The three steps:
1. ``augment`` adds the evidence request to the schema and the task.
2. The VisionExtractor runs as usual (it is not changed).
3. ``check_pdf`` finds each quote in the PDF's own text layer, compares the value with it,
   and gives the page position of the words.

Needs: pip install "gaik[vision-extract,source-tracing]" and model credentials (.env).
"""

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE.parents[2] / ".env")

# Allow running without `pip install -e .`
sys.path.insert(0, str(HERE.parents[2] / "src"))

from gaik.software_components.source_tracing import SourceTracing  # noqa: E402
from gaik.software_components.vision_extractor import VisionExtractor  # noqa: E402
from po_schema import REQUIREMENTS, TASK, PurchaseOrder, print_report  # noqa: E402


def main(pdf_name: str = "PO.pdf") -> None:
    pdf = HERE / pdf_name
    tracing = SourceTracing()

    # 1. Ask for evidence: a copy of the schema with the citation field, and the task text
    #    with the instruction. "files" because the model reads the PDF itself.
    task = tracing.augment(PurchaseOrder, TASK, source="files")

    # 2. The extractor, unchanged.
    extractor = VisionExtractor(model_provider="openai", use_azure=True, reasoning_effort="low")
    result = extractor.extract(
        file_paths=[pdf],
        user_requirements=task.prompt,
        extraction_model=task.model,
        requirements=REQUIREMENTS,
    )

    # 3. Check each value against its quote in the PDF.
    data, report = tracing.check_pdf(result.data, [pdf])

    print("Extracted data (evidence removed):")
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    print_report(report)

    # A UI can draw the boxes: fractions of the page, per quoted word.
    first = next((item for item in report.items if item.rects), None)
    if first:
        print(f"\nBox of '{first.quote[:30]}' on page {first.page}: {first.rects[0]}")


if __name__ == "__main__":
    main(*sys.argv[1:2])
