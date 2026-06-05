"""Unit tests for LLMJudge.judge_text_pair() and ExtractionEvaluator semantic mode."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from gaik.software_components.evaluators import ExtractionEvaluator
from gaik.software_components.evaluators.dataset import (
    EvaluationDataset,
    EvaluationItem,
)
from gaik.software_components.validators.llm_judge import (
    TEXT_PAIR_SYSTEM_PROMPT,
    LLMJudge,
    TextJudgement,
    build_text_pair_prompt,
    parse_text_judgement,
)

# ── parse_text_judgement ────────────────────────────────────────────


def test_parse_text_judgement_clean_json():
    raw = '{"equivalent": true, "severity": "ok", "score": 5, "reason": "identical"}'
    eq, sev, sc, reason = parse_text_judgement(raw)
    assert eq is True
    assert sev == "ok"
    assert sc == 5
    assert reason == "identical"


def test_parse_text_judgement_with_markdown_fence():
    raw = (
        '```json\n{"equivalent": false, "severity": "wrong", "score": 1, "reason": "diverges"}\n```'
    )
    eq, sev, sc, reason = parse_text_judgement(raw)
    assert eq is False
    assert sev == "wrong"
    assert sc == 1


def test_parse_text_judgement_clamps_score_to_5():
    raw = '{"equivalent": true, "severity": "ok", "score": 99, "reason": "high"}'
    _, _, sc, _ = parse_text_judgement(raw)
    assert sc == 5


def test_parse_text_judgement_unparseable_returns_wrong():
    raw = "this is not JSON"
    eq, sev, sc, reason = parse_text_judgement(raw)
    assert eq is False
    assert sev == "wrong"
    assert sc == 0
    assert reason.startswith("<unparseable")


def test_parse_text_judgement_invalid_severity_falls_back():
    raw = '{"equivalent": true, "severity": "AMAZING", "score": 5, "reason": "x"}'
    _, sev, _, _ = parse_text_judgement(raw)
    assert sev == "wrong"


# ── build_text_pair_prompt ──────────────────────────────────────────


def test_build_text_pair_prompt_includes_field_name_when_given():
    prompt = build_text_pair_prompt(
        extracted_text="foo",
        expected_text="bar",
        field_name="MyField",
    )
    assert "Field: MyField" in prompt
    assert "'foo'" in prompt
    assert "'bar'" in prompt


def test_build_text_pair_prompt_omits_field_when_none():
    prompt = build_text_pair_prompt(extracted_text="a", expected_text="b")
    assert "Field:" not in prompt
    assert "'a'" in prompt
    assert "'b'" in prompt


def test_text_pair_system_prompt_mentions_severity_levels():
    assert "ok" in TEXT_PAIR_SYSTEM_PROMPT
    assert "suspect" in TEXT_PAIR_SYSTEM_PROMPT
    assert "wrong" in TEXT_PAIR_SYSTEM_PROMPT


# ── LLMJudge.judge_text_pair ────────────────────────────────────────


def test_judge_text_pair_both_empty_raises():
    judge = LLMJudge(model_provider="azure")
    with pytest.raises(ValueError, match="empty"):
        judge.judge_text_pair("", "")


def test_judge_text_pair_returns_text_judgement():
    judge = LLMJudge(model_provider="azure")
    fake_response = '{"equivalent": true, "severity": "ok", "score": 5, "reason": "match"}'
    with patch.object(
        judge,
        "_dispatch_text",
        return_value=(fake_response, 50, 20),
    ) as dispatch:
        result = judge.judge_text_pair(
            extracted_text="kärsätrukin kärsästä puuttuu pultti",
            expected_text="Kärsätrukista puuttui pultti",
            field_name="Mitä tapahtui",
        )
    assert isinstance(result, TextJudgement)
    assert result.equivalent is True
    assert result.severity == "ok"
    assert result.score == 5
    assert result.usage.input_tokens == 50
    assert result.usage.output_tokens == 20
    assert result.usage.total_tokens == 70
    dispatch.assert_called_once()


def test_judge_text_pair_unparseable_response_returns_wrong():
    judge = LLMJudge(model_provider="azure")
    with patch.object(judge, "_dispatch_text", return_value=("not json", 10, 5)):
        result = judge.judge_text_pair("a", "b", field_name="X")
    assert result.equivalent is False
    assert result.severity == "wrong"
    assert result.score == 0


# ── ExtractionEvaluator semantic mode wired via judge_text_pair ─────


def test_extraction_evaluator_semantic_mode_calls_judge_text_pair():
    judge = LLMJudge(model_provider="azure")
    evaluator = ExtractionEvaluator(match_mode="semantic", judge=judge)

    expected = {"description": "Tietokonetta ei ollut lukittu."}
    extracted = {"description": "Tietokonetta ei oltu lukittu."}

    with patch.object(
        judge,
        "judge_text_pair",
        return_value=TextJudgement(
            equivalent=True,
            severity="ok",
            score=5,
            reason="same fact, minor wording",
            usage=MagicMock(),
        ),
    ) as judge_call:
        result = evaluator.evaluate_item(expected, extracted)

    judge_call.assert_called_once()
    assert result.metrics.f1 == 1.0
    assert result.verdicts[0].matched is True
    assert result.verdicts[0].score == 5


def test_extraction_evaluator_semantic_mode_low_score_not_match():
    judge = LLMJudge(model_provider="azure")
    evaluator = ExtractionEvaluator(match_mode="semantic", judge=judge)

    expected = {"description": "Foo"}
    extracted = {"description": "Bar"}

    with patch.object(
        judge,
        "judge_text_pair",
        return_value=TextJudgement(
            equivalent=False,
            severity="wrong",
            score=1,
            reason="different facts",
            usage=MagicMock(),
        ),
    ):
        result = evaluator.evaluate_item(expected, extracted)

    assert result.verdicts[0].matched is False
    assert result.verdicts[0].score == 1


def test_extraction_evaluator_semantic_mode_dataset_path():
    judge = LLMJudge(model_provider="azure")
    evaluator = ExtractionEvaluator(match_mode="semantic", judge=judge)
    dataset = EvaluationDataset.from_list(
        [
            EvaluationItem(input="t1", expected={"x": "alpha"}),
            EvaluationItem(input="t2", expected={"x": "beta"}),
        ]
    )

    with patch.object(
        judge,
        "judge_text_pair",
        return_value=TextJudgement(
            equivalent=True,
            severity="ok",
            score=5,
            reason="ok",
            usage=MagicMock(),
        ),
    ):
        result = evaluator.evaluate_dataset(dataset, [{"x": "alpha-prime"}, {"x": "beta-2"}])

    # Both items judged equivalent, so aggregate F1 should be 1.0.
    assert result.aggregate.f1 == 1.0
