"""Prompts for DraftReviewer."""

from __future__ import annotations

from .models import Edit

SYSTEM_PROMPT = """\
You are a meticulous fact-checker and precise editor. You compare a text with reference \
material and return the search-and-replace edits that correct it. If no edits are needed, \
return an empty list of edits.

Rules:
1. Each 'search' must match the text EXACTLY, letter for letter, including whitespace, \
case, newlines and punctuation.
2. Each 'search' must occur exactly once in the text. Include enough surrounding words to \
make it unique.
3. Use an empty 'replace' to delete a passage.
4. Edits are applied in order, each to the text left by the edits before it.
5. Preserve the formatting and structure of the text unless the checks say otherwise.
6. Keep each 'search' short: just long enough to locate the passage."""

DEFAULT_CHECKS = """\
- Every factual claim must be supported by the reference material.
- Correct numbers, years, dates, names and attributions that contradict the reference.
- Remove claims that the reference does not support.
- Do not rewrite the style and do not reorder the content."""


def review_instruction(reference: str, instructions: str) -> str:
    return (
        "Check the text against the reference material and fix problems with targeted "
        "search-and-replace edits. Make only the changes the checks call for.\n\n"
        f"Checks:\n{instructions.strip() or DEFAULT_CHECKS}\n\n"
        f"Reference material (inside <reference>):\n<reference>\n{reference}\n</reference>"
    )


def check_prompt(text: str) -> str:
    return (
        f"Text to review (inside <text>):\n<text>\n{text}\n</text>\n\n"
        "Copy each 'search' EXACTLY from this text so the passage can be located."
    )


def retry_prompt(text: str, failed: list[tuple[Edit, str]], attempt: int) -> str:
    listed = "\n\n".join(
        f"  search: {edit.search!r}\n  replace: {edit.replace!r}\n"
        f"  reason: {edit.reason}\n  error: {error}"
        for edit, error in failed
    )
    return (
        f"You have proposed edits to this text {attempt} time(s), but these edits could "
        f"not be applied:\n\n{listed}\n\n"
        "The edits that did apply are already in the current text below; do not repeat "
        "them. Return NEW edits that make the failed changes, each with a 'search' that "
        "occurs exactly once in the current text. An empty list leaves the failed edits "
        "unresolved.\n\n"
        f"Current text (inside <text>):\n<text>\n{text}\n</text>"
    )
