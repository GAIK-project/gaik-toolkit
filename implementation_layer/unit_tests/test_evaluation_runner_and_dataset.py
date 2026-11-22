"""The batch runner stops on Ctrl-C, and datasets load with a byte order mark."""

from __future__ import annotations

import pytest
from gaik.software_components.evaluators import BatchEvaluationRunner, EvaluationDataset


def test_ctrl_c_stops_the_run_instead_of_failing_one_item() -> None:
    def pipeline(item):
        raise KeyboardInterrupt

    runner = BatchEvaluationRunner(pipeline, on_error="skip")

    with pytest.raises(KeyboardInterrupt):
        runner.run(EvaluationDataset.from_list([{"input": "a"}, {"input": "b"}]))


def test_an_error_is_still_recorded_as_an_item_failure() -> None:
    def pipeline(item):
        raise ValueError(item.input)

    result = BatchEvaluationRunner(pipeline, on_error="skip").run(
        EvaluationDataset.from_list([{"input": "a"}])
    )

    assert result.n_failures == 1 and result.outputs == [None]


def test_a_dataset_saved_with_a_byte_order_mark_loads(tmp_path) -> None:
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("input,expected\nquestion,answer\n", encoding="utf-8-sig")
    jsonl_path = tmp_path / "data.jsonl"
    jsonl_path.write_text('{"input": "question", "expected": "answer"}\n', encoding="utf-8-sig")

    for dataset in (EvaluationDataset.from_csv(csv_path), EvaluationDataset.from_jsonl(jsonl_path)):
        assert [(item.input, item.expected) for item in dataset] == [("question", "answer")]
