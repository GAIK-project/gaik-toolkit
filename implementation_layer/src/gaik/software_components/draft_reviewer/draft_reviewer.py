"""Fact-check generated text against reference material with exact search-and-replace edits."""

from __future__ import annotations

from collections.abc import Mapping
from difflib import SequenceMatcher

from pydantic import BaseModel, ConfigDict, Field

from gaik.software_components.llm import create_llm_client
from gaik.software_components.source_material import (
    SourceMaterial,
    with_source_material_instruction,
)

from .models import Edit, ReviewResult
from .prompts import SYSTEM_PROMPT, check_prompt, retry_prompt, review_instruction


class EditList(BaseModel):
    """The reviewer's structured answer."""

    model_config = ConfigDict(extra="forbid")

    edits: list[Edit]


class RetryEdit(Edit):
    """An edit in a retry answer, naming the failed edit it makes."""

    model_config = ConfigDict(extra="forbid")

    answers: str = Field(
        description="The id of the failed edit that this edit makes, such as F1, copied "
        "from the failed_edits block; an empty string for an edit that makes none of them."
    )


class RetryEditList(BaseModel):
    """The reviewer's structured answer to a retry request."""

    model_config = ConfigDict(extra="forbid")

    edits: list[RetryEdit]


def _plain(edit: Edit) -> Edit:
    """The edit as a plain ``Edit``, without a retry answer's ``answers`` field."""
    return Edit(search=edit.search, replace=edit.replace, reason=edit.reason)


def _apply(text: str, edits: list[Edit]) -> tuple[str, list[Edit], list[tuple[int, Edit, str]]]:
    """Apply edits in order where the search text occurs exactly once.

    Failed edits come back with their position in ``edits``.
    """
    applied: list[Edit] = []
    failed: list[tuple[int, Edit, str]] = []
    for index, edit in enumerate(edits):
        count = text.count(edit.search)
        if not edit.search:
            failed.append((index, edit, "the search text is empty"))
        elif count == 0:
            failed.append((index, edit, "not found in the text"))
        elif count > 1:
            failed.append(
                (index, edit, f"found {count} times, add surrounding words to make it unique")
            )
        else:
            text = text.replace(edit.search, edit.replace, 1)
            applied.append(edit)
    return text, applied, failed


LEFT_OUT = "left out of the last answer, propose it again"


def _closeness(a: str, b: str) -> float:
    """How alike two texts are, from 0 to 1; 1 when one contains the other."""
    a, b = a.strip(), b.strip()
    if a and b and (a in b or b in a):
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _answer_score(edit: Edit, earlier: Edit) -> float | None:
    """How well a retry edit stands for an earlier failed edit, or None when it does not.

    Used only when a retry answer names no failed edit by its id. It does when it gives
    the same reason, or makes the same correction: a replacement whose text contains the
    earlier replacement or is contained in it, or a deletion of text like the text the
    earlier deletion meant to delete. Closer search texts score higher, so each earlier
    edit is paired with the retry edit nearest to it.
    """
    closeness = _closeness(edit.search, earlier.search)
    if edit.reason.strip() and edit.reason.strip() == earlier.reason.strip():
        return 2.0 + closeness
    old, new = earlier.replace.strip(), edit.replace.strip()
    if not old:
        return 1.0 + closeness if not new and closeness >= 0.5 else None
    if new and (old in new or new in old):
        return 1.0 + closeness
    return None


def _match_by_text(previous: dict[str, Edit], edits: list[Edit]) -> dict[int, str]:
    """Pair retry edits with earlier failed edits by their text, one to one.

    The best-scoring pairs are taken first, so one retried deletion or correction
    cannot account for several earlier ones.
    """
    pairs = sorted(
        (
            (score, order, j, fid)
            for order, (fid, earlier) in enumerate(previous.items())
            for j, edit in enumerate(edits)
            if (score := _answer_score(edit, earlier)) is not None
        ),
        key=lambda pair: (-pair[0], pair[1], pair[2]),
    )
    owner: dict[int, str] = {}
    for _, _, j, fid in pairs:
        if fid not in owner.values() and j not in owner:
            owner[j] = fid
    return owner


def _owners(previous: dict[str, Edit], edits: list[Edit]) -> dict[int, str]:
    """Which earlier failed edit each retry edit makes, as {retry index: failed id}.

    A retry edit names its failed edit by id. Each id is taken by the first edit that
    names it; an edit that names no known id is a new edit. Only when the answer names
    no known id at all (a model that ignores the field) are the edits paired with the
    failed ones by their text instead.
    """
    owner: dict[int, str] = {}
    for j, edit in enumerate(edits):
        fid = getattr(edit, "answers", "").strip().upper()
        if fid in previous and fid not in owner.values():
            owner[j] = fid
    return owner or _match_by_text(previous, edits)


class DraftReviewer:
    """Fact-check a text against reference material and apply exact corrections."""

    def __init__(
        self,
        config: dict,
        model: str | None = None,
        *,
        max_attempts: int = 5,
        chat_options: dict | None = None,
    ):
        """
        Args:
            config: Provider config from ``get_llm_config()``.
            model: Optional model override. Defaults to ``config["model"]``.
            max_attempts: Most LLM requests per review, the first one included.
            chat_options: Extra options for every reviewer call, such as
                ``reasoning_effort`` or ``temperature``.
        """
        if max_attempts < 1:
            raise ValueError(f"max_attempts must be at least 1, got {max_attempts}")
        self.max_attempts = max_attempts
        self.chat_options = chat_options or {}
        self.client = create_llm_client({**config, "model": model} if model else config)

    def review(
        self, draft: str, *, reference: str | Mapping[str, str], instructions: str = ""
    ) -> ReviewResult:
        """Review ``draft`` against ``reference``.

        ``reference`` is the reference text, or a mapping of names to texts (for
        example one entry per source or per earlier section); each piece goes to
        the model in its own labelled block. ``instructions`` replaces the default
        checks and stays outside the blocks. The draft and the reference are
        material: a sentence in them cannot change the checks. Edits that still do
        not match exactly once after ``max_attempts`` requests, or that a retry
        answer leaves out entirely, are returned in ``unresolved``.
        """
        if not draft.strip():
            raise ValueError("draft is empty")
        pieces = [reference] if isinstance(reference, str) else list(reference.values())
        if not any(piece.strip() for piece in pieces):
            raise ValueError("reference is empty")
        system = with_source_material_instruction(SYSTEM_PROMPT)
        text = draft
        applied: list[Edit] = []
        # Each failed edit keeps one id, such as F1, until a retry edit that names it
        # applies; the retry request lists the ids and the retry answer names them.
        failed: dict[str, tuple[Edit, str]] = {}
        made = 0
        material = SourceMaterial()
        for attempt in range(1, self.max_attempts + 1):
            # The same block id for every request of this review, so the instruction
            # stays the same across retries; a new one only when an applied or failed
            # edit has written the current id into what is sent.
            sent = [text] + [f"{e.search}\n{e.replace}\n{e.reason}" for e, _ in failed.values()]
            if any(material.boundary in piece for piece in sent):
                material = SourceMaterial()
            if failed:
                prompt = retry_prompt(
                    text,
                    [(fid, e, error) for fid, (e, error) in failed.items()],
                    attempt - 1,
                    material,
                )
                response_format = RetryEditList
            else:
                prompt = check_prompt(text, material)
                response_format = EditList
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": review_instruction(reference, instructions, material)},
                {"role": "user", "content": prompt},
            ]
            edits = self.client.chat_parsed(
                messages, response_format=response_format, **self.chat_options
            ).edits
            if not edits:
                break
            previous = {fid: e for fid, (e, _) in failed.items()}
            owner = _owners(previous, edits) if previous else {}
            text, done, missed = _apply(text, [_plain(e) for e in edits])
            applied.extend(done)
            # A failed edit that no retry edit makes stays failed under its id, so it is
            # asked for again and ends in ``unresolved`` rather than disappearing. One
            # whose retry edit fails too is carried once, as that retry edit.
            failed = {
                fid: (e, LEFT_OUT) for fid, e in previous.items() if fid not in owner.values()
            }
            for j, edit, error in missed:
                fid = owner.get(j)
                if fid is None:
                    made += 1
                    fid = f"F{made}"
                failed[fid] = (edit, error)
            if not failed:
                break
        return ReviewResult(
            text=text, applied=applied, unresolved=[edit for edit, _ in failed.values()]
        )
