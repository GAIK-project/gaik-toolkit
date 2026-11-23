"""RAGResponseEvaluator: ranking without decisive comparisons, resuming by question, and
running inside an event loop. No network: the clients are fakes.
"""

from __future__ import annotations

import asyncio

import pandas as pd
import pytest
from gaik.software_components.evaluators.rag_response_evaluator import (
    DEFAULT_PAIRWISE_SPEC,
    CorrectnessScore,
    RAGResponseEvaluator,
    _aggregate_pairwise,
)


def test_a_system_with_only_ties_ranks_by_its_scores_not_last() -> None:
    aspects = DEFAULT_PAIRWISE_SPEC.aspect_fields
    rows = []
    for a, b, winner in (("A", "B", "tie"), ("A", "C", "tie"), ("B", "C", "A")):
        row = {"question": "q", "system_a": a, "system_b": b, "winner": winner}
        row |= {f"{aspect}_a": 3 for aspect in aspects} | {f"{aspect}_b": 3 for aspect in aspects}
        rows.append(row)

    ranking = _aggregate_pairwise(pd.DataFrame(rows), ["A", "B", "C"], DEFAULT_PAIRWISE_SPEC)

    assert [r.system for r in ranking] == ["B", "A", "C"]
    assert pd.isna(ranking[1].win_rate)


class _Scores:
    """A client that scores each answer by its question's number (0-3), and counts the calls."""

    def __init__(self):
        self.calls = 0

    def chat_parsed(self, messages, response_format, temperature=0):
        self.calls += 1
        question = messages[1]["content"].split('label="question">\n', 1)[1].split("\n", 1)[0]
        score = int(question.split()[-1])
        return CorrectnessScore(
            omissions="",
            contradictions="",
            relevance_notes="",
            precision_notes="",
            coverage_score=score,
            contradiction_score=2,
            relevance_score=2,
            precision_score=2,
            overall_score=score,
            reason=question,
        )


def _questions(numbers) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "question": [f"question {n}" for n in numbers],
            "reference": ["reference answer"] * len(numbers),
            "x_response": ["the x system's answer"] * len(numbers),
        }
    )


def test_resume_matches_rows_by_question_not_position(tmp_path) -> None:
    client = _Scores()
    evaluator = RAGResponseEvaluator(client, max_concurrency=1)
    first = evaluator.evaluate(_questions([1, 2, 3]))
    evaluator.save(first, tmp_path, write_plots=False)
    saved = pd.read_csv(tmp_path / "rag_eval_scored.csv")

    # The same questions in another order, one left out and a new one added.
    resumed = evaluator.evaluate(_questions([3, 1, 0]), resume_from=saved)

    assert client.calls == 4  # three first, then only the new question
    assert resumed.scored_df["x_response_coverage_score"].astype(int).tolist() == [3, 1, 0]


def test_a_saved_row_with_a_score_missing_is_judged_again(tmp_path) -> None:
    client = _Scores()
    evaluator = RAGResponseEvaluator(client, max_concurrency=1)
    evaluator.save(evaluator.evaluate(_questions([1, 2])), tmp_path, write_plots=False)
    saved = pd.read_csv(tmp_path / "rag_eval_scored.csv")
    saved.loc[1, "x_response_overall_score"] = None  # a cell lost, say in a spreadsheet

    resumed = evaluator.evaluate(_questions([1, 2]), resume_from=saved)

    assert client.calls == 3  # only the incomplete row again
    assert resumed.scored_df["x_response_overall_score"].astype(int).tolist() == [1, 2]
    assert resumed.per_system[0].n == 2


def test_concurrent_scoring_runs_inside_a_running_event_loop() -> None:
    client = _Scores()
    evaluator = RAGResponseEvaluator(client, max_concurrency=3)

    async def inside_a_loop():
        return evaluator.evaluate(_questions([1, 2, 3]))

    result = asyncio.run(inside_a_loop())

    assert result.scored_df["x_response_overall_score"].astype(int).tolist() == [1, 2, 3]


def test_a_system_never_compared_ranks_last() -> None:
    aspects = DEFAULT_PAIRWISE_SPEC.aspect_fields
    row = {"question": "q", "system_a": "A", "system_b": "B", "winner": "A"}
    row |= {f"{aspect}_a": 3 for aspect in aspects} | {f"{aspect}_b": 3 for aspect in aspects}

    ranking = _aggregate_pairwise(pd.DataFrame([row]), ["A", "B", "C"], DEFAULT_PAIRWISE_SPEC)

    assert [r.system for r in ranking] == ["A", "B", "C"]


def test_resume_matches_questions_that_a_csv_reads_back_as_numbers(tmp_path) -> None:
    client = _Scores()
    evaluator = RAGResponseEvaluator(client, max_concurrency=1)
    frame = _questions([1, 3])
    # Questions that are only digits come back from read_csv as the numbers 1 and 3.
    frame["question"] = ["1", "3"]
    evaluator.save(evaluator.evaluate(frame), tmp_path, write_plots=False)
    saved = pd.read_csv(tmp_path / "rag_eval_scored.csv")

    evaluator.evaluate(frame, resume_from=saved)

    assert client.calls == 2  # nothing judged again


def test_a_frame_whose_index_repeats_a_label_resumes_each_row() -> None:
    client = _Scores()
    evaluator = RAGResponseEvaluator(client, max_concurrency=1)
    first = evaluator.evaluate(_questions([1, 3]))
    saved = first.scored_df.reset_index(drop=True)

    from gaik.software_components.evaluators.rag_response_evaluator import _init_scored_df

    frame = _questions([1, 3])
    frame.index = [0, 0]
    scored = _init_scored_df(frame, ["x_response"], ["coverage_score"], saved)

    assert scored["x_response_coverage_score"].tolist() == [1, 3]


def test_pairwise_resume_takes_the_last_saved_row_and_judges_an_incomplete_one() -> None:
    from gaik.software_components.evaluators.rag_response_evaluator import _init_pairwise_df

    aspects = DEFAULT_PAIRWISE_SPEC.aspect_fields
    done = {"system_a": "x_response", "system_b": "y_response", "winner": "A"}
    done |= {f"{aspect}_a": 3 for aspect in aspects} | {f"{aspect}_b": 3 for aspect in aspects}
    saved = pd.DataFrame(
        [
            {"question": "q1", **done, "winner": "B"},
            {"question": "q1", **done},  # saved twice: the last one counts
            {"question": "q2", **done, "clarity_a": None},  # an aspect score lost
        ]
    )
    frame = pd.DataFrame(
        {"question": ["q1", "q2"], "x_response": ["x " * 20] * 2, "y_response": ["y " * 20] * 2}
    )

    comparisons = _init_pairwise_df(
        frame, "question", [("x_response", "y_response")], DEFAULT_PAIRWISE_SPEC, saved
    )

    assert comparisons["winner"].tolist()[0] == "A"
    assert pd.isna(comparisons["winner"].tolist()[1])  # judged again


def _concatenated(first, second) -> pd.DataFrame:
    """Two frames joined with pd.concat: their index labels repeat (0, 1, 0, 1)."""
    return pd.concat([_questions(first), _questions(second)])


@pytest.mark.parametrize("concurrency", [1, 3], ids=["sequential", "concurrent"])
def test_a_frame_whose_index_repeats_a_label_is_scored_row_by_row(concurrency) -> None:
    client = _Scores()
    evaluator = RAGResponseEvaluator(client, max_concurrency=concurrency)

    result = evaluator.evaluate(_concatenated([1, 2], [3, 0]))

    assert client.calls == 4
    assert result.scored_df.index.tolist() == [0, 1, 0, 1]  # the caller's index stays
    assert result.scored_df["x_response_coverage_score"].astype(int).tolist() == [1, 2, 3, 0]
    assert result.scored_df["x_response_reason"].str.contains("question 3").tolist() == [
        False,
        False,
        True,
        False,
    ]
    assert result.per_system[0].n == 4


@pytest.mark.parametrize("concurrency", [1, 3], ids=["sequential", "concurrent"])
def test_resuming_a_frame_whose_index_repeats_a_label_keeps_the_resumed_rows(
    concurrency,
) -> None:
    client = _Scores()
    evaluator = RAGResponseEvaluator(client, max_concurrency=concurrency)
    saved = evaluator.evaluate(_questions([1, 2])).scored_df
    calls_before = client.calls

    # Rows 0 and 1 of the first frame are resumed; label 0 and 1 repeat for 3 and 0.
    result = evaluator.evaluate(_concatenated([1, 2], [3, 0]), resume_from=saved)

    assert client.calls - calls_before == 2  # only questions 3 and 0
    assert result.scored_df["x_response_coverage_score"].astype(int).tolist() == [1, 2, 3, 0]


def test_pairwise_resume_with_questions_that_match_after_a_csv_round_trip() -> None:
    from gaik.software_components.evaluators.rag_response_evaluator import _init_pairwise_df

    aspects = DEFAULT_PAIRWISE_SPEC.aspect_fields
    done = {"system_a": "x_response", "system_b": "y_response"}
    done |= {f"{aspect}_a": 3 for aspect in aspects} | {f"{aspect}_b": 3 for aspect in aspects}
    # 101 and "101", "q\r\n2" and "q\n2" are one question each once read back from a CSV.
    saved = pd.DataFrame(
        [
            {"question": 101, **done, "winner": "B"},
            {"question": "101", **done, "winner": "A"},
            {"question": "q\r\n2", **done, "winner": "B"},
            {"question": "q\n2", **done, "winner": "tie"},
        ]
    )
    frame = pd.DataFrame(
        {
            "question": ["101", "q\n2"],
            "x_response": ["x " * 20] * 2,
            "y_response": ["y " * 20] * 2,
        }
    )

    comparisons = _init_pairwise_df(
        frame, "question", [("x_response", "y_response")], DEFAULT_PAIRWISE_SPEC, saved
    )

    assert comparisons["winner"].tolist() == ["A", "tie"]  # the last saved row counts
