"""The agentic reviewer applies an edit to the passage its search means, or to none.

A reviewer's ``search`` is meant to be copied letter for letter from the draft, but a
model sometimes changes a letter, a quote or a space. The edit must then land on the
passage it means, never on a span shifted from it or on a second passage; when that is
unclear it stays unresolved and is asked for again. Offline: no model is called.
"""

from __future__ import annotations

import random
import time

import pytest
from gaik.software_modules.multi_source_report_generator.agentic import _span
from gaik.software_modules.multi_source_report_generator.agentic.reviewer import (
    Correction,
    _apply_corrections,
    _find_search_string,
)

SECTION = (
    "The building was inspected on a dry day in March.\n\n"
    "The roof covering was replaced in 2012 and the gutters were renewed in 2015. "
    "Moss grows on the north slope, and two tiles near the chimney are cracked.\n\n"
    "The facade is brick with a cement render on the ground floor. The render has "
    "hairline cracks under the kitchen window but no loose pieces were found.\n\n"
    "The windows are double glazed and date from 1998."
)
PASSAGE = "two tiles near the chimney are cracked"


def _typo(text: str, pos: int) -> str:
    return text[:pos] + ("x" if text[pos] != "x" else "y") + text[pos + 1 :]


def _apply(search: str, replace: str = "REPLACED") -> tuple[str, list[dict]]:
    text, _, failed = _apply_corrections(
        SECTION, [Correction(search=search, replace=replace, reason="r")]
    )
    return text, failed


@pytest.mark.parametrize("pos", range(len(PASSAGE)))
def test_a_one_letter_typo_replaces_the_passage_or_nothing(pos):
    text, failed = _apply(_typo(PASSAGE, pos))
    if failed:
        assert text == SECTION
    else:
        assert text == SECTION.replace(PASSAGE, "REPLACED")


@pytest.mark.parametrize("pos", range(len(PASSAGE)))
@pytest.mark.parametrize("kind", ["deleted", "inserted"])
def test_a_letter_left_out_or_added_replaces_the_passage_or_nothing(pos, kind):
    search = (
        PASSAGE[:pos] + PASSAGE[pos + 1 :]
        if kind == "deleted"
        else PASSAGE[:pos] + "q" + PASSAGE[pos:]
    )
    if search in SECTION:
        pytest.skip("the search occurs as it is")
    text, failed = _apply(search)
    if failed:
        assert text == SECTION
    else:
        assert text == SECTION.replace(PASSAGE, "REPLACED")


def test_almost_every_one_letter_change_is_still_applied():
    applied = 0
    for pos in range(len(PASSAGE)):
        for search in (_typo(PASSAGE, pos), PASSAGE[:pos] + "q" + PASSAGE[pos:]):
            applied += not _apply(search)[1]
    assert applied >= 0.9 * 2 * len(PASSAGE)


def test_a_typo_inside_the_passage_is_found():
    search = "The roof covering was replacd in 2012 and the gutters were renewed in 2015."
    text, failed = _apply(
        search, "The roof covering was replaced in 2013 and the gutters were renewed in 2015."
    )
    assert failed == []
    assert "replaced in 2013 and the gutters" in text
    assert text.replace("2013", "2012") == SECTION


@pytest.mark.parametrize(
    "search",
    [
        # Within 10% of the passage, but a different number is a different fact.
        "The roof covering was replaced in 2021 and the gutters were renewed in 2015.",
        "The roof covering was replaced in 2012 and the gutters were renewed in 2016.",
        "two tiles near the chimney are cracked, 3 of them",
    ],
)
def test_a_close_match_that_changes_a_number_is_refused(search):
    text, failed = _apply(search)
    assert text == SECTION
    assert failed[0]["error"] in (_span.NUMBER_DIFFERS, _span.NOT_FOUND)


def test_a_number_differs_error_is_given_for_a_changed_year():
    text = "Intro. The roof was repaired in 2020. Walls are intact. Doors are new."
    assert _span.locate(text, "The roof was repaired in 2021. Walls are intact.") == (
        _span.NUMBER_DIFFERS
    )
    # Swapped words are more than a typo.
    assert not isinstance(
        _span.locate(text, "The walls were repaired in 2020. Roof is intact."), _span.Span
    )


def test_quotes_dashes_case_and_spaces_are_ignored():
    text = "The wall is “brick” — mostly. The   Roof is old."
    edits = [
        Correction(
            search='The wall is "brick" - mostly.', replace="The wall is stone.", reason="r"
        ),
        Correction(search="the roof is old.", replace="The roof is new.", reason="r"),
    ]
    new, applied, failed = _apply_corrections(text, edits)
    assert failed == []
    assert new == "The wall is stone. The roof is new."
    assert applied[0]["search"] == "The wall is “brick” — mostly."


def test_an_edit_that_fits_two_passages_is_unresolved():
    text = "The roof leaks badly. Later: The roof leaks badly."
    for search in ("The roof leaks badly.", "the roof leaks badly.", "The roof leaks badlx."):
        new, applied, failed = _apply_corrections(
            text, [Correction(search=search, replace="X", reason="r")]
        )
        assert new == text and applied == []
        assert len(failed) == 1


def test_an_edge_letter_that_could_be_replaced_or_added_is_unresolved():
    # "x" may stand for "[" or come before it; either reading would leave a stray
    # character beside the replacement, so the edit is asked for again.
    text = "See [GitHub - the demo app](https://example.org) for the code."
    assert _find_search_string(text, "xGitHub - the demo app](https") is None
    # A start inside a word is never the passage's edge, so this one is clear.
    found = _find_search_string(text, "xee [GitHub - the demo")
    assert found == "See [GitHub - the demo"


def test_whitespace_the_text_lacks_is_not_added_by_the_replacement():
    text = "Intro.\n\nThe roof was replaced in 2012."
    new, _, failed = _apply_corrections(
        text,
        [
            Correction(
                search=" The rof was replaced in 2012.", replace=" The roof is new.", reason="r"
            )
        ],
    )
    assert failed == []
    assert new == "Intro.\n\nThe roof is new."


def test_unicode_and_finnish_text():
    text = "Kattoremontti tehtiin vuonna 2012 ja räystäät uusittiin 2015. Status: \U0001f525."
    search = "Kattoremontti tehtiin vuonna 2012 ja raystäät uusittiin 2015."
    assert _find_search_string(text, search) == text[: text.index(" Status")]
    assert _find_search_string(text, "") is None
    assert _find_search_string("", "anything at all here") is None


def test_the_fuzzy_match_takes_bounded_time():
    # A long section of a few repeated words, with a long search: the earlier fallback
    # scored every offset and took seconds to minutes here.
    words = "the roof wall window was inspected and found in good condition with cracks".split()
    rng = random.Random(3)
    section = " ".join(rng.choice(words) for _ in range(3500))
    start = section.index(" ", 5000) + 1
    passage = section[start : start + 1000]
    # The same words in a fixed cycle: the passage occurs many times.
    cycle = " ".join(words[i % len(words)] for i in range(3500))
    began = time.perf_counter()
    found = _span.locate(section, _typo(passage, 500))
    absent = _span.locate(section, "zq" * 500)
    repeated = _span.locate(cycle, _typo(cycle[start : start + 1000], 500))
    elapsed = time.perf_counter() - began
    assert absent == _span.NOT_FOUND
    assert not isinstance(repeated, _span.Span)
    assert isinstance(found, _span.Span)
    assert (found.start, found.end) == (start, start + 1000)
    assert elapsed < 2.0


@pytest.mark.parametrize(
    ("text", "search", "passage"),
    [
        # A thousands separator is not another number.
        (
            "Intro. The repair cost 1 200 euros and was done in May. End.",
            "The repair cost 1200 euros and was done in May.",
            "The repair cost 1 200 euros and was done in May.",
        ),
        (
            "Intro. The repair cost 1200 euros and was done in May. End.",
            "The repair cost 1,200 euros and was done in May.",
            "The repair cost 1200 euros and was done in May.",
        ),
        # A list item's number after a line break, dropped by the search.
        (
            "1. Eka kohta.\n2. Toinen kohta on tässä, ja se jatkuu pitkään.",
            "Eka kohta.\nToinen kohta on tässä, ja se jatkuu pitkään.",
            "Eka kohta.\n2. Toinen kohta on tässä, ja se jatkuu pitkään.",
        ),
    ],
)
def test_grouped_digits_and_an_inner_list_number_are_the_same_numbers(text, search, passage):
    assert _find_search_string(text, search) == passage


def test_a_list_number_the_search_adds_at_its_start_is_still_refused():
    # Ignoring it would let the edit take the previous sentence's ". " as its edge.
    text = "Eka kohta.\nToinen kohta on tässä, ja se jatkuu pitkään."
    assert _find_search_string(text, "2. Toinen kohta on tässä, ja se jatkuu pitkään.") is None
