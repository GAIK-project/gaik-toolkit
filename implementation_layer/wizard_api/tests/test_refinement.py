"""Gate 3 refinement: the blueprint-first rule, held by the server (#96).

V1's SKILL.md states it as a rule the agent should follow. A rule an agent
should follow is one it can skip under pressure, and SKILL.md names the
consequence itself: the blueprint says one thing while run_poc.py does another,
and nothing downstream can be trusted. These tests pin the sequence.

Which row of V1's table a piece of feedback falls into is the agent's
judgement — it has the table and the conversation. What is checked here is what
follows from that judgement once it is made.
"""

import pytest
from wizard_api.services.refinement import (
    IMPLEMENTATION_RULE,
    INTENT_RULE,
    Refinement,
    RefinementRejectedError,
    check_regeneration_allowed,
    classify,
)

# ---------------------------------------------------------------------------
# Recording the feedback
# ---------------------------------------------------------------------------


def test_an_intent_change_says_the_blueprint_moves_first():
    r = classify("The Excel export should have one row per invoice line", "intent")

    assert r.requires_blueprint_change is True
    assert r.rule == INTENT_RULE


def test_an_implementation_fix_leaves_the_blueprint_alone():
    r = classify("The output path is wrong, it writes to ./out not ./output", "implementation")

    assert r.requires_blueprint_change is False
    assert r.rule == IMPLEMENTATION_RULE


def test_the_rule_is_readable_rather_than_a_code():
    """The user is told what will happen before it happens."""
    assert "blueprint" in classify("x", "intent").rule
    assert "patched directly" in classify("x", "implementation").rule


def test_empty_feedback_is_refused():
    """ "It did not work" recorded against a run helps nobody later."""
    for blank in ("", "   ", "\n"):
        with pytest.raises(RefinementRejectedError, match="what was wrong"):
            classify(blank, "intent")


def test_an_unknown_classification_is_refused_rather_than_defaulted():
    with pytest.raises(RefinementRejectedError, match="classification must be"):
        classify("something", "cosmetic")


def test_feedback_is_bounded():
    with pytest.raises(RefinementRejectedError, match="too long"):
        classify("x" * 4001, "intent")


def test_surrounding_whitespace_is_not_part_of_the_feedback():
    assert classify("  the dates are strings  ", "intent").feedback == "the dates are strings"


# ---------------------------------------------------------------------------
# The rule itself
# ---------------------------------------------------------------------------


def _intent(text="the schema needs a line-items list"):
    return Refinement(classification="intent", feedback=text, rule=INTENT_RULE)


def _implementation(text="wrong output path"):
    return Refinement(classification="implementation", feedback=text, rule=IMPLEMENTATION_RULE)


def test_an_intent_change_cannot_regenerate_before_the_blueprint_moves():
    with pytest.raises(RefinementRejectedError, match="before regenerating"):
        check_regeneration_allowed(
            _intent(), blueprint_version_at_feedback=3, blueprint_version_now=3
        )


def test_an_intent_change_may_regenerate_once_the_blueprint_has_moved():
    check_regeneration_allowed(_intent(), blueprint_version_at_feedback=3, blueprint_version_now=4)


def test_a_blueprint_that_went_backwards_does_not_count_as_moving():
    """A restored older version is not the change the feedback asked for."""
    with pytest.raises(RefinementRejectedError):
        check_regeneration_allowed(
            _intent(), blueprint_version_at_feedback=5, blueprint_version_now=4
        )


def test_an_implementation_fix_is_never_blocked():
    """By definition it changes nothing the blueprint records."""
    check_regeneration_allowed(
        _implementation(), blueprint_version_at_feedback=3, blueprint_version_now=3
    )


def test_the_refusal_names_the_version_it_is_still_at():
    with pytest.raises(RefinementRejectedError, match="version 7"):
        check_regeneration_allowed(
            _intent(), blueprint_version_at_feedback=7, blueprint_version_now=7
        )
