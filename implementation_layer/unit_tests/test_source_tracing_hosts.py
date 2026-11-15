"""Source tracing against the four components it works around.

The language model is replaced by a fake that answers the way a model that follows the
instruction would: it fills the model it was handed, including ``field_sources``. Everything
else is the real component, so these tests show that each host passes the evidence through
its own post-processing, and that the component can then check it. No host is modified.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from gaik.software_components.extractor import (
    ChildRequirements,
    CompositeExtractionRequirements,
    DataExtractor,
    ExtractionRequirements,
    FieldSpec,
)
from gaik.software_components.extractor import extractor as extractor_module
from gaik.software_components.extractor.schema import _create_parent_with_nested_list_model
from gaik.software_components.source_tracing import SOURCES_FIELD, SourceTracing, transcript_used
from pydantic import BaseModel

EXAMPLES = Path(__file__).parent.parent / "examples" / "software_components" / "source_tracing"
CONFIG = {"provider": "openai", "api_key": "test-key", "model": "test-model"}

TEXT = "Invoice no. 100234\nTotal: 1.234,50 EUR\nLine 1: Bolt M8 x 4 pcs\nLine 2: Nut M8 x 8 pcs"


def _cite(field: str, quote: str, document: int = 1, page: int = 1) -> dict:
    return {"field": field, "document": document, "page": page, "quote": quote}


def _spec(name: str, kind: str) -> FieldSpec:
    return FieldSpec(field_name=name, field_type=kind, description=name)


def _reqs(name: str, *fields: FieldSpec) -> ExtractionRequirements:
    return ExtractionRequirements(use_case_name=name, fields=list(fields))


def _fake_model_call(monkeypatch: pytest.MonkeyPatch, payload: dict) -> dict:
    """Make the extractor's model call return ``payload`` validated against the model it got."""
    seen: dict = {}

    def fake_parse_with(**kwargs):
        seen["model"] = kwargs["response_format"]
        seen["prompt"] = kwargs["messages"][-1]["content"]
        parsed = kwargs["response_format"].model_validate(payload)
        message = SimpleNamespace(parsed=parsed)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)

    monkeypatch.setattr(extractor_module, "_parse_with", fake_parse_with)
    return seen


class Flat(BaseModel):
    number: str | None = None
    total: float | None = None


class Row(BaseModel):
    description: str | None = None
    quantity: int | None = None


class WithRows(BaseModel):
    number: str | None = None
    lines: list[Row] = []


FLAT_REQS = _reqs("flat", _spec("number", "str"), _spec("total", "float"))
ROW_REQS = _reqs("rows", _spec("description", "str"), _spec("quantity", "int"))


def _data_extractor() -> DataExtractor:
    return DataExtractor(config=CONFIG)


def test_data_extractor_flat_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "number": "100234",
        "total": 1234.5,
        SOURCES_FIELD: {
            "items": [
                _cite("number", "Invoice no. 100234"),
                _cite("total", "Total: 1.234,50 EUR"),
            ]
        },
    }
    seen = _fake_model_call(monkeypatch, payload)
    st = SourceTracing()
    task = st.augment(Flat, "Extract the invoice", source="text")

    results = _data_extractor().extract(
        extraction_model=task.model,
        requirements=FLAT_REQS,
        user_requirements=task.prompt,
        documents=[TEXT],
    )
    clean, report = st.check_text(results, [TEXT])

    assert "SOURCE CITATIONS" in seen["prompt"]
    assert clean == [{"number": "100234", "total": 1234.5}]
    assert report.summary()["verified"] == 2 and report.coverage == 1.0
    assert set(Flat.model_fields) == {"number", "total"}  # the caller's model is unchanged


def test_data_extractor_rows_keep_their_citations_and_record_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "number": "100234",
        "lines": [
            {"description": "Bolt M8", "quantity": 4},
            {"description": "Nut M8", "quantity": 8},
        ],
        SOURCES_FIELD: {
            "items": [
                _cite("number", "Invoice no. 100234"),
                _cite("lines[0].quantity", "Bolt M8 x 4 pcs"),
                _cite("lines[1].quantity", "Nut M8 x 8 pcs"),
                _cite("lines[1].description", "Nut M8"),
            ]
        },
    }
    _fake_model_call(monkeypatch, payload)
    st = SourceTracing()
    task = st.augment(WithRows, "Extract the invoice lines", source="text")

    results = _data_extractor().extract(
        extraction_model=task.model,
        requirements=ROW_REQS,
        user_requirements=task.prompt,
        documents=[TEXT],
    )
    clean, report = st.check_text(results, [TEXT])

    # The evidence is not mistaken for table rows and not lost.
    assert SOURCES_FIELD not in clean[0]
    assert [row["quantity"] for row in clean[0]["lines"]] == [4, 8]
    assert [item.verdict for item in report.items] == ["verified"] * 4
    # A value every record shares has no record number; a row's values have their row's.
    assert [item.record for item in report.items] == [None, 0, 1, 1]
    # Four of the five values have evidence: lines[0].description has none.
    assert report.coverage == pytest.approx(4 / 5)


def test_data_extractor_parent_with_nested_list_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    parent = _reqs("parent", _spec("number", "str"))
    child = ChildRequirements(
        container_name="lines", container_description="Lines", requirements=ROW_REQS
    )
    model = _create_parent_with_nested_list_model(parent_requirements=parent, children=[child])
    requirements = CompositeExtractionRequirements(parent_requirements=parent, children=[child])
    payload = {
        "number": "100234",
        "lines": [{"description": "Bolt M8", "quantity": 4}],
        SOURCES_FIELD: {
            "items": [
                _cite("number", "Invoice no. 100234"),
                _cite("lines[0].quantity", "Bolt M8 x 4 pcs"),
            ]
        },
    }
    _fake_model_call(monkeypatch, payload)
    st = SourceTracing()
    task = st.augment(model, "Extract the invoice", source="text")

    results = _data_extractor().extract(
        extraction_model=task.model,
        requirements=requirements,
        user_requirements=task.prompt,
        documents=[TEXT],
    )
    clean, report = st.check_text(results, [TEXT])

    assert clean[0]["lines"][0]["quantity"] == 4
    assert [item.verdict for item in report.items] == ["verified", "verified"]


def test_data_extractor_several_documents_pair_results_with_their_texts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answers = iter(
        [
            {"number": "1", SOURCES_FIELD: {"items": [_cite("number", "Order 1")]}},
            {"number": "2", SOURCES_FIELD: {"items": [_cite("number", "Order 3")]}},
        ]
    )

    def fake_parse_with(**kwargs):
        parsed = kwargs["response_format"].model_validate(next(answers))
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))], usage=None
        )

    monkeypatch.setattr(extractor_module, "_parse_with", fake_parse_with)
    st = SourceTracing()
    task = st.augment(Flat, "Extract the number", source="text")
    texts = ["Order 1", "Order 2"]

    results = _data_extractor().extract(
        extraction_model=task.model,
        requirements=FLAT_REQS,
        user_requirements=task.prompt,
        documents=texts,
    )
    _, report = st.check_text(results, texts)

    assert [item.verdict for item in report.items] == ["verified", "check"]
    assert [item.document for item in report.items] == [1, 2]


# --- VisionExtractor ---------------------------------------------------------------------


def _vision_extractor(monkeypatch: pytest.MonkeyPatch, payload: dict, **kwargs):
    from gaik.software_components.vision_extractor import VisionExtractor

    extractor = VisionExtractor(api_config=CONFIG, **kwargs)
    seen: dict = {}

    def fake_extract(file_paths, model, user_requirements):
        seen.update(model=model, prompt=user_requirements)
        return model.model_validate(_for(model, payload)).model_dump(), None

    monkeypatch.setattr(extractor, "_extract", fake_extract)
    return extractor, seen


def _for(model: type[BaseModel], payload: dict) -> dict:
    """The payload in the shape of ``model``: wrapped per value when verification is on."""
    if not any(name.endswith("_Verifiable") for name in [model.__name__]):
        return payload

    def wrap(value):
        return {"value": value, "confidence_score": 0.9, "confidence_reason": "stated"}

    wrapped: dict = {}
    for name, value in payload.items():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            wrapped[name] = [{key: wrap(item) for key, item in row.items()} for row in value]
        elif isinstance(value, list):
            wrapped[name] = value
        else:
            wrapped[name] = wrap(value)
    return wrapped


@pytest.mark.parametrize("verification", [False, True])
def test_vision_extractor_with_and_without_verification(
    monkeypatch: pytest.MonkeyPatch, verification: bool
) -> None:
    pdf = EXAMPLES / "PO.pdf"
    payload = {
        "number": "560471823",
        "total": 0.0,
        SOURCES_FIELD: [_cite("number", "Document No. 560471823")],
    }
    extractor, seen = _vision_extractor(monkeypatch, payload, include_verification=verification)
    st = SourceTracing()
    task = st.augment(Flat, "Extract the purchase number", source="files")

    result = extractor.extract(
        file_paths=[pdf],
        user_requirements=task.prompt,
        extraction_model=task.model,
        requirements=FLAT_REQS,
    )
    clean, report = st.check_pdf(result.data, [pdf])

    assert "counting the attached files from 1" in seen["prompt"]
    item = report.items[0]
    assert item.field == "number" and item.verdict == "verified"
    assert item.rects and item.page == 1
    # The value is compared bare, not as its confidence envelope; one of two values is cited.
    assert item.value == "560471823" and report.coverage == 0.5
    # The evidence is gone from the data; with verification on, the values keep their
    # confidence envelopes, as without source tracing.
    assert SOURCES_FIELD not in clean
    if verification:
        assert clean["number"]["value"] == "560471823"
    else:
        assert clean["number"] == "560471823"


# --- the two modules ------------------------------------------------------------------------


def test_documents_to_structured_data_with_a_supplied_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gaik.software_modules.documents_to_structured_data import DocumentsToStructuredData

    pdf = EXAMPLES / "PO2.pdf"
    payload = {
        "number": "7200445321",
        "total": 0.0,
        SOURCES_FIELD: {"items": [_cite("number", "PURCHASE NO: 7200445321")]},
    }
    seen = _fake_model_call(monkeypatch, payload)
    st = SourceTracing()
    task = st.augment(Flat, "Extract the purchase number", source="text")

    pipeline = DocumentsToStructuredData(api_config=CONFIG)
    result = pipeline.run(
        file_path=pdf,
        user_requirements=task.prompt,
        parser_choice="pymupdf",
        schema=task.model,
        requirements=FLAT_REQS,
    )
    clean, report = st.check_text(result.extracted_fields, result.parsed_documents)

    assert "SOURCE CITATIONS" in seen["prompt"]
    assert clean[0]["number"] == "7200445321"
    assert report.items[0].verdict == "verified"


@pytest.mark.parametrize("enhanced", [None, "Invoice no. 100234. Total: 1.234,50 EUR"])
def test_audio_to_structured_data_checks_the_transcript_it_read(
    monkeypatch: pytest.MonkeyPatch, enhanced: str | None
) -> None:
    from gaik.software_modules.audio_to_structured_data import pipeline as audio_pipeline

    raw = (
        "invoice number one hundred thousand two hundred thirty four total one two three four euro"
    )
    transcription = SimpleNamespace(raw_transcript=raw, enhanced_transcript=enhanced)
    monkeypatch.setattr(
        audio_pipeline,
        "Transcriber",
        lambda **kwargs: SimpleNamespace(transcribe=lambda **kw: transcription),
    )
    quote = "Total: 1.234,50 EUR" if enhanced else "total one two three four euro"
    payload = {
        "number": "100234",
        "total": 1234.5,
        SOURCES_FIELD: {"items": [_cite("total", quote)]},
    }
    _fake_model_call(monkeypatch, payload)
    st = SourceTracing()
    task = st.augment(Flat, "Extract the invoice", source="text")

    result = audio_pipeline.AudioToStructuredData(api_config=CONFIG).run(
        file_path="synthetic.mp3",
        user_requirements=task.prompt,
        schema=task.model,
        requirements=FLAT_REQS,
    )
    clean, report = st.check_text(result.extracted_fields, transcript_used(result))

    assert transcript_used(result) == (enhanced or raw)
    assert clean[0]["total"] == 1234.5
    assert report.items[0].status == "found"
    # In the raw transcript the number is in words, so only the quote can be checked.
    assert report.items[0].verdict == ("verified" if enhanced else "unchecked")
