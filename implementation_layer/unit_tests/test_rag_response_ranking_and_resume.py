"""RAGResponseEvaluator: ranking without decisive comparisons, resuming by question, and
running inside an event loop. No network: the clients are fakes.
"""

from __future__ import annotations

import asyncio

import pandas as pd
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


def test_concurrent_scoring_runs_inside_a_running_event_loop() -> None:
    client = _Scores()
    evaluator = RAGResponseEvaluator(client, max_concurrency=3)

    async def inside_a_loop():
        return evaluator.evaluate(_questions([1, 2, 3]))

    result = asyncio.run(inside_a_loop())

    assert result.scored_df["x_response_overall_score"].astype(int).tolist() == [1, 2, 3]
