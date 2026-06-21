"""Diff-editor reviewer — ported from the Lotus ``agentic_diff_editor`` and
genericized.

A mandatory fact/format repair pass for one section: the LLM returns a
structured ``CorrectionList`` of ``{search, replace, reason}`` edits, which are
applied with exact then fuzzy (>= 0.9) string matching; unapplied edits are
retried (up to ``MAX_ATTEMPTS``). Whatever cannot be applied is returned as
human-readable warnings rather than raising. An optional style-only ``polish``
pass reuses the same editor.

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


def _find_search_string(text: str, search: str, threshold: float = FUZZY_THRESHOLD) -> str | None:
    """Return the actual substring of ``text`` matching ``search``, or None.

    Handles exact, case-insensitive, and (for longer strings) fuzzy matches.
    """
    if search in text:
        return search

    low = search.lower()
    text_low = text.lower()
    if low in text_low:
        pos = text_low.find(low)
        return text[pos : pos + len(search)]

    # Too short to fuzzy-match reliably.
    if len(search) < 10:
        return None

    n = len(search)
    best: str | None = None
    best_ratio = threshold
    step = max(1, n // 4)
    for i in range(0, max(1, len(text) - n + 1), step):
        cand = text[i : i + n]
        ratio = SequenceMatcher(None, low, cand.lower()).ratio()
        if ratio >= best_ratio:
            best_ratio = ratio
            best = cand
    return best


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
