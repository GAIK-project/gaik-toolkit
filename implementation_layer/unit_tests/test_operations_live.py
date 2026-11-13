"""Live checks of gaik.operations: real model calls on short synthetic texts.

Each test makes the calls its operation makes (one for an extraction or a classification,
two for field generation). The quotes are checked against the text by SourceTracing, so a
test fails when a quote is not in the text, whatever the model claims.

Needs Azure OpenAI: ``AZURE_API_KEY`` and ``AZURE_ENDPOINT``, with ``AZURE_DEPLOYMENT``
naming the chat deployment. Skipped when the key or the endpoint is missing. The
transcription check also needs ``AZURE_TRANSCRIPTION_MODEL`` and is skipped without it.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from gaik.operations import (
    FieldDefinition,
    OperationSettings,
    classify_text,
    extract_fields,
    generate_fields,
    parse_document,
    run_async,
    transcribe_audio,
)

_MISSING = [name for name in ("AZURE_API_KEY", "AZURE_ENDPOINT") if not os.getenv(name, "").strip()]

# Calls a real LLM: these assert on model output, so they fail when the model or
# the Azure deployment changes, not only when our code regresses. Kept out of the
# push gate (`-m "not llm"`); see .github/workflows/test.yml.
pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(bool(_MISSING), reason=f"live Azure OpenAI test: set {', '.join(_MISSING)}"),
]

SETTINGS = OperationSettings(provider="azure")
SAMPLES = Path(__file__).parent.parent / "no-code-assets" / "samples"
SAMPLE_PDF = SAMPLES / "purchase-order-processing" / "sample_data" / "customer_data" / "PO.pdf"
SAMPLE_AUDIO = SAMPLES / "incident-report-writing" / "Sample_2.m4a"

NOTE = (
    "Service note. The visit took place on 14 March 2026 at the Kallio pumping station.\n"
    "Technician Aino Virtanen replaced the shaft seal of pump P-12 and checked two valves.\n"
    "The pump was back in use the same afternoon.\n"
)
FIELDS = [
    FieldDefinition(name="Käyntipäivä", type="date", description="The date of the visit"),
    FieldDefinition(name="site", description="The place where the work was done"),
    FieldDefinition(name="supervisor", description="The name of the supervisor, if one is named"),
]


def _check_note_values(values) -> None:
    by_name = {item.name: item for item in values}
    assert list(by_name) == ["Käyntipäivä", "site", "supervisor"]

    visit = by_name["Käyntipäivä"]
    assert visit.value == "2026-03-14"
    assert visit.evidence and visit.evidence in NOTE
    assert "14 March 2026" in visit.evidence
    assert visit.verdict == "verified"

    site = by_name["site"]
    assert "Kallio" in str(site.value)
    assert site.evidence and site.evidence in NOTE
    assert site.verdict in ("verified", "reworded")

    # The note names no supervisor.
    assert by_name["supervisor"].model_dump(include={"value", "evidence", "verdict"}) == {
        "value": None,
        "evidence": None,
        "verdict": None,
    }


def test_generate_fields_names_the_fields_of_a_requirement():
    # The requirement says outright that a note is one record: "from each note" reads as
    # rows to the structure step now and then, and generate_fields refuses rows.
    fields = generate_fields(
        "A service note describes one visit to a site. Extract the visit date, the site name "
        "and the technician's name.",
        settings=SETTINGS,
    )

    names = " ".join(field.name for field in fields)
    print([(field.name, field.type) for field in fields])
    assert 3 <= len(fields) <= 6
    assert "date" in names and "site" in names and "technician" in names
    assert any(field.type == "date" for field in fields)
    assert all(field.name and field.description for field in fields)


def test_extract_fields_returns_values_with_quotes_from_the_text():
    values = extract_fields(NOTE, FIELDS, settings=SETTINGS)

    print([item.model_dump() for item in values])
    _check_note_values(values)


def test_the_same_extraction_through_run_async():
    values = asyncio.run(run_async(extract_fields, NOTE, FIELDS, settings=SETTINGS, deadline=240))

    _check_note_values(values)


def test_classify_text_picks_urgent_for_a_leak_onto_an_electrical_cabinet():
    result = classify_text(
        "Water is dripping from the ceiling straight onto the main electrical cabinet.",
        {
            "urgent": "A risk to people or equipment that needs action today",
            "normal": "Can wait for the next planned visit",
        },
        settings=SETTINGS,
    )

    print(result.model_dump())
    assert result.label == "urgent"
    assert result.backend == "llm"
    assert result.confidence == result.probabilities["urgent"] > 0.5
    assert round(sum(result.probabilities.values()), 3) == 1.0


def test_a_parsed_sample_pdf_is_extracted_with_quotes_from_its_text():
    pytest.importorskip("pymupdf")
    document = parse_document(SAMPLE_PDF)
    assert document.kind == "pdf" and len(document.pages) >= 1

    values = extract_fields(
        document.text,
        [
            FieldDefinition(name="supplier", description="The name of the supplier"),
            FieldDefinition(name="order_date", type="date", description="The date of the order"),
        ],
        settings=SETTINGS,
    )

    print([item.model_dump() for item in values])
    supplier, order_date = values
    assert "Precision Steel" in str(supplier.value)
    assert supplier.evidence and supplier.evidence in document.text
    assert order_date.value == "2025-10-12"
    assert order_date.evidence and order_date.evidence in document.text


@pytest.mark.skipif(
    not os.getenv("AZURE_TRANSCRIPTION_MODEL", "").strip(),
    reason="live transcription test: set AZURE_TRANSCRIPTION_MODEL",
)
def test_transcribe_audio_returns_the_text_of_a_sample_recording(tmp_path):
    pytest.importorskip("pydub")

    transcript = transcribe_audio(
        SAMPLE_AUDIO,
        language="English",
        settings=OperationSettings(provider="azure", work_dir=tmp_path),
    )

    print(len(transcript.text), transcript.duration_s, transcript.model)
    assert len(transcript.text.split()) >= 5
    assert transcript.failed_segments == 0
    assert transcript.language == "English"
    assert transcript.model
    assert list(tmp_path.iterdir()) == []
