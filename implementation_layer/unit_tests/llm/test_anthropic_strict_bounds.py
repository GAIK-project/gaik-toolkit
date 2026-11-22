"""Bounds a strict Claude tool cannot hold are stated in the schema, and an answer
that breaks only them is fitted rather than refused, on fields marked FIT_TO_BOUNDS
only: a caller's field is never changed (#146 item 8)."""

import json
import logging
import math
from typing import Annotated

import httpx
import pytest
from gaik.software_components.llm.base import FIT_TO_BOUNDS
from gaik.software_components.llm.config import get_llm_config
from gaik.software_components.llm.factory import create_llm_client
from pydantic import BaseModel, Field, ValidationError

pytest.importorskip("anthropic")

STRICT, PLAIN = "claude-sonnet-5", "claude-sonnet-4-6"


def _reply(name, data):
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-test",
        "content": [{"type": "tool_use", "id": "t", "name": name, "input": data}],
        "stop_reason": "tool_use",
        "stop_sequence": None,
        "usage": {"input_tokens": 8, "output_tokens": 3},
    }


def _config(model, name, data, bodies):
    def handle(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=_reply(name, data))

    return get_llm_config(
        "anthropic",
        api_key="test-key",
        model=model,
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handle)),
    )


def _ask(model, response_format, data, bodies=None):
    bodies = [] if bodies is None else bodies
    client = create_llm_client(_config(model, response_format.__name__, data, bodies))
    return client.chat_parsed([{"role": "user", "content": "Hi"}], response_format=response_format)


class Note(BaseModel):
    text: Annotated[str, FIT_TO_BOUNDS] = Field(max_length=5)


class Bounded(BaseModel):
    """Every bounded field opts in to fitting."""

    reasoning: Annotated[str, FIT_TO_BOUNDS] = Field(max_length=10, description="Why.")
    confidence: Annotated[float, FIT_TO_BOUNDS] = Field(ge=0, le=1)
    count: Annotated[int, FIT_TO_BOUNDS] = Field(gt=0)
    share: Annotated[float, FIT_TO_BOUNDS] = Field(gt=0, lt=1)
    comment: Annotated[str | None, FIT_TO_BOUNDS] = Field(None, max_length=3)
    tags: list[str] = Field(default_factory=list)
    note: Note | None = None


GOOD = {"reasoning": "short", "confidence": 0.5, "count": 2, "share": 0.5}


def test_an_answer_that_breaks_only_dropped_bounds_is_fitted(caplog):
    answer = {
        "reasoning": "x" * 25,
        "confidence": 1.4,
        "count": 0,
        "share": 1.0,
        "comment": "abcdef",
        "tags": ["a"],
    }
    with caplog.at_level(logging.WARNING):
        result = _ask(STRICT, Bounded, answer)
    assert result.reasoning == "x" * 10
    assert result.confidence == 1
    assert result.count == 1
    assert result.share == math.nextafter(1.0, 0) and result.share < 1
    assert result.comment == "abc"
    # The log names the fields, never their values.
    assert "reasoning" in caplog.text and "comment" in caplog.text
    assert "xxxxxxxxxx" not in caplog.text


def test_a_value_below_a_minimum_is_raised_to_it():
    result = _ask(STRICT, Bounded, {**GOOD, "confidence": -0.2, "share": 0.0})
    assert result.confidence == 0
    assert result.share > 0


@pytest.mark.parametrize(("answer", "fitted"), [(0.0, 1), (-3.0, 1)])
def test_an_int_field_answered_with_a_whole_float_gets_an_int(answer, fitted):
    """A JSON 0.0 for an int field with gt=0 becomes 1, not the smallest float."""
    result = _ask(STRICT, Bounded, {**GOOD, "count": answer})
    assert result.count == fitted and isinstance(result.count, int)


class Below(BaseModel):
    count: Annotated[int, FIT_TO_BOUNDS] = Field(lt=10)


def test_an_int_field_above_an_exclusive_maximum_gets_the_int_below():
    assert _ask(STRICT, Below, {"count": 10.0}).count == 9


def test_a_field_in_a_nested_model_that_opts_in_is_fitted():
    result = _ask(STRICT, Bounded, {**GOOD, "note": {"text": "too long"}})
    assert result.note.text == "too l"


class Invoice(BaseModel):
    """A caller's extraction schema: no field opts in."""

    invoice_number: str = Field(max_length=20)
    amount: float = Field(ge=0)
    reasoning: Annotated[str, FIT_TO_BOUNDS] = Field("", max_length=10)


@pytest.mark.parametrize(
    "answer",
    [
        {"invoice_number": "INV-" + "9" * 21, "amount": 10.0},
        {"invoice_number": "INV-1", "amount": -50.0},
        # One field that opts in does not open the others.
        {"invoice_number": "INV-" + "9" * 21, "amount": 10.0, "reasoning": "x" * 30},
    ],
)
def test_a_callers_field_is_never_changed(caplog, answer):
    with caplog.at_level(logging.WARNING), pytest.raises(ValidationError):
        _ask(STRICT, Invoice, answer)
    assert "fitted" not in caplog.text


def test_a_callers_field_still_gets_its_bounds_in_words():
    bodies = []
    _ask(STRICT, Invoice, {"invoice_number": "INV-1", "amount": 1.0}, bodies)
    properties = bodies[0]["tools"][0]["input_schema"]["properties"]
    assert properties["invoice_number"]["description"] == "At most 20 characters."
    assert properties["amount"]["description"] == "At least 0."


def test_a_field_in_a_list_is_not_fitted_even_when_it_opts_in():
    class Notes(BaseModel):
        notes: list[Note]

    with pytest.raises(ValidationError):
        _ask(STRICT, Notes, {"notes": [{"text": "too long"}]})


def test_the_marker_stays_out_of_the_schema():
    bodies = []
    _ask(STRICT, Bounded, GOOD, bodies)
    assert "FIT_TO_BOUNDS" not in json.dumps(bodies[0]["tools"][0])
    assert "FitToBounds" not in json.dumps(Bounded.model_json_schema())


def test_the_strict_schema_states_the_bounds_it_drops():
    bodies = []
    _ask(STRICT, Bounded, GOOD, bodies)
    properties = bodies[0]["tools"][0]["input_schema"]["properties"]
    assert "maxLength" not in json.dumps(properties)
    assert properties["reasoning"]["description"] == "Why. At most 10 characters."
    assert properties["confidence"]["description"] == "At least 0. At most 1."
    assert properties["count"]["description"] == "Greater than 0."
    assert properties["share"]["description"] == "Greater than 0. Less than 1."
    comment = [branch for branch in properties["comment"]["anyOf"] if branch["type"] == "string"]
    assert comment[0]["description"] == "At most 3 characters."
    note = bodies[0]["tools"][0]["input_schema"]["$defs"]["Note"]["properties"]["text"]
    assert note["description"] == "At most 5 characters."


def test_other_errors_still_raise():
    # A wrong type is not a bound, and nothing is fitted when one error is not.
    with pytest.raises(ValidationError):
        _ask(STRICT, Bounded, {**GOOD, "count": "many", "reasoning": "x" * 25})


class Minimum(BaseModel):
    code: str = Field(min_length=3)
    even: int = Field(multiple_of=2)


@pytest.mark.parametrize("answer", [{"code": "ab", "even": 2}, {"code": "abc", "even": 3}])
def test_a_minimum_length_or_a_multiple_is_not_invented(answer):
    with pytest.raises(ValidationError):
        _ask(STRICT, Minimum, answer)


def test_a_model_that_saw_the_bounds_is_held_to_them():
    with pytest.raises(ValidationError):
        _ask(PLAIN, Bounded, {**GOOD, "reasoning": "x" * 25})


class WithDefault(BaseModel):
    limits: dict[str, int] = Field(default={"maximum": 5})
    level: int = Field(3, le=9)


def test_a_default_value_is_left_as_it_is():
    bodies = []
    _ask(STRICT, WithDefault, {"limits": {}, "level": 3}, bodies)
    properties = bodies[0]["tools"][0]["input_schema"]["properties"]
    assert properties["limits"]["default"] == {"maximum": 5}
    assert properties["level"]["description"] == "At most 9."


def test_a_minimum_length_of_one_reads_as_one_character():
    class Label(BaseModel):
        label: str = Field(min_length=1, max_length=40)

    bodies = []
    _ask(STRICT, Label, {"label": "a"}, bodies)
    label = bodies[0]["tools"][0]["input_schema"]["properties"]["label"]
    assert label["description"] == "At least 1 character. At most 40 characters."


def test_generated_sql_with_long_reasoning_keeps_its_sql():
    from gaik.software_components.tabular_agent.models import GeneratedSQL

    sql = "SELECT COUNT(*) FROM orders"
    result = _ask(STRICT, GeneratedSQL, {"sql": sql, "reasoning": "because " * 100})
    assert result.sql == sql
    assert len(result.reasoning) == 500


@pytest.mark.parametrize(("confidence", "fitted"), [(0.9, 0.9), (1.2, 1.0), (95, 1.0), (-0.1, 0.0)])
def test_the_document_classifier_keeps_its_class(confidence, fitted):
    """Its own score and explanation opt in: a score past 0..1 or a long reasoning
    no longer turns the answer into 'unknown'."""
    from gaik.software_components.doc_classifier.classifier import DocumentClassifier

    answer = {"document_class": "invoice", "confidence": confidence, "reasoning": "y" * 300}
    classifier = DocumentClassifier(
        config=_config(STRICT, "ClassificationResult", answer, []), model=STRICT
    )
    result = classifier._classify_with_llm("Invoice 12", ["invoice", "receipt", "unknown"])
    assert result["class"] == "invoice"
    assert result["confidence"] == fitted
    assert len(result["reasoning"]) == 200
