"""Diff-editor reviewer — ported from the Lotus ``agentic_diff_editor`` and
genericized.

A mandatory fact/format repair pass for one section: the LLM returns a
structured ``CorrectionList`` of ``{search, replace, reason}`` edits. Each is
applied where its search occurs once, or else at the one passage it means once case,
quotes, dashes and whitespace are ignored, or at the one passage within 10% of it and
with the same numbers (``_span.locate``); an edit that fits no passage, or more than
one, is retried (up
to ``MAX_ATTEMPTS``). Whatever cannot be applied is returned as human-readable
warnings rather than raising. An optional style-only ``polish`` pass reuses the
same editor.

Uses GAIK's ``ProviderClient.chat_parsed(messages, response_format=...)`` for
structured output; the matching needs no extra dependencies.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from pydantic import BaseModel, Field, field_validator

from gaik.software_components.draft_reviewer.draft_reviewer import (
    LEFT_OUT,
    _owners,
    _split_ids,
)
from gaik.software_components.draft_reviewer.models import Edit
from gaik.software_components.draft_reviewer.prompts import retry_prompt
from gaik.software_components.source_material import (
    SourceMaterial,
    with_source_material_instruction,
)

from .._material import Evidence
from ._span import Span, locate
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
    answers: list[str] = Field(
        default_factory=list,
        description="In a retry: the ids of the failed edits this correction makes, such "
        'as ["F1"], or ["F1", "F2"] when one correction makes both, copied from the '
        "failed_edits block; an empty list for a correction that makes none of them.",
    )

    @field_validator("answers", mode="before")
    @classmethod
    def _ids(cls, value):
        # One id written as a string ("F1", or "F1, F2") is taken as before.
        return _split_ids(value) if isinstance(value, str) else value


class CorrectionList(BaseModel):
    """List of corrections to apply."""

    corrections: list[Correction] = Field(default_factory=list)
    explanation: str = Field(default="", description="Overall explanation (1-3 sentences).")


# ---------------------------------------------------------------------------
# Applying corrections
# ---------------------------------------------------------------------------


def _find_search_string(text: str, search: str, threshold: float = FUZZY_THRESHOLD) -> str | None:
    """Return the passage of ``text`` that ``search`` means, or None.

    Exact first, then ignoring case, quote and dash styles and whitespace runs, then
    (for 10 characters or more) a close match; a loose match must be the only one.
    """
    span = locate(text, search, threshold)
    return text[span.start : span.end] if isinstance(span, Span) else None


def _replacement(span: Span, replace: str) -> str:
    """``replace`` without the edge whitespace of the search that the text lacks there."""
    if span.lead and replace.startswith(span.lead):
        replace = replace[len(span.lead) :]
    if span.trail and replace.endswith(span.trail):
        replace = replace[: len(replace) - len(span.trail)]
    return replace


def _apply_corrections(
    text: str, corrections: list[Correction]
) -> tuple[str, list[dict], list[dict]]:
    current = text
    successful: list[dict] = []
    failed: list[dict] = []
    for index, c in enumerate(corrections):
        span = locate(current, c.search, FUZZY_THRESHOLD)
        if isinstance(span, Span):
            target = current[span.start : span.end]
            replace = _replacement(span, c.replace)
            current = current[: span.start] + replace + current[span.end :]
            successful.append({"search": target, "replace": replace, "reason": c.reason})
        else:
            failed.append(
                {
                    "search": c.search,
                    "replace": c.replace,
                    "reason": c.reason,
                    "error": span,
                    "index": index,
                }
            )
    return current, successful, failed


def _request_corrections(
    client, instruction: str, user_prompt: str, chat_kwargs: dict
) -> CorrectionList:
    messages = [
        {"role": "system", "content": with_source_material_instruction(_EDITOR_SYSTEM_PROMPT)},
        {"role": "user", "content": instruction},
        {"role": "user", "content": user_prompt},
    ]
    result = client.chat_parsed(messages, response_format=CorrectionList, **chat_kwargs)
    if isinstance(result, CorrectionList):
        return result
    # Defensive: some clients may hand back a dict / other BaseModel.
    if isinstance(result, BaseModel):
        # Unset fields stay unset: a correction without "answers" is paired by its text.
        return CorrectionList.model_validate(result.model_dump(exclude_unset=True))
    return CorrectionList.model_validate(result)


def _check_prompt(text: str, blocks: SourceMaterial) -> str:
    return (
        "Text to review (in the source_material block labelled text):\n"
        + blocks.wrap(text, label="text")
        + "\n\nIf you make corrections, copy each 'search' field EXACTLY from this text "
        "so the passage can be located."
    )


def _retry_prompt(text: str, failed: list[dict], attempt: int, blocks: SourceMaterial) -> str:
    """The DraftReviewer's retry request: every failed edit must be made again or it
    stays unresolved (and fails a strict review), so the two reviewers ask alike."""
    listed = [(f["id"], Edit(**_edit_fields(f)), f["error"]) for f in failed]
    return retry_prompt(text, listed, attempt, blocks)


def _edit_fields(failed: dict) -> dict:
    return {key: failed[key] for key in ("search", "replace", "reason")}


Instruction = str | Callable[[SourceMaterial], str]
"""The editor's instruction, or a function that builds it with the request's blocks."""


def _instruction_for(instruction: Instruction, blocks: SourceMaterial) -> str:
    return instruction(blocks) if callable(instruction) else instruction


def diff_editor_run(
    *,
    text: str,
    instruction: Instruction,
    client,
    chat_kwargs: dict,
) -> tuple[str, list[dict], list[str], int]:
    """Run the check -> apply -> retry loop.

    The requests share one block id, so the instruction stays the same across
    retries; a new id is drawn, and a callable ``instruction`` rebuilt with it, only
    when an applied or failed edit has written the current id into what is sent.

    Returns ``(corrected_text, applied_edits, warnings, num_proposed)``.
    ``warnings`` lists edits that could not be applied after all retries.
    """
    current = text
    applied: list[dict] = []

    blocks = SourceMaterial()
    first = _request_corrections(
        client, _instruction_for(instruction, blocks), _check_prompt(current, blocks), chat_kwargs
    )
    num_proposed = len(first.corrections)
    pending = first.corrections

    attempt = 0
    # Each failed edit keeps one id until a correction that makes it applies. A failed
    # edit that a retry answer leaves out stays failed, so it is asked for again and
    # ends in ``warnings`` (and fails a strict review) rather than disappearing.
    failed: list[dict] = []
    made = 0
    while pending:
        previous = {f["id"]: Correction(**_edit_fields(f)) for f in failed}
        owner = _owners(previous, pending) if previous else {}
        claimed = {fid for ids in owner.values() for fid in ids}
        current, successful, missed = _apply_corrections(current, pending)
        applied.extend(successful)
        failed = [{**f, "error": LEFT_OUT} for f in failed if f["id"] not in claimed]
        for f in missed:
            # A retry correction that makes several failed edits and fails too is
            # carried once, under the first id it names.
            ids = owner.get(f.pop("index"))
            if ids:
                fid = ids[0]
            else:
                made += 1
                fid = f"F{made}"
            failed.append({**f, "id": fid})
        attempt += 1
        if not failed:
            break
        if attempt >= MAX_ATTEMPTS:
            break
        sent = [current] + [f"{f['search']}\n{f['replace']}\n{f['reason']}" for f in failed]
        if any(blocks.boundary in piece for piece in sent):
            blocks = SourceMaterial()
        pending = _request_corrections(
            client,
            _instruction_for(instruction, blocks),
            _retry_prompt(current, failed, attempt, blocks),
            chat_kwargs,
        ).corrections

    warnings = [
        f"Unresolved reviewer edit ({f['error']}; after {attempt} attempt(s)): {f['search'][:80]!r}"
        for f in failed
    ]
    return current, applied, warnings, num_proposed


def review_and_polish(
    *,
    draft: str,
    evidence: Evidence,
    title: str,
    instructions: str,
    sample_section: str,
    has_sample: bool,
    include_source_references: bool,
    report_description: str | None,
    additional_instructions: str | None = None,
    dependencies_context: Mapping[str, str] | None,
    client,
    chat_kwargs: dict,
    polish: bool,
    reporter,
    label: str,
) -> tuple[str, list[dict], list[str]]:
    """Mandatory fact/format repair, then optional style-only polish."""

    def instruction(blocks: SourceMaterial) -> str:
        return build_reviewer_instruction(
            blocks=blocks,
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
