"""Numbers compare as numbers in ExtractionEvaluator, and the judge prompts can write them.

No network: the judges are fakes.
"""

from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import patch

import pytest
from gaik.software_components.evaluators import ExtractionEvaluator
from gaik.software_components.source_material import SourceMaterial
from gaik.software_components.validators.llm_judge import LLMJudge, compare_pairwise
from gaik.software_components.validators.llm_judge.prompts import (
    build_hallucination_prompt,
    build_text_pair_prompt,
    build_user_prompt,
)
from gaik.software_components.validators.llm_judge.schema import TextJudgement


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


@pytest.mark.parametrize(
    ("expected", "extracted", "matched"),
    [
        (19.99, Decimal("19.99"), True),
        ("19.99", Decimal("19.99"), True),
        (19.99, "19.99", True),
        (Decimal("340.00"), 340, True),
        ([1.5, 2], [Decimal("1.5"), Decimal("2")], True),
        ({"net": 10.0}, {"net": Decimal("10")}, True),
        (19.99, Decimal("19.98"), False),
        ("007", "7", False),  # two strings stay strings
        (True, 1, True),  # as before: True == 1
        (Decimal(19.99), 19.99, True),  # a Decimal made from the float, as before
        ([1, 2], (1, 2), False),  # as before: a list is not a tuple
        ("007", 7, False),  # a leading zero makes a code, not a number
        ("00100", 100, False),
        ("0401234567", 401234567, False),
        ("0", 0, True),
        ("0.5", 0.5, True),
    ],
)
def test_numbers_compare_as_numbers(expected, extracted, matched) -> None:
    result = ExtractionEvaluator().evaluate_item({"total": expected}, {"total": extracted})

    assert result.verdicts[0].matched is matched


class _TextJudge:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls = 0

    def judge_text_pair(self, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return TextJudgement(equivalent=False, severity="wrong", score=1, reason="differs")


def test_semantic_mode_scores_both_empty_without_a_call() -> None:
    judge = _TextJudge()
    evaluator = ExtractionEvaluator(match_mode="semantic", judge=judge)

    verdict = evaluator.evaluate_item({"city": None}, {"city": " "}).verdicts[0]

    assert verdict.matched and verdict.reason == "both empty" and judge.calls == 0


def test_semantic_mode_counts_a_judge_error_as_a_failed_match() -> None:
    judge = _TextJudge(ValueError("AZURE_API_KEY is not set"))
    evaluator = ExtractionEvaluator(match_mode="semantic", judge=judge)

    verdict = evaluator.evaluate_item({"city": "Helsinki"}, {"city": "Oslo"}).verdicts[0]

    assert not verdict.matched and verdict.score == 0
    assert verdict.reason == "judge call failed (ValueError)"


def _answer_block(prompt: str) -> str:
    return prompt.split('label="answer">\n', 1)[1].split("\n</source_material", 1)[0]


def test_the_prompt_builders_write_decimals_as_numbers() -> None:
    # A Decimal a float cannot hold exactly is written as its digits.
    extracted = {
        "total": Decimal("19.99"),
        "count": Decimal("3"),
        "exact": Decimal("12345678901234567890.123"),
    }

    for prompt in (
        build_user_prompt(extracted),
        build_hallucination_prompt("source", extracted),
    ):
        assert json.loads(_answer_block(prompt)) == {
            "total": 19.99,
            "count": 3,
            "exact": "12345678901234567890.123",
        }


def test_pairwise_and_validate_accept_decimals() -> None:
    judge, calls = _judge(['{"winner": "a", "score_a": 5, "score_b": 3, "reason": "r"}'])

    compare_pairwise(judge, [b"page"], {"total": Decimal("1.5")}, {"total": Decimal("2.5")})
    judge.validate([b"page"], {"total": Decimal("1.5")})

    assert all("1.5" in call["user"] for call in calls)


@pytest.mark.parametrize(("value", "shown"), [(None, "None"), (42, "42"), (Decimal("1.5"), "1.5")])
def test_a_value_that_is_not_text_is_wrapped_as_its_text(value, shown) -> None:
    prompt = build_text_pair_prompt(value, "expected", material=SourceMaterial("b" * 16))

    assert f'label="answer">\n{shown}\n</source_material' in prompt
