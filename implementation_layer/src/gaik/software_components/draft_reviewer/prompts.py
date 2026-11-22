"""Prompts for DraftReviewer."""

from __future__ import annotations

from collections.abc import Mapping

from gaik.software_components.source_material import SourceMaterial

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


def _reference_blocks(material: SourceMaterial, reference: str | Mapping[str, str]) -> str:
    """The reference material, one labelled block per piece (one block for a plain string)."""
    if isinstance(reference, str):
        return material.wrap(reference, label="reference")
    return "\n\n".join(material.wrap(text, label=label) for label, text in reference.items())


def review_instruction(
    reference: str | Mapping[str, str], instructions: str, material: SourceMaterial
) -> str:
    """The checks, outside the blocks, followed by the reference material in its blocks."""
    return (
        "Check the text against the reference material and fix problems with targeted "
        "search-and-replace edits. Make only the changes the checks call for.\n\n"
        f"Checks:\n{instructions.strip() or DEFAULT_CHECKS}\n\n"
        "Reference material (each piece in its own source_material block, labelled with "
        "its name):\n" + _reference_blocks(material, reference)
    )


def check_prompt(text: str, material: SourceMaterial) -> str:
    return (
        "Text to review (in the source_material block labelled text):\n"
        + material.wrap(text, label="text")
        + "\n\nCopy each 'search' EXACTLY from this text so the passage can be located."
    )


def retry_prompt(
    text: str, failed: list[tuple[str, Edit, str]], attempt: int, material: SourceMaterial
) -> str:
    """The retry request: each failed edit under its id, then the current text."""
    listed = "\n\n".join(
        f"  id: {fid}\n  search: {edit.search!r}\n  replace: {edit.replace!r}\n"
        f"  reason: {edit.reason}\n  error: {error}"
        for fid, edit, error in failed
    )
    return (
        f"You have proposed edits to this text {attempt} time(s), but the edits in the "
        "source_material block labelled failed_edits could not be applied.\n\n"
        + material.wrap(listed, label="failed_edits")
        + "\n\nThe edits that did apply are already in the current text below; do not "
        "repeat them. Return NEW edits that make the failed changes, each with a 'search' "
        "that occurs exactly once in the current text. Set 'answers' of each edit to the "
        'ids of the failed edits it makes, such as ["F1"], or ["F1", "F2"] when one edit '
        "makes both, or to an empty list for an edit that makes none of them. A failed "
        "edit that no new edit names stays unresolved, and so does every failed edit if "
        "you return no edits.\n\n"
        "Current text (in the source_material block labelled text):\n"
        + material.wrap(text, label="text")
    )
