"""Log lines name positions, reasons and sizes, not the text being judged or curated."""

import logging

from gaik.software_components.knowledge_curator.knowledge_curator import _log_summary
from gaik.software_components.validators.llm_judge.llm_judge import parse_judge_flags
from gaik.software_components.validators.llm_judge.pairwise import _parse_pairwise

PRIVATE = "SOURCE-TEXT-THAT-MUST-NOT-BE-LOGGED"


def test_an_unreadable_judge_answer_is_logged_by_size(caplog):
    with caplog.at_level(logging.WARNING):
        assert parse_judge_flags(f"not json: {PRIVATE}") == []
    assert PRIVATE not in caplog.text
    assert "characters" in caplog.text


def test_an_unreadable_pairwise_answer_is_logged_by_size(caplog):
    with caplog.at_level(logging.WARNING):
        assert _parse_pairwise(f"not json: {PRIVATE}") == ("tie", 0, 0, "")
    assert PRIVATE not in caplog.text
    assert "characters" in caplog.text


def test_the_curator_log_summary_has_no_quotes_or_topics():
    failing = [
        (2, "quote not found in source", f'unit 2: quote "{PRIVATE}" not found in "a.md"'),
        (5, "file is not a source", f'unit 5: file "x.md" is not a source; quote "{PRIVATE}"'),
    ]
    conflicts = [f'conflict "{PRIVATE}" refers to unit positions [9], but the section has 5 units']

    summary = _log_summary(failing, conflicts)

    assert summary == [
        "unit 2: quote not found in source",
        "unit 5: file is not a source",
        "1 conflict(s) refer to missing units",
    ]
    assert all(PRIVATE not in line for line in summary)
