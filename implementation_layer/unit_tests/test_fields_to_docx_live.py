"""Live test of fields to Word: a real extraction with evidence, written to a Word file.

``DataExtractor`` fills three fields from a synthetic service note with the evidence request
of ``SourceTracing``; ``check_text`` checks the quotes; ``FieldsToDocx`` writes the record and
the report to a file, which is read back with python-docx. One model call.

Needs Azure OpenAI: ``AZURE_API_KEY`` and ``AZURE_ENDPOINT``, with ``AZURE_DEPLOYMENT``
naming the chat deployment. Skipped when the key or the endpoint is missing.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

docx = pytest.importorskip("docx")

from gaik.software_components.extractor import (  # noqa: E402
    DataExtractor,
    ExtractionRequirements,
    FieldSpec,
    create_extraction_model,
)
from gaik.software_components.fields_to_docx import FieldsToDocx  # noqa: E402
from gaik.software_components.llm import get_llm_config  # noqa: E402
from gaik.software_components.source_tracing import SourceTracing  # noqa: E402

_MISSING = [name for name in ("AZURE_API_KEY", "AZURE_ENDPOINT") if not os.getenv(name, "").strip()]

# Calls a real LLM: these assert on model output, so they fail when the model or
# the Azure deployment changes, not only when our code regresses. Kept out of the
# push gate (`-m "not llm"`); see .github/workflows/test.yml.
pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(bool(_MISSING), reason=f"live Azure OpenAI test: set {', '.join(_MISSING)}"),
]

# Synthetic: no real site, person or order.
NOTE = (
    "Service visit at Hall 3 on 12 November 2026.\n"
    "The technician replaced the inlet valve of pump P-204 and changed two gaskets.\n"
    "The pump was tested for 30 minutes without leaks.\n"
)
TASK = "Fill the service report from the technician's note."
REQUIREMENTS = ExtractionRequirements(
    use_case_name="service_note",
    fields=[
        FieldSpec(
            field_name="site",
            field_type="str",
            description="The hall or site where the work was done, as the note names it",
            nullable=True,
        ),
        FieldSpec(
            field_name="visit_date",
            field_type="date",
            description="The date of the service visit",
            nullable=True,
        ),
        FieldSpec(
            field_name="work_done",
            field_type="str",
            description="What the technician did, in one sentence",
            nullable=True,
        ),
    ],
)


def test_an_extracted_record_and_its_evidence_reach_the_word_file(tmp_path: Path):
    tracing = SourceTracing()
    task = tracing.augment(create_extraction_model(REQUIREMENTS), TASK, source="text")
    results = DataExtractor(config=get_llm_config("azure")).extract(
        extraction_model=task.model,
        requirements=REQUIREMENTS,
        user_requirements=task.prompt,
        documents=[NOTE],
    )
    records, report = tracing.check_text(results, [NOTE])
    assert len(records) == 1

    result = FieldsToDocx().write(
        records,
        tmp_path / "service_report.docx",
        title="Service report",
        labels={"visit_date": "Date of visit"},
        trace=report,
        appendix=NOTE,
    )

    document = docx.Document(str(result.path))
    rows = [[cell.text for cell in row.cells] for row in document.tables[0].rows]
    print(report.summary())
    for row in rows:
        print(row)

    assert rows[0] == ["Field", "Value", "Evidence"]
    assert [row[0] for row in rows[1:]] == ["Site", "Date of visit", "Work done"]
    values = {row[0]: row[1] for row in rows[1:]}
    assert "Hall 3" in values["Site"]
    assert values["Date of visit"] == "2026-11-12"
    assert (result.rows, result.filled) == (3, 3)

    # At least one quote in the file stands in the note as it is, and the file shows it
    # with the verdict of the check.
    found = [item for item in report.items if item.span is not None and item.quote in NOTE]
    assert found, "no quote of the model was found in the note"
    cells = [row[2] for row in rows[1:]]
    assert any(f'"{item.quote}" ({item.verdict})' in cells for item in found)
    assert [paragraph.text for paragraph in document.paragraphs][-2:] == [
        "Appendix: source text",
        NOTE.strip(),
    ]
