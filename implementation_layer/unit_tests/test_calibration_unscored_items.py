"""Calibration leaves an item the judge did not score out of Pearson r and the means.

No network: the judge's provider call is a fake.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from gaik.software_components.validators.llm_judge import (
    CalibrationItem,
    LLMJudge,
    calibrate_against_human_labels,
)


def _judge(replies) -> tuple[LLMJudge, list[dict]]:
    """An LLMJudge whose provider call returns ``replies`` in turn and records each call."""
    judge = LLMJudge(model_provider="azure")
    calls: list[dict] = []
    replies = list(replies)

    def dispatch(source_pages, user_prompt, system_prompt):
        calls.append({"user": user_prompt, "system": system_prompt})
        return replies[min(len(calls) - 1, len(replies) - 1)], 10, 5

    patch.object(judge, "_dispatch", side_effect=dispatch).start()
    patch.object(
        judge, "_dispatch_text", side_effect=lambda user, system: dispatch([], user, system)
    ).start()
    return judge, calls


def teardown_function():
    patch.stopall()


def _flags(*flags: tuple[str, int]) -> str:
    return json.dumps(
        {
            "flags": [
                {"item_index": 0, "field": field, "severity": "ok", "score": score, "reason": field}
                for field, score in flags
            ]
        }
    )


def _calibration_items(scores: list[int]) -> list[CalibrationItem]:
    return [
        CalibrationItem(source_pages=[b"p"], extracted={"total": 1}, human_score=s) for s in scores
    ]


def test_an_item_without_a_score_is_left_out_of_r_and_the_means() -> None:
    replies = [
        _flags(("total", 1)),
        _flags(("total", 2)),
        _flags(("total", 4)),
        _flags(("other", 5)),  # no flag for the field: unscored, not 0
    ]
    judge, _ = _judge(replies)

    report = calibrate_against_human_labels(
        judge, _calibration_items([1, 2, 4, 5]), field_filter="total"
    )

    assert report.pearson_r == pytest.approx(1.0)
    assert report.mean_judge_score == pytest.approx(7 / 3)
    assert report.mean_human_score == pytest.approx(7 / 3)
    assert report.n_items == 4
    assert [p["scored"] for p in report.per_item] == [True, True, True, False]
    assert report.per_item[3]["judge_score"] == 0.0  # as before; "scored" tells it apart


def test_an_unreadable_reply_is_not_an_ok_verdict() -> None:
    judge, _ = _judge(["not json", _flags(("total", 5)), _flags(("total", 1))])
    items = [
        CalibrationItem(source_pages=[b"p"], extracted={}, human_score=1, human_severity="wrong"),
        CalibrationItem(source_pages=[b"p"], extracted={}, human_score=5, human_severity="ok"),
        CalibrationItem(source_pages=[b"p"], extracted={}, human_score=1, human_severity="wrong"),
    ]

    report = calibrate_against_human_labels(judge, items)

    first = report.per_item[0]
    assert first["scored"] is False and first["judge_severity"] is None
    assert first["judge_error"].startswith("response is not JSON")
    # Only the two readable verdicts count: one agrees, one does not.
    assert report.severity_agreement_rate == pytest.approx(0.5)


def test_a_reply_read_only_in_part_is_left_out() -> None:
    # The low-scoring flag has an unknown severity and is dropped: the rest is not the verdict.
    reply = json.dumps(
        {
            "flags": [
                {"field": "vendor", "severity": "ok", "score": 5},
                {"field": "total", "severity": "bad", "score": 1},
            ]
        }
    )
    judge, _ = _judge([reply, _flags(("total", 2)), _flags(("total", 4))])
    items = _calibration_items([1, 2, 4])

    report = calibrate_against_human_labels(judge, items)

    first = report.per_item[0]
    assert first["scored"] is False and first["judge_severity"] is None
    assert first["judge_error"] == "1 of 2 flags could not be read"
    assert report.pearson_r == pytest.approx(1.0)
