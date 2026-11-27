"""VisionExtractor's and MultimodalParser's OpenAI requests -- no LLM calls.

Two 400s from the Responses API on Azure, both checked live on 27 Nov 2026:
- a hand-written model with a ``Decimal | None`` field: "Invalid JSON schema: regex
  lookaround is not supported" (Pydantic's Decimal pattern, inside an anyOf branch);
- a GPT-4.1 deployment: "Unsupported parameter: 'reasoning.effort' is not supported with
  this model."
"""

from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
from gaik.software_components.parsers.multimodal_parser import multimodal_parser as mp
from gaik.software_components.vision_extractor import vision_extractor as ve
from pydantic import BaseModel


class _Invoice(BaseModel):
    invoice_number: str | None = None
    total_amount: Decimal | None = None


def test_a_decimal_field_leaves_no_lookaround_in_the_strict_schema():
    strict = ve._make_schema_strict(_Invoice.model_json_schema())
    text = json.dumps(strict)
    assert "(?!" not in text and "(?=" not in text
    branches = strict["properties"]["total_amount"]["anyOf"]
    assert {b.get("type") for b in branches} == {"number", "string", "null"}


@pytest.mark.parametrize("pattern", [r"(?=x)", r"(?!x)", r"(?<=x)", r"(?<!x)"])
def test_every_lookaround_pattern_is_dropped(pattern):
    node = {"type": "string", "pattern": pattern, "description": "kept"}
    assert ve._make_schema_strict(node) == {"type": "string", "description": "kept"}


def test_an_ordinary_pattern_stays():
    node = {"type": "string", "pattern": r"^[A-Z]{2}-\d{4}$"}
    assert ve._make_schema_strict(node) == node


def test_objects_inside_anyof_are_made_strict():
    schema = {
        "anyOf": [
            {"type": "object", "properties": {"a": {"type": "string"}}},
            {"type": "null"},
        ]
    }
    branch = ve._make_schema_strict(schema)["anyOf"][0]
    assert branch["additionalProperties"] is False
    assert branch["required"] == ["a"]


def test_a_ref_still_keeps_no_sibling_keywords():
    assert ve._make_schema_strict({"$ref": "#/$defs/X", "description": "x"}) == {
        "$ref": "#/$defs/X"
    }


def test_the_callers_schema_is_not_changed():
    schema = _Invoice.model_json_schema()
    before = json.dumps(schema, sort_keys=True)
    ve._make_schema_strict(schema)
    assert json.dumps(schema, sort_keys=True) == before


class _Responses:
    def __init__(self, text: str):
        self.text = text
        self.kwargs: dict = {}

    def create(self, **kwargs):
        self.kwargs = kwargs
        usage = SimpleNamespace(input_tokens=10, output_tokens=5, total_tokens=15)
        return SimpleNamespace(output_text=self.text, usage=usage, status="completed")


def _fake_client(monkeypatch, module, text: str) -> _Responses:
    responses = _Responses(text)
    client = SimpleNamespace(responses=responses, close=lambda: None)
    monkeypatch.setattr(module, "create_openai_client", lambda config: client)
    return responses


@pytest.mark.parametrize(
    ("model", "sent"),
    [("gpt-6-luna", True), ("gpt-5.4-mini", True), ("my-deployment", True), ("gpt-4.1", False)],
)
def test_vision_extractor_sends_reasoning_only_to_models_that_take_it(monkeypatch, model, sent):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    extractor = ve.VisionExtractor(model_provider="openai", use_azure=False, model=model)
    responses = _fake_client(monkeypatch, ve, '{"invoice_number": "A-1", "total_amount": null}')

    result, _usage = extractor._call_openai([], "system", "user", _Invoice)

    assert result == {"invoice_number": "A-1", "total_amount": None}
    assert ("reasoning" in responses.kwargs) is sent
    if sent:
        assert responses.kwargs["reasoning"] == {"effort": extractor.reasoning_effort}
    schema = json.dumps(responses.kwargs["text"]["format"]["schema"])
    assert "(?!" not in schema


@pytest.mark.parametrize(("model", "sent"), [("gpt-6-luna", True), ("gpt-4o", False)])
def test_multimodal_parser_sends_reasoning_only_to_models_that_take_it(
    monkeypatch, tmp_path, model, sent
):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    parser = mp.MultimodalParser(model_provider="openai", use_azure=False, model=model)
    responses = _fake_client(monkeypatch, mp, "# Page")
    monkeypatch.setattr(mp, "_build_openai_content", lambda path, prompt: [])

    parser._call_openai(tmp_path / "doc.pdf", "system", "user")

    assert ("reasoning" in responses.kwargs) is sent
