"""Source Tracing example: see the evidence on the page.

Runs the VisionExtractor on a purchase order PDF with source tracing, then writes ONE
self-contained HTML page that shows what the check found: every value with its quote
outlined on the PDF page, a verdict per value, and an explanation of each part.

    python source_tracing_viewer_example.py              # PO.pdf
    python source_tracing_viewer_example.py PO2.pdf      # the two-page purchase order

Open ``output/trace_view.html`` in a browser. The page needs no server: the PDF pages are
embedded in it. ``trace_viewer.py`` (next to this file) builds the page and shows, on the
page itself, the function that draws the boxes, so you can reuse it in your own interface.

The real purchase order gives mostly verified values. Three extra fields are added to the
task on purpose, so the page also shows the other verdicts: a value that is translated, one
that is converted to another unit, and a category code that the document does not contain.

Needs: pip install "gaik[vision-extract,source-tracing]" and model credentials (.env).
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE.parents[2] / ".env")

# Allow running without `pip install -e .`
sys.path.insert(0, str(HERE.parents[2] / "src"))

from gaik.software_components.extractor import (  # noqa: E402
    CompositeExtractionRequirements,
    ExtractionRequirements,
    FieldSpec,
)
from gaik.software_components.source_tracing import SourceTracing  # noqa: E402
from gaik.software_components.vision_extractor import VisionExtractor  # noqa: E402
from po_schema import REQUIREMENTS, TASK, PurchaseOrder  # noqa: E402
from pydantic import Field  # noqa: E402
from trace_viewer import write_trace_view  # noqa: E402

# Three fields that the document cannot answer word for word, to show the other verdicts.
EXTRA_TASK = """
Also extract these three values. They are not written in the document in this form, so give
them as asked:
- first_item_description_fi: the description of the first line item, translated into Finnish.
- first_item_quantity_lb: the quantity of the first line item converted to pounds (a number).
- first_item_steel_class: the material of the first line item as one of the codes
  carbon_steel or stainless_steel.
"""


class TracedPurchaseOrder(PurchaseOrder):
    first_item_description_fi: str | None = Field(None, description="First item, in Finnish")
    first_item_quantity_lb: float | None = Field(None, description="First quantity, in pounds")
    first_item_steel_class: str | None = Field(None, description="carbon_steel or stainless_steel")


EXTENDED_REQUIREMENTS = CompositeExtractionRequirements(
    parent_requirements=ExtractionRequirements(
        use_case_name="purchase_order_view",
        fields=[
            *REQUIREMENTS.parent_requirements.fields,
            FieldSpec(
                field_name="first_item_description_fi",
                field_type="str",
                description="First line item description, translated into Finnish",
            ),
            FieldSpec(
                field_name="first_item_quantity_lb",
                field_type="float",
                description="First line item quantity converted to pounds",
            ),
            FieldSpec(
                field_name="first_item_steel_class",
                field_type="str",
                description="Material of the first line item: carbon_steel or stainless_steel",
            ),
        ],
    ),
    children=REQUIREMENTS.children,
)


def main(pdf_name: str = "PO.pdf") -> None:
    pdf = HERE / pdf_name
    tracing = SourceTracing()

    # 1. Ask for evidence. "files": the model reads the PDF itself and names file and page.
    task_text = TASK + EXTRA_TASK
    task = tracing.augment(TracedPurchaseOrder, task_text, source="files")

    # 2. The extractor, unchanged.
    extractor = VisionExtractor(model_provider="openai", use_azure=True, reasoning_effort="low")
    result = extractor.extract(
        file_paths=[pdf],
        user_requirements=task.prompt,
        extraction_model=task.model,
        requirements=EXTENDED_REQUIREMENTS,
    )

    # 3. Check each value against its quote in the PDF.
    data, report = tracing.check_pdf(result.data, [pdf])

    summary = report.summary()
    print(
        f"{summary['total']} values with a quote: {summary['verified']} verified, "
        f"{summary['check']} check, {summary['reworded']} reworded, "
        f"{summary['unchecked']} unchecked (coverage {summary['coverage']:.0%})"
    )

    # 4. One HTML page with everything: the quotes on the pages, the verdicts, the explanations.
    out = write_trace_view(
        HERE / "output" / "trace_view.html",
        pdf_paths=[pdf],
        report=report,
        clean_results=data,
        task_prompt=task.prompt,
        task_text=task_text,
        notes=[
            "The last three fields (first_item_description_fi, first_item_quantity_lb and "
            "first_item_steel_class) were added to the task on purpose: a translated value, a "
            "converted value and a category code are not written in the document, so they show "
            "the other verdicts.",
        ],
    )
    print(f"Open this page in a browser: {out}")


if __name__ == "__main__":
    main(*sys.argv[1:2])
