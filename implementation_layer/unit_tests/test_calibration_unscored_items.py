"""Calibration leaves items without a judge score out of r and the means (#144, #134)."""

from __future__ import annotations

import pytest
from gaik.software_components.validators.llm_judge.calibration import (
    calibrate_against_human_labels,
)
from gaik.software_components.validators.llm_judge.schema import (
    CalibrationItem,
    JudgeUsage,
    ValidationFlag,
    ValidationResult,
)


class _ScriptedJudge:
    """Returns one prepared result per call, in order; no model is involved."""

    def __init__(self, results: list[ValidationResult]) -> None:
        self._results = iter(results)

    def validate(self, _pages, _extracted, _rubric):
        return next(self._results)


def _usage() -> JudgeUsage:
    return JudgeUsage(provider="fake", model="fake")


def _scored(score: int, field: str = "total") -> ValidationResult:
    flag = ValidationFlag(item_index=0, field=field, severity="ok", score=score)
    return ValidationResult(flags=[flag], raw_judge_text="{}", usage=_usage())


def _item(human: int, severity: str | None = None) -> CalibrationItem:
    return CalibrationItem(
        source_pages=[b"png"], extracted={"total": 1}, human_score=human, human_severity=severity
    )


def test_an_item_with_no_flag_for_the_field_is_left_out() -> None:
    judge = _ScriptedJudge([_scored(5), _scored(3), _scored(1), _scored(4, field="other")])
    dataset = [_item(5), _item(3), _item(1), _item(2)]

    report = calibrate_against_human_labels(judge, dataset, field_filter="total")

    assert report.n_items == 4
    assert report.pearson_r == pytest.approx(1.0)
    assert report.mean_judge_score == pytest.approx(3.0)
    assert report.mean_human_score == pytest.approx(3.0)
    assert report.per_item[3]["judge_score"] is None
    assert report.per_item[3]["skipped"] == "no scored flag"


def test_an_unreadable_judge_response_is_not_severity_ok() -> None:
    unreadable = ValidationResult(
        flags=[], raw_judge_text="not json", usage=_usage(), judge_error="unreadable response"
    )
    judge = _ScriptedJudge([unreadable])

    report = calibrate_against_human_labels(judge, [_item(4, severity="ok")])

    (row,) = report.per_item
    assert row["judge_severity"] is None
    assert row["judge_score"] is None
    assert row["skipped"] == "judge_error"
    assert row["judge_error"] == "unreadable response"
    assert report.severity_agreement_rate == 0.0
    assert report.mean_judge_score == 0.0
