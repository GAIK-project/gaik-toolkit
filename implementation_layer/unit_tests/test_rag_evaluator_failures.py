"""RAGEvaluator scores each metric from its own flag and reports what the judge did not score.

No network: the judge's provider call is a fake.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from gaik.software_components.evaluators import RAGEvaluator, RAGItemResult
from gaik.software_components.evaluators.rag_evaluator import _aggregate
from gaik.software_components.validators.llm_judge import LLMJudge


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


def test_each_metric_reads_the_flag_for_its_own_field() -> None:
    judge, _ = _judge(
        [
            _flags(("query", 5), ("faithfulness", 2)),
            _flags(("Answer Relevance", 4)),
            _flags(("query", 5), ("answer", 1)),  # no flag for context_precision
        ]
    )

    item = RAGEvaluator(judge).evaluate_item(query="q", answer="a", context=["c"])

    assert item.faithfulness_score == 2 and item.reasons["faithfulness"] == "faithfulness"
    assert item.answer_relevance_score == 4
    assert item.context_precision_score == 0
    assert item.errors == {"context_precision": "judge gave no score for context_precision"}


def test_an_unreadable_reply_reports_the_judge_error() -> None:
    judge, _ = _judge(["Looks good to me."])

    item = RAGEvaluator(judge).evaluate_item(query="q", answer="a", context=["c"])

    assert item.faithfulness_score == 0
    assert item.errors["faithfulness"].startswith("response is not JSON")


def test_a_failed_judge_call_is_an_error_not_a_score() -> None:
    judge = LLMJudge(model_provider="azure")
    patch.object(judge, "_dispatch_text", side_effect=TimeoutError("slow")).start()

    item = RAGEvaluator(judge).evaluate_item(query="q", answer="a", context=["c"])

    assert item.errors["faithfulness"] == "judge call failed (TimeoutError)"


def _item(faith: int, errors: dict | None = None, recall: int | None = None) -> RAGItemResult:
    return RAGItemResult(
        query="q",
        answer="a",
        context=["c"],
        ground_truth=None,
        faithfulness_score=faith,
        answer_relevance_score=5,
        context_precision_score=5,
        context_recall_score=recall,
        errors=errors or {},
    )


def test_failed_items_are_left_out_of_the_mean_and_counted() -> None:
    items = [_item(5) for _ in range(9)] + [_item(0, {"faithfulness": "judge call failed"})]

    metrics = _aggregate(items)

    assert metrics.faithfulness == 1.0
    assert metrics.failed == {"faithfulness": 1, "answer_relevance": 0, "context_precision": 0}
    assert "PARTIAL" in str(metrics) and "PARTIAL" not in str(_aggregate(items[:9]))
    assert metrics.context_recall is None


def test_a_metric_no_item_was_scored_on_is_zero_and_all_failed() -> None:
    metrics = _aggregate([_item(0, {"faithfulness": "x"}, recall=0), _item(0, recall=0)])

    assert metrics.faithfulness == 0.0 and metrics.failed["faithfulness"] == 2
    assert metrics.context_recall == 0.0 and metrics.failed["context_recall"] == 2


def test_a_reply_whose_metric_flag_cannot_be_read_gives_no_score() -> None:
    # The faithfulness flag lacks its severity, so only the query's flag is read.
    reply = (
        '{"flags": [{"field": "query", "severity": "ok", "score": 5},'
        ' {"field": "faithfulness", "score": 2}]}'
    )
    judge, _ = _judge([reply])

    item = RAGEvaluator(judge).evaluate_item(query="q", answer="a", context=["c"])

    assert item.faithfulness_score == 0
    assert item.errors["faithfulness"] == (
        "judge gave no score for faithfulness; 1 of 2 flags could not be read"
    )
