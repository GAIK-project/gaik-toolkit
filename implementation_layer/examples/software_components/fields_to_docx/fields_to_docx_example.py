"""Fields to Word Example

Writes two Word files to the system's temporary folder and prints their paths:

1. label and value pairs with a facts line and the source text as an appendix;
2. a record with display labels and an evidence column. The evidence is a hand-made
   extraction result checked by the real ``SourceTracing().check_text``: plain code,
   no model call.

    python fields_to_docx_example.py

Needs: pip install "gaik[fields-to-docx]". No credentials.
"""

import sys
import tempfile
from datetime import date
from pathlib import Path

# Allow running without `pip install -e .`
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.fields_to_docx import FieldsToDocx  # noqa: E402
from gaik.software_components.source_tracing import SourceTracing  # noqa: E402

OUTPUT = Path(tempfile.gettempdir())

# Synthetic text: no real site, person or order.
NOTE = """\
Service visit at Hall 3 on 12 November 2026.
The technician replaced the inlet valve of pump P-204 and changed two gaskets.

The pump was tested for 30 minutes without leaks. The spare valve was the last one in
stock, so a new one has to be ordered before the next visit."""


def pairs_example() -> Path:
    """Label and value pairs, a facts line and the note as an appendix."""
    result = FieldsToDocx().write(
        [
            ("Site", "Hall 3"),
            ("Equipment", "Pump P-204"),
            ("Work done", "Replaced the inlet valve and changed two gaskets"),
            ("Parts used", ["Inlet valve", "Gasket", "Gasket"]),
            ("Test run (minutes)", 30.0),
            ("Leaks found", False),
            ("Next visit", None),
        ],
        OUTPUT / "gaik_fields_to_docx_pairs.docx",
        title="Service report",
        metadata={"Date": date(2026, 11, 12), "Source": "Technician's note"},
        appendix=NOTE,
        footer="Synthetic example content",
    )
    print(f"Pairs:  {result.path} ({result.filled} of {result.rows} rows filled)")
    return result.path


def record_with_evidence_example() -> Path:
    """A record as an extractor returns it, with quotes checked against the note."""

    def cite(field: str, quote: str) -> dict:
        return {"field": field, "document": 1, "page": 1, "quote": quote}

    # What DataExtractor.extract() returns for a model that SourceTracing.augment prepared:
    # the values, and one citation per value in "field_sources". Written by hand here, with
    # one quote that is not in the note, to show the "check" verdict.
    extracted = {
        "site": "Hall 3",
        "visit_date": "2026-11-12",
        "work_done": "Replaced the inlet valve and changed two gaskets",
        "test_minutes": 30,
        "order_needed": True,
        "next_visit": None,
        "field_sources": {
            "items": [
                cite("site", "Service visit at Hall 3"),
                cite("visit_date", "on 12 November 2026"),
                cite("work_done", "replaced the inlet valve of pump P-204"),
                cite("test_minutes", "tested for 45 minutes"),
                cite("order_needed", "a new one has to be ordered"),
            ]
        },
    }
    record, report = SourceTracing().check_text(extracted, [NOTE])
    print(f"Check:  {report.summary()}")

    result = FieldsToDocx().write(
        record,
        OUTPUT / "gaik_fields_to_docx_evidence.docx",
        title="Service report with evidence",
        labels={"visit_date": "Date of visit", "test_minutes": "Test run (minutes)"},
        trace=report,
        appendix=NOTE,
        appendix_title="Appendix: technician's note",
    )
    print(f"Record: {result.path} ({result.filled} of {result.rows} rows filled)")
    return result.path


if __name__ == "__main__":
    pairs_example()
    record_with_evidence_example()
