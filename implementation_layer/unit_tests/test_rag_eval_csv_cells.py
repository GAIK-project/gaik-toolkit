"""RAG evaluation CSVs open in a spreadsheet as the text they hold."""

import pandas as pd
from gaik.software_components.evaluators.rag_response_evaluator import _write_csv


def test_text_that_starts_like_a_formula_is_written_as_text(tmp_path):
    df = pd.DataFrame(
        {
            "question": ["=1+1", "+cmd", "-2 apples", "@SUM(A1)", "\tlead", "plain"],
            "score": [1, 2, 3, 4, 5, 6],
            "delta": [-0.5, 0.0, 1.5, -1.0, 2.0, 3.0],
        }
    )
    path = tmp_path / "out.csv"

    _write_csv(df, path)

    back = pd.read_csv(path, keep_default_na=False)
    assert back["question"].tolist() == [
        "'=1+1",
        "'+cmd",
        "'-2 apples",
        "'@SUM(A1)",
        "'\tlead",
        "plain",
    ]
    # Numbers stay numbers, including negative ones.
    assert back["score"].tolist() == [1, 2, 3, 4, 5, 6]
    assert back["delta"].tolist() == [-0.5, 0.0, 1.5, -1.0, 2.0, 3.0]


def test_the_frame_given_is_not_changed(tmp_path):
    df = pd.DataFrame({"answer": ["=x"]})

    _write_csv(df, tmp_path / "out.csv")

    assert df["answer"].tolist() == ["=x"]


def test_missing_and_non_text_values_pass_through(tmp_path):
    df = pd.DataFrame({"note": [None, "ok", 3]})

    _write_csv(df, tmp_path / "out.csv")

    assert pd.read_csv(tmp_path / "out.csv")["note"].tolist()[1:] == ["ok", "3"]
