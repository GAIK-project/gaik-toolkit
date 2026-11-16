"""The Extractor demo's fields mode: the model and the field specs use the same names."""

import asyncio

import pytest
from api.routers import extractor
from fastapi import HTTPException


def _extract(monkeypatch, fields):
    seen = {}

    class FakeExtractor:
        def __init__(self, *args, **kwargs):
            pass

    async def run_extraction(_extractor, model, requirements, *args):
        seen["model"] = list(model.model_fields)
        seen["specs"] = [spec.field_name for spec in requirements.fields]
        return extractor.ExtractResponse(results=[], document_count=1)

    monkeypatch.setattr("gaik.software_components.extractor.DataExtractor", FakeExtractor)
    monkeypatch.setattr(extractor, "get_api_config", lambda: {"model": "m"})
    monkeypatch.setattr(extractor, "get_model_options", lambda config: {})
    monkeypatch.setattr(extractor, "_run_extraction", run_extraction)
    request = extractor.ExtractRequest(documents=["text"], user_requirements="x", fields=fields)
    asyncio.run(extractor.extract_data(request))
    return seen


def test_the_model_uses_the_normalised_field_names(monkeypatch):
    seen = _extract(monkeypatch, {"unit-price": "Price", "total_(eur)": "Total"})
    assert seen["model"] == seen["specs"] == ["unit_price", "total_eur"]


def test_two_names_for_the_same_field_are_a_bad_request(monkeypatch):
    with pytest.raises(HTTPException) as caught:
        _extract(monkeypatch, {"unit-price": "Price", "unit_price": "Price again"})
    assert caught.value.status_code == 400
