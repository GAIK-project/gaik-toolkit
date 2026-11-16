"""Diff-editor reviewer — ported from the Lotus ``agentic_diff_editor`` and
genericized.

A mandatory fact/format repair pass for one section: the LLM returns a
structured ``CorrectionList`` of ``{search, replace, reason}`` edits, which are
applied with an exact, then a normalized, then a fuzzy (>= 0.9) match that must
be unique; unapplied edits are retried (up to ``MAX_ATTEMPTS``). Whatever cannot be
applied is returned as human-readable warnings rather than raising. An optional
style-only ``polish`` pass reuses the same editor.

Uses GAIK's ``ProviderClient.chat_parsed(messages, response_format=...)`` for
structured output and the stdlib ``difflib`` for fuzzy matching (no extra deps).
"""

from __future__ import annotations

from difflib import SequenceMatcher

from pydantic import BaseModel, Field

from .prompts import build_polish_instruction, build_reviewer_instruction

MAX_ATTEMPTS = 5
FUZZY_THRESHOLD = 0.9

_EDITOR_SYSTEM_PROMPT = """\
You are a precise text editor and meticulous fact-checker that produces \
structured search/replace instructions for revising text.

Task: analyse the provided text against the given instructions and reference \
material, then produce the edits needed. If no edits are needed, return an empty \
list of corrections.

Critical rules:
1. Each 'search' string must EXACTLY match existing text letter-for-letter, \
including whitespace, case, newlines and punctuation.
2. Each 'search' string must appear exactly once — include enough surrounding \
context (typically 1-3 sentences) to be unique.
3. Use an empty string "" for 'replace' to delete text.
4. Preserve the formatting, indentation and structure of the original text \
unless the instructions say otherwise.
5. Keep search/replace strings concise — just long enough to locate and fix the \
issue. Follow the instructions about what to revise (and what not to)."""


class Correction(BaseModel):
    """A single search/replace correction."""

    search: str = Field(description="Letter-for-letter exact string to find in the text.")
    replace: str = Field(description="Replacement string to apply.")
    reason: str = Field(description="Why this correction is needed (1-2 sentences).")


class CorrectionList(BaseModel):
    """List of corrections to apply."""

    corrections: list[Correction] = Field(default_factory=list)
    explanation: str = Field(default="", description="Overall explanation (1-3 sentences).")


# ---------------------------------------------------------------------------
# Applying corrections
# ---------------------------------------------------------------------------


# Curly quotes, en and em dashes and the no-break space, as their plain forms.
_FOLD = str.maketrans("\u2018\u2019\u201c\u201d\u2013\u2014\u00a0", "''\"\"-- ")


def _folded(text: str) -> tuple[str, list[int]]:
    """``text`` lower-cased, quotes and dashes folded, whitespace runs collapsed to one
    space, with the index in ``text`` of each kept character."""
    out: list[str] = []
    where: list[int] = []
    for i, ch in enumerate(text.translate(_FOLD)):
        if ch.isspace():
            if out and out[-1] == " ":
                continue
            ch = " "
        for c in ch.lower():
            out.append(c)
            where.append(i)
    return "".join(out), where


def _unique_find(haystack: str, needle: str) -> int | None:
    pos = haystack.find(needle)
    if pos < 0 or haystack.find(needle, pos + 1) >= 0:
        return None
    return pos


def _find_search_string(text: str, search: str, threshold: float = FUZZY_THRESHOLD) -> str | None:
    """Return the actual substring of ``text`` matching ``search``, or None.

    Tries an exact match, then one that ignores case, quote and dash styles and
    whitespace runs, then (for longer strings) a fuzzy match of at least
    ``threshold`` checked at every offset, for spans as long as ``search`` and one
    character shorter or longer. A loose match is taken only when exactly one span of
    ``text`` fits best, so an edit never lands on a shifted or a second span;
    anything else returns None and the edit stays unresolved. Whitespace at either
    end of ``search`` is matched only where the text has whitespace beside the passage.
    """
    if search in text:
        return search

    folded_text, where = _folded(text)
    folded_search = _folded(search)[0]
    # A space at either end belongs to the passage the edit replaces. It is dropped only
    # when the text does not hold it there, as before a passage that starts the text.
    if folded_search not in folded_text:
        folded_search = folded_search.strip()
    if folded_search:
        pos = _unique_find(folded_text, folded_search)
        if pos is not None:
            return text[where[pos] : where[pos + len(folded_search) - 1] + 1]

    # Too short to fuzzy-match reliably.
    core = search.strip()
    if len(core) < 10:
        return None
    span = _fuzzy_span(text, core, threshold)
    if span is None:
        return None
    start, end = span
    # The search's own whitespace at an end takes the whitespace character beside the
    # passage, so a replacement that carries it does not leave a doubled space.
    if search[0].isspace() and start > 0 and text[start - 1].isspace():
        start -= 1
    if search[-1].isspace() and end < len(text) and text[end].isspace():
        end += 1
    return text[start:end]


def _fuzzy_span(text: str, search: str, threshold: float) -> tuple[int, int] | None:
    """The ``(start, end)`` of the one span of ``text`` that fits ``search`` best, or None."""
    n = len(search)
    matcher = SequenceMatcher(None, autojunk=False)
    matcher.set_seq2(search.lower())
    fits: dict[tuple[int, int], tuple[int, int]] = {}

    def ratio_at(start: int, width: int, floor: float) -> float:
        """Score ``text[start:start + width]``; a span that fits goes into ``fits``."""
        end = min(start + width, len(text))
        matcher.set_seq1(text[start:end].lower())
        if matcher.real_quick_ratio() < floor or matcher.quick_ratio() < floor:
            return 0.0
        ratio = matcher.ratio()
        if ratio >= threshold:
            edits = sum(
                max(i2 - i1, j2 - j1)
                for tag, i1, i2, j1, j2 in matcher.get_opcodes()
                if tag != "equal"
            )
            matched = sum(block.size for block in matcher.get_matching_blocks())
            # Fewest edits first, then most characters kept.
            fits[(start, end)] = (edits, -matched)
        return ratio

    # Spans one character shorter and longer than ``search`` are tried too: after a
    # one-character insertion or deletion only the passage itself needs a single edit,
    # while two spans of the search's own length, shifted by one, would tie. Such a span
    # that fits keeps the span of the search's length at the same start above ``near``,
    # so only those starts are tried with the other two lengths.
    near = threshold - (2 - threshold) / (2 * n)
    for start in range(0, max(1, len(text) - n + 2)):
        if ratio_at(start, n, near) >= near:
            ratio_at(start, n - 1, threshold)
            ratio_at(start, n + 1, threshold)
    if not fits:
        return None
    rank = min(fits.values())
    best = [span for span, r in fits.items() if r == rank]
    # Two spans that fit equally well, such as a passage with or without the character
    # next to it, leave the edit unresolved.
    if len(best) != 1:
        return None
    start, end = best[0]
    # A second fitting span that does not overlap the best one makes it ambiguous.
    if any(s >= end or e <= start for s, e in fits):
        return None
    return start, end


def _apply_corrections(
    text: str, corrections: list[Correction]
) -> tuple[str, list[dict], list[dict]]:
    current = text
    successful: list[dict] = []
    failed: list[dict] = []
    for c in corrections:
        target = c.search if c.search in current else _find_search_string(current, c.search)
        if target:
            current = current.replace(target, c.replace, 1)
            successful.append({"search": target, "replace": c.replace, "reason": c.reason})
        else:
            failed.append(
                {
                    "search": c.search,
                    "replace": c.replace,
                    "reason": c.reason,
                    "error": "search string not found in text",
                }
            )
    return current, successful, failed


def _request_corrections(
    client, instruction: str, user_prompt: str, chat_kwargs: dict
) -> CorrectionList:
    messages = [
        {"role": "system", "content": _EDITOR_SYSTEM_PROMPT},
        {"role": "user", "content": instruction},
        {"role": "user", "content": user_prompt},
    ]
    result = client.chat_parsed(messages, response_format=CorrectionList, **chat_kwargs)
    if isinstance(result, CorrectionList):
        return result
    # Defensive: some clients may hand back a dict / other BaseModel.
    if isinstance(result, BaseModel):
        return CorrectionList.model_validate(result.model_dump())
    return CorrectionList.model_validate(result)


def _check_prompt(text: str) -> str:
    return (
        "Text to review (inside <text>):\n<text>\n"
        f"{text}\n</text>\n\n"
        "If you make corrections, copy each 'search' field EXACTLY from this text "
        "so the passage can be located."
    )


def _retry_prompt(text: str, failed: list[dict], attempt: int) -> str:
    failed_info = "\n\n".join(
        f"  search: {f['search']!r}\n  replace: {f['replace']!r}\n  error: {f['error']}"
        for f in failed
    )
    return (
        f"You have attempted to correct this text {attempt} time(s), but the following "
        "edits could not be applied because their search strings were not found:\n\n"
        f"{failed_info}\n\n"
        "Re-read the instructions and decide whether these changes are still needed. "
        "If so, produce NEW corrections whose 'search' strings EXACTLY match the current "
        "text below.\n\n"
        f"<text>\n{text}\n</text>"
    )


def diff_editor_run(
    *,
    text: str,
    instruction: str,
    client,
    chat_kwargs: dict,
) -> tuple[str, list[dict], list[str], int]:
    """Run the check -> apply -> retry loop.

    Returns ``(corrected_text, applied_edits, warnings, num_proposed)``.
    ``warnings`` lists edits that could not be applied after all retries.
    """
    current = text
    applied: list[dict] = []

    first = _request_corrections(client, instruction, _check_prompt(current), chat_kwargs)
    num_proposed = len(first.corrections)
    pending = first.corrections

    attempt = 0
    failed: list[dict] = []
    while pending:
        current, successful, failed = _apply_corrections(current, pending)
        applied.extend(successful)
        attempt += 1
        if not failed:
            break
        if attempt >= MAX_ATTEMPTS:
            break
        pending = _request_corrections(
            client, instruction, _retry_prompt(current, failed, attempt), chat_kwargs
        ).corrections

    warnings = [
        f"Unresolved reviewer edit (search text not found after {attempt} attempt(s)): "
        f"{f['search'][:80]!r}"
        for f in failed
    ]
    return current, applied, warnings, num_proposed


def review_and_polish(
    *,
    draft: str,
    evidence: str,
    title: str,
    instructions: str,
    sample_section: str,
    has_sample: bool,
    include_source_references: bool,
    report_description: str | None,
    additional_instructions: str | None = None,
    dependencies_context: str,
    client,
    chat_kwargs: dict,
    polish: bool,
    reporter,
    label: str,
) -> tuple[str, list[dict], list[str]]:
    """Mandatory fact/format repair, then optional style-only polish."""
    instruction = build_reviewer_instruction(
        title=title,
        instructions=instructions,
        evidence=evidence,
        sample_section=sample_section,
        has_sample=has_sample,
        include_source_references=include_source_references,
        report_description=report_description,
        additional_instructions=additional_instructions,
        dependencies_context=dependencies_context,
    )
    text, applied, warnings, num_proposed = diff_editor_run(
        text=draft, instruction=instruction, client=client, chat_kwargs=chat_kwargs
    )
    reporter.emit(
        f"[{label}] reviewer: {num_proposed} correction(s) proposed, {len(applied)} applied"
    )
    if warnings:
        reporter.emit(
            f"[{label}] reviewer: {len(warnings)} correction(s) could not be applied -> warning"
        )

    if polish:
        text, _, _, _ = diff_editor_run(
            text=text,
            instruction=build_polish_instruction(report_description=report_description),
            client=client,
            chat_kwargs=chat_kwargs,
        )
        reporter.emit(f"[{label}] style polish applied")

    return text, applied, warnings
