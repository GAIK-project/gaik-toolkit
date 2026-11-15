"""A judge response that cannot be read is reported as such, never as a pass."""

from __future__ import annotations

from unittest.mock import patch

from gaik.software_components.validators.llm_judge import LLMJudge, LLMJudgePanel
from gaik.software_components.validators.llm_judge.panel import _agreement_score
from gaik.software_components.validators.llm_judge.schema import ValidationFlag

PAGE = [b"\x89PNG page"]
EXTRACTED = {"name": "A", "total": "10"}
NO_FLAGS = '{"flags": []}'
TOTAL_WRONG = '{"flags": [{"item_index": 0, "field": "total", "severity": "wrong"}]}'


def _judge(reply: str) -> LLMJudge:
    judge = LLMJudge(model_provider="azure")
    patch.object(judge, "_dispatch", return_value=(reply, 10, 5)).start()
    patch.object(judge, "_dispatch_text", return_value=(reply, 10, 5)).start()
    return judge


def teardown_function():
    patch.stopall()


def test_a_readable_empty_verdict_passes():
    result = _judge(NO_FLAGS).validate(PAGE, EXTRACTED)
    assert result.judge_error is None
    assert result.passed


def test_a_response_that_is_not_json_is_an_error_not_a_pass():
    result = _judge("I could not decide.").validate(PAGE, EXTRACTED)
    assert result.flags == []
    assert result.judge_error and "not JSON" in result.judge_error
    assert not result.passed


def test_a_json_response_without_a_flags_list_is_an_error():
    result = _judge('{"verdict": "fine"}').validate(PAGE, EXTRACTED)
    assert result.judge_error == "response has no flags list"
    assert not result.passed


def test_the_error_names_the_size_but_not_the_content():
    result = _judge("the total 4711 looks fine to me").validate(PAGE, EXTRACTED)
    assert "4711" not in result.judge_error


def test_a_flagged_field_does_not_pass():
    result = _judge(TOTAL_WRONG).validate(PAGE, EXTRACTED)
    assert result.judge_error is None
    assert not result.passed


def test_a_flag_with_an_unknown_severity_is_an_error_not_a_pass():
    reply = '{"flags": [{"item_index": 0, "field": "total", "severity": "critical"}]}'
    result = _judge(reply).validate(PAGE, EXTRACTED)
    assert result.flags == []
    assert result.judge_error == "1 of 1 flags could not be read"
    assert not result.passed


def test_a_flag_that_is_not_an_object_is_an_error_and_readable_flags_are_kept():
    reply = '{"flags": ["total is wrong", {"item_index": 0, "field": "name", "severity": "ok"}]}'
    result = _judge(reply).validate(PAGE, EXTRACTED)
    assert [f.field for f in result.flags] == ["name"]
    assert result.judge_error == "1 of 2 flags could not be read"
    assert not result.passed


def test_an_unreadable_hallucination_flag_is_an_error_but_an_ok_flag_is_not():
    unknown = '{"flags": [{"field": "total", "value": "10", "severity": "critical"}]}'
    no_field = '{"flags": [{"value": "10", "severity": "wrong"}]}'
    for reply in (unknown, no_field):
        report = _judge(reply).detect_hallucinations("source text", EXTRACTED)
        assert report.judge_error == "1 of 1 flags could not be read"
        assert not report.passed
    ok = '{"flags": [{"field": "total", "value": "10", "severity": "ok"}]}'
    report = _judge(ok).detect_hallucinations("source text", EXTRACTED)
    assert report.flags == [] and report.judge_error is None
    assert report.passed


def test_an_unreadable_hallucination_verdict_is_an_error():
    report = _judge("no idea").detect_hallucinations("source text", EXTRACTED)
    assert report.flags == [] and report.judge_error
    assert not report.passed
    assert _judge(NO_FLAGS).detect_hallucinations("source text", EXTRACTED).passed


def test_a_panel_with_an_unreadable_judge_does_not_pass():
    panel = LLMJudgePanel([_judge(NO_FLAGS), _judge("garbled"), _judge(NO_FLAGS)])
    result = panel.validate(PAGE, EXTRACTED)
    assert len(result.judge_errors) == 1
    assert result.aggregated_flags == []
    assert not result.passed


def test_a_panel_whose_judges_all_fail_has_no_agreement():
    result = LLMJudgePanel([_judge("x"), _judge("y")]).validate(PAGE, EXTRACTED)
    assert result.agreement_score == 0.0
    assert not result.passed


def test_a_panel_of_readable_empty_verdicts_passes_with_full_agreement():
    result = LLMJudgePanel([_judge(NO_FLAGS), _judge(NO_FLAGS)]).validate(PAGE, EXTRACTED)
    assert result.passed and result.agreement_score == 1.0


def _flag(field: str, severity: str) -> ValidationFlag:
    return ValidationFlag(item_index=0, field=field, severity=severity)


def test_a_field_one_judge_flags_and_another_passes_is_a_disagreement():
    assert _agreement_score([[_flag("total", "wrong")], []]) == 0.0
    assert _agreement_score([[_flag("total", "wrong")], [_flag("total", "wrong")]]) == 1.0
    assert _agreement_score([[_flag("total", "ok")], []]) == 1.0
