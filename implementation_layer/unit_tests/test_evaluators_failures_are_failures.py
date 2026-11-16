"""Evaluator inputs and failures that used to be read as success (issue #144)."""

from __future__ import annotations

import pytest
from gaik.software_components.evaluators.dataset import EvaluationDataset
from gaik.software_components.evaluators.extraction_evaluator import ExtractionEvaluator
from gaik.software_components.evaluators.runner import BatchEvaluationRunner


class _MisconfiguredJudge:
    """A judge whose provider is not configured: every call raises ValueError."""

    def __init__(self) -> None:
        self.calls = 0

    def judge_text_pair(self, **_kwargs):
        self.calls += 1
        raise ValueError("Missing required environment variable: AZURE_API_KEY")


def test_a_judge_configuration_error_is_not_a_match() -> None:
    judge = _MisconfiguredJudge()
    evaluator = ExtractionEvaluator(match_mode="semantic", judge=judge)

    result = evaluator.evaluate_item({"city": "Helsinki"}, {"city": "Oslo"})

    assert judge.calls == 1
    (verdict,) = result.verdicts
    assert verdict.matched is False
    assert verdict.reason == "judge call failed"
    assert result.metrics.f1 == 0.0


def test_two_empty_values_match_without_calling_the_judge() -> None:
    judge = _MisconfiguredJudge()
    evaluator = ExtractionEvaluator(match_mode="semantic", judge=judge)

    score, reason = evaluator._semantic_match("note", "", " ")

    assert (score, reason) == (5, "both empty")
    assert judge.calls == 0


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
def test_an_interrupt_stops_the_runner_instead_of_failing_one_item(interrupt) -> None:
    def pipeline(_item):
        raise interrupt()

    runner = BatchEvaluationRunner(pipeline, on_error="skip")
    dataset = EvaluationDataset.from_list([{"input": "a"}, {"input": "b"}])

    with pytest.raises(interrupt):
        runner.run(dataset)


def test_an_ordinary_error_is_still_recorded_and_skipped() -> None:
    def pipeline(item):
        if item.input == "a":
            raise RuntimeError("boom")
        return "ok"

    result = BatchEvaluationRunner(pipeline, on_error="skip").run(
        EvaluationDataset.from_list([{"input": "a"}, {"input": "b"}])
    )

    assert [idx for idx, _ in result.failures] == [0]
    assert result.outputs == [None, "ok"]


def test_a_csv_saved_with_a_byte_order_mark_loads(tmp_path) -> None:
    path = tmp_path / "dataset.csv"
    path.write_text("input,expected\nquestion,answer\n", encoding="utf-8-sig")

    dataset = EvaluationDataset.from_csv(path)

    assert [item.input for item in dataset] == ["question"]


def test_a_jsonl_saved_with_a_byte_order_mark_loads(tmp_path) -> None:
    path = tmp_path / "dataset.jsonl"
    path.write_text('{"input": "question"}\n', encoding="utf-8-sig")

    dataset = EvaluationDataset.from_jsonl(path)

    assert [item.input for item in dataset] == ["question"]
