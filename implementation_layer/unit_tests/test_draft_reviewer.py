"""Unit tests for DraftReviewer. Offline: ``create_llm_client`` is replaced by a fake."""

from __future__ import annotations

import pytest
from gaik.software_components.draft_reviewer import DraftReviewer, Edit, ReviewResult
from gaik.software_components.draft_reviewer import draft_reviewer as dr

CONFIG = {"provider": "openai", "api_key": "x", "model": "base-model"}
REFERENCE = "The bridge opened in 1998. It carries 45,000 vehicles a day."
DRAFT = "The bridge opened in 1999. It carries 40,000 vehicles a day. It was painted blue."


class _FakeClient:
    """Returns scripted responses in order and records the messages of each call."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[list[dict]] = []
        self.config: dict | None = None
        self.kwargs: list[dict] = []

    def chat_parsed(self, messages, response_format, **kwargs):
        assert response_format is dr.EditList
        self.calls.append(messages)
        self.kwargs.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture
def make(monkeypatch):
    def _make(*responses, **kwargs):
        client = _FakeClient(responses)

        def factory(config):
            client.config = config
            return client

        monkeypatch.setattr(dr, "create_llm_client", factory)
        return DraftReviewer(CONFIG, **kwargs), client

    return _make


def _edits(*edits: Edit) -> dr.EditList:
    return dr.EditList(edits=list(edits))


YEAR = Edit(search="opened in 1999", replace="opened in 1998", reason="The reference says 1998.")


def test_no_edits_returns_draft_unchanged(make):
    reviewer, client = make(_edits())
    result = reviewer.review(DRAFT, reference=REFERENCE)
    assert result == ReviewResult(text=DRAFT, applied=[], unresolved=[])
    [messages] = client.calls
    assert [m["role"] for m in messages] == ["system", "user", "user"]
    assert REFERENCE in messages[1]["content"]
    assert "supported by the reference material" in messages[1]["content"]
    assert DRAFT in messages[2]["content"]
    assert client.kwargs == [{}]


def test_chat_options_reach_every_request(make):
    bad = Edit(search="not in the draft", replace="x", reason="r")
    reviewer, client = make(_edits(bad), _edits(), chat_options={"reasoning_effort": "low"})
    reviewer.review(DRAFT, reference=REFERENCE)
    assert client.kwargs == [{"reasoning_effort": "low"}] * 2


def test_exact_edit_corrects_wrong_year(make):
    reviewer, client = make(_edits(YEAR))
    result = reviewer.review(DRAFT, reference=REFERENCE, instructions="Check only the years.")
    assert result.text == DRAFT.replace("1999", "1998")
    assert result.applied == [YEAR]
    assert result.applied[0].reason == "The reference says 1998."
    assert result.unresolved == []
    instruction = client.calls[0][1]["content"]
    assert "Check only the years." in instruction
    assert "supported by the reference material" not in instruction


def test_not_found_edit_is_retried_then_applied(make):
    traffic = Edit(search="40,000", replace="45,000", reason="The reference says 45,000.")
    typo = Edit(search="opened in 1990", replace="opened in 1998", reason="Wrong year.")
    reviewer, client = make(_edits(traffic, typo), _edits(YEAR))
    result = reviewer.review(DRAFT, reference=REFERENCE)
    assert result.text == DRAFT.replace("40,000", "45,000").replace("1999", "1998")
    assert result.applied == [traffic, YEAR]
    assert result.unresolved == []
    assert len(client.calls) == 2
    retry = client.calls[1][2]["content"]
    assert "'opened in 1990'" in retry
    assert "not found" in retry
    assert "It carries 45,000 vehicles a day." in retry


def test_ambiguous_search_fails_and_is_retried(make):
    draft = "The bridge opened in 1999. It was painted in 1999."
    ambiguous = Edit(search="1999", replace="1998", reason="Wrong year.")
    reviewer, client = make(_edits(ambiguous), _edits(YEAR))
    result = reviewer.review(draft, reference=REFERENCE)
    assert result.text == "The bridge opened in 1998. It was painted in 1999."
    assert result.applied == [YEAR]
    assert "found 2 times" in client.calls[1][2]["content"]


def test_edit_failing_every_attempt_is_unresolved(make):
    missing = Edit(search="opened in 2001", replace="opened in 1998", reason="Wrong year.")
    reviewer, client = make(*[_edits(missing)] * 3, max_attempts=3)
    result = reviewer.review(DRAFT, reference=REFERENCE)
    assert result == ReviewResult(text=DRAFT, applied=[], unresolved=[missing])
    assert len(client.calls) == 3


def test_empty_retry_answer_keeps_failed_edits_unresolved(make):
    missing = Edit(search="opened in 2001", replace="opened in 1998", reason="Wrong year.")
    reviewer, client = make(_edits(missing), _edits())
    result = reviewer.review(DRAFT, reference=REFERENCE)
    assert result == ReviewResult(text=DRAFT, applied=[], unresolved=[missing])
    assert len(client.calls) == 2


def test_empty_replace_deletes_passage(make):
    delete = Edit(search=" It was painted blue.", replace="", reason="Not in the reference.")
    reviewer, _ = make(_edits(delete))
    result = reviewer.review(DRAFT, reference=REFERENCE)
    assert result.text == "The bridge opened in 1999. It carries 40,000 vehicles a day."


def test_edits_apply_in_order(make):
    month = Edit(search="opened in 1998", replace="opened in May 1998", reason="Add month.")
    reviewer, _ = make(_edits(YEAR, month))
    result = reviewer.review(DRAFT, reference=REFERENCE)
    assert result.text.startswith("The bridge opened in May 1998.")
    assert result.applied == [YEAR, month]


@pytest.mark.parametrize(("draft", "reference"), [("", REFERENCE), (DRAFT, " \n")])
def test_empty_input_raises(make, draft, reference):
    reviewer, client = make()
    with pytest.raises(ValueError, match="is empty"):
        reviewer.review(draft, reference=reference)
    assert client.calls == []


def test_max_attempts_below_one_raises(make):
    with pytest.raises(ValueError, match="max_attempts"):
        make(max_attempts=0)


def test_model_override_reaches_client(make):
    _, client = make(model="override-model")
    assert client.config == {**CONFIG, "model": "override-model"}
    assert CONFIG["model"] == "base-model"
    _, client = make()
    assert client.config is CONFIG


def test_client_exception_propagates(make):
    reviewer, _ = make(RuntimeError("provider down"))
    with pytest.raises(RuntimeError, match="provider down"):
        reviewer.review(DRAFT, reference=REFERENCE)
