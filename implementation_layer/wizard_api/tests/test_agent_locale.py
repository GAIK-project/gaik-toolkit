"""The agent's reply language follows the UI locale (customer test report, T5; 11, 14, 17, R9).

The locale reached the agent only in the bootstrap turn, and the web route never
sent one at all, so the agent chose its own language — mixing Finnish and
English in the same session and once answering in Italian. These tests cover the
API half: the instruction that pins the language, and the one that re-pins it
when the user switches the UI mid-session.
"""

from wizard_api.services.agent_service import (
    _bootstrap_prompt,
    _language_line,
    relanguage_prompt,
)

# ---------------------------------------------------------------------------
# Pinning at bootstrap
# ---------------------------------------------------------------------------


def test_the_bootstrap_pins_the_language_for_a_known_locale():
    assert "in Finnish" in _language_line("fi")
    assert "in English" in _language_line("en")


def test_the_instruction_overrides_the_language_the_user_writes_in():
    """17: the user wrote Finnish, the agent replied in Italian. The pin has to
    beat whatever language the message itself is in."""
    assert "regardless of the language the user writes in" in _language_line("fi")


def test_an_unknown_or_missing_locale_pins_nothing():
    assert _language_line(None) == ""
    assert _language_line("") == ""
    assert _language_line("it") == ""


def test_the_bootstrap_prompt_carries_the_pin(tmp_path):
    assert "in Finnish" in _bootstrap_prompt(tmp_path, "fi")
    assert "in English" in _bootstrap_prompt(tmp_path, "en")


# ---------------------------------------------------------------------------
# Re-pinning on a switch (R9)
# ---------------------------------------------------------------------------


def test_switching_the_ui_language_re_pins_the_agent():
    prompt = relanguage_prompt("fi", "en")

    assert prompt is not None
    assert "English" in prompt


def test_no_instruction_when_the_locale_has_not_changed():
    assert relanguage_prompt("fi", "fi") is None
    assert relanguage_prompt("en", "en") is None


def test_no_instruction_when_the_incoming_locale_is_unknown():
    """A missing or unrecognised locale must not silently re-language a session
    that was pinned correctly."""
    assert relanguage_prompt("fi", None) is None
    assert relanguage_prompt("fi", "") is None
    assert relanguage_prompt("fi", "it") is None


def test_a_session_bootstrapped_without_a_locale_can_still_be_pinned_later():
    prompt = relanguage_prompt(None, "fi")

    assert prompt is not None
    assert "Finnish" in prompt


def test_case_and_whitespace_do_not_count_as_a_switch():
    assert relanguage_prompt("fi", " FI ") is None
