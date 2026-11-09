"""Source Tracing example: DataExtractor on text, with evidence checked against the text.

The DataExtractor reads text, so the PDF is first turned into text (here with PyMuPDF's own
text layer; any parser output works the same). The quotes are then checked against exactly
that text, with the position of each quote as character offsets.

    python source_tracing_data_extractor_example.py

Needs: pip install "gaik[extract,source-tracing]" and model credentials (.env).
"""

import json
import sys
from pathlib import Path

import pymupdf
from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE.parents[2] / ".env")

# Allow running without `pip install -e .`
sys.path.insert(0, str(HERE.parents[2] / "src"))

from gaik.software_components.config import get_openai_config  # noqa: E402
from gaik.software_components.extractor import DataExtractor  # noqa: E402
from gaik.software_components.source_tracing import SourceTracing  # noqa: E402
from po_schema import REQUIREMENTS, TASK, PurchaseOrder, print_report  # noqa: E402


def main() -> None:
    with pymupdf.open(HERE / "PO.pdf") as pdf:
        text = "\n".join(page.get_text() for page in pdf)

    tracing = SourceTracing()

    # 1. "text": the extractor reads text, not files. The instruction tells the model to
    #    answer document 1 and to leave the page at 1 unless the text marks its pages.
    task = tracing.augment(PurchaseOrder, TASK, source="text")

    # 2. The extractor, unchanged. It returns one result per document.
    extractor = DataExtractor(config=get_openai_config(use_azure=True))
    results = extractor.extract(
        extraction_model=task.model,
        requirements=REQUIREMENTS,
        user_requirements=task.prompt,
        documents=[text],
    )

    # 3. Check the quotes against the text the extractor read.
    data, report = tracing.check_text(results, [text])

    print("Extracted data (evidence removed):")
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    print_report(report)

    located = next((item for item in report.items if item.span), None)
    if located:
        start, end = located.span
        print(f"\nQuote for {located.field} sits at characters {start}-{end}: {text[start:end]!r}")


if __name__ == "__main__":
    main()
