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


# What Pydantic 2.12 and 2.13 emit for ``total_amount: Decimal | None`` (2.14 emits no
# pattern). Written out, so the test checks the fix whichever Pydantic is installed.
_PYDANTIC_212_INVOICE = {
    "type": "object",
    "title": "_Invoice",
    "properties": {
        "invoice_number": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None},
        "total_amount": {
            "anyOf": [
                {"type": "number"},
                {"type": "string", "pattern": r"^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$"},
                {"type": "null"},
            ],
            "default": None,
        },
    },
}


def test_pydantics_decimal_pattern_is_dropped_inside_anyof():
    strict = ve._make_schema_strict(_PYDANTIC_212_INVOICE)
    assert "(?!" not in json.dumps(strict)
    assert strict["properties"]["total_amount"]["anyOf"] == [
        {"type": "number"},
        {"type": "string"},
        {"type": "null"},
    ]


def test_the_installed_pydantics_decimal_schema_has_no_lookaround_either():
    assert "(?!" not in json.dumps(ve._make_schema_strict(_Invoice.model_json_schema()))


@pytest.mark.parametrize("pattern", [r"^(?!foo).*$", r"^[a-z(?=)]+$", r"^[A-Z]{2}-\d{4}$"])
def test_a_callers_own_pattern_stays(pattern):
    # A lookaround the caller wrote gets OpenAI's 400 naming it; nothing is guessed away.
    node = {"type": "string", "pattern": pattern}
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
    before = json.dumps(_PYDANTIC_212_INVOICE, sort_keys=True)
    ve._make_schema_strict(_PYDANTIC_212_INVOICE)
    assert json.dumps(_PYDANTIC_212_INVOICE, sort_keys=True) == before


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


@pytest.mark.parametrize(
    ("family", "override", "sent"),
    [("gpt-4o", "gpt-6-luna", True), ("gpt-6-luna", "gpt-4.1", False)],
)
def test_a_model_override_is_judged_by_its_own_name(monkeypatch, family, override, sent):
    # model_family describes api_config's model, not the model= that replaces it.
    config = {"api_key": "k", "model": "chat-prod", "model_family": family}
    extractor = ve.VisionExtractor(api_config=config, model=override, reasoning_effort="high")
    responses = _fake_client(monkeypatch, ve, '{"invoice_number": null, "total_amount": null}')

    extractor._call_openai([], "system", "user", _Invoice)

    assert responses.kwargs["model"] == override
    assert ("reasoning" in responses.kwargs) is sent


def test_the_config_family_decides_for_its_own_deployment(monkeypatch):
    config = {"api_key": "k", "model": "chat-prod", "model_family": "gpt-4o"}
    extractor = ve.VisionExtractor(api_config=config)
    responses = _fake_client(monkeypatch, ve, '{"invoice_number": null, "total_amount": null}')

    extractor._call_openai([], "system", "user", _Invoice)

    assert "reasoning" not in responses.kwargs


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
