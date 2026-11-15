"""Pairwise RAG evaluation: the swap pass and resuming from a saved CSV."""

import re

import pandas as pd
import pytest
from gaik.software_components.evaluators.rag_response_evaluator import (
    PairwiseVerdict,
    RAGResponseEvaluator,
)

_ASPECTS = ("directness", "specificity", "completeness", "consistency", "clarity")


class _Judge:
    """A fake judge that records the order it was shown and always picks ``winner``."""

    def __init__(self, winner: str = "A"):
        self.winner = winner
        self.shown: list[tuple[str, str]] = []

    def chat_parsed(self, messages, response_format, temperature=0):
        prompt = messages[1]["content"]
        first = re.search(r"<response_a>\n(.*?)\n</response_a>", prompt, re.S).group(1)
        second = re.search(r"<response_b>\n(.*?)\n</response_b>", prompt, re.S).group(1)
        self.shown.append((first, second))
        scores = {f"{aspect}_{side}": 3 for aspect in _ASPECTS for side in "ab"}
        return PairwiseVerdict(
            a_summary="",
            b_summary="",
            key_differences="",
            winner=self.winner,
            confidence="high",
            reason="r",
            **scores,
        )


def _frame(questions=("q",)) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "question": list(questions),
            "x_response": ["answer from x " * 3] * len(questions),
            "y_response": ["answer from y " * 3] * len(questions),
        }
    )


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("max_concurrency", [1, 2])
def test_the_swap_pass_shows_the_pair_in_the_other_order(seed, max_concurrency):
    judge = _Judge()
    evaluator = RAGResponseEvaluator(judge, max_concurrency=max_concurrency)

    result = evaluator.evaluate_pairwise(_frame(), random_seed=seed)

    first, second = judge.shown
    assert second == (first[1], first[0])
    # A judge that always picks the response shown first agrees with itself only
    # when both passes show the same order, so the swap must call it a tie.
    row = result.comparisons_df.iloc[0]
    assert row["winner"] == "tie"
    assert not row["swap_consistent"]


def test_a_saved_table_resumes_without_judging_again(tmp_path):
    # Text that starts like a formula is saved with a leading apostrophe.
    frame = _frame(questions=("-5 C is cold?", "=SUM of what?", "plain"))
    judge = _Judge(winner="tie")
    evaluator = RAGResponseEvaluator(judge, max_concurrency=1)
    first = evaluator.evaluate_pairwise(frame, random_seed=1)
    evaluator.save(first, tmp_path, write_plots=False)
    calls = len(judge.shown)

    saved = pd.read_csv(tmp_path / "rag_eval_pairwise.csv")
    resumed = evaluator.evaluate_pairwise(frame, resume_from=saved, random_seed=1)

    assert len(judge.shown) == calls
    assert resumed.comparisons_df["question"].tolist() == frame["question"].tolist()
    assert resumed.comparisons_df["winner"].tolist() == ["tie"] * 3


def test_a_saved_table_resumes_when_a_system_name_starts_like_a_formula(tmp_path):
    frame = _frame().rename(
        columns={"x_response": "-base_response", "y_response": "+rerank_response"}
    )
    judge = _Judge(winner="tie")
    evaluator = RAGResponseEvaluator(judge, max_concurrency=1)
    evaluator.save(evaluator.evaluate_pairwise(frame, random_seed=1), tmp_path, write_plots=False)
    calls = len(judge.shown)

    saved = pd.read_csv(tmp_path / "rag_eval_pairwise.csv")
    evaluator.evaluate_pairwise(frame, resume_from=saved, random_seed=1)

    assert len(judge.shown) == calls
