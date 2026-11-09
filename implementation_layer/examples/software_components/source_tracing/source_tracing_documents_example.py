"""Source Tracing example: DocumentsToStructuredData, with evidence checked against the parsed text.

The module parses the document and extracts from the parsed text. Passing a ready schema
(``schema=`` and ``requirements=``) keeps the module from generating its own, so the
evidence request reaches only the extraction. The quotes are checked against
``result.parsed_documents``, the text the extractor actually read.

    python source_tracing_documents_example.py

Needs: pip install "gaik[documents-to-structured-data,source-tracing]" and credentials (.env).
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
from gaik.software_modules.documents_to_structured_data import (  # noqa: E402
    DocumentsToStructuredData,
)
from po_schema import REQUIREMENTS, TASK, PurchaseOrder, print_report  # noqa: E402


def main() -> None:
    tracing = SourceTracing()
    task = tracing.augment(PurchaseOrder, TASK, source="text")

    pipeline = DocumentsToStructuredData(use_azure=True)
    result = pipeline.run(
        file_path=HERE / "PO.pdf",
        user_requirements=task.prompt,
        # PyMuPDF reads the PDF's text layer without a model call; "vision_parser" also works.
        parser_choice="pymupdf",
        schema=task.model,
        requirements=REQUIREMENTS,
    )

    data, report = tracing.check_text(result.extracted_fields, result.parsed_documents)

    print("Extracted data (evidence removed):")
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    print_report(report)


if __name__ == "__main__":
    main()
