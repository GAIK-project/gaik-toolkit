"""Fact-check generated text against reference material with exact search-and-replace edits."""

from __future__ import annotations

import re
from collections.abc import Mapping
from difflib import SequenceMatcher

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


_FAILED_ID = re.compile(r"F\d+")
_DIGIT_RUNS = re.compile(r"\d+")


def _split_ids(value: str | list[str]) -> list[str]:
    """The failed-edit ids written in ``value``, such as ``["F1", "F2"]`` for "f1, F2"."""
    text = value if isinstance(value, str) else " ".join(str(v) for v in value)
    return list(dict.fromkeys(_FAILED_ID.findall(text.upper())))


class RetryEdit(Edit):
    """An edit in a retry answer, naming the failed edits it makes."""

    model_config = ConfigDict(extra="forbid")

    answers: list[str] = Field(
        description='The ids of the failed edits that this edit makes, such as ["F1"], or '
        '["F1", "F2"] when one edit makes both, copied from the failed_edits block; an '
        "empty list for an edit that makes none of them."
    )

    @field_validator("answers", mode="before")
    @classmethod
    def _ids(cls, value):
        # One id written as a string ("F1", or "F1, F2") is taken as before.
        return _split_ids(value) if isinstance(value, str) else value


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


_DELETION_CLOSENESS = 0.8
"""How alike a retried deletion's search must be to the failed one's to stand for it."""


def _answer_score(edit: Edit, earlier: Edit) -> float | None:
    """How well a retry edit stands for an earlier failed edit, or None when it does not.

    Used only for a retry edit without the ``answers`` field. It does when it makes the
    same correction: a replacement whose text contains the earlier replacement or is
    contained in it, or, for a deletion, a deletion of nearly the same text (search texts
    at least 80% alike, with the same numbers: deleting " Built in 2021." does not stand
    for deleting " Built in 2020."). A shared reason alone is not enough, since a generic
    one ("Not in the reference.") fits unrelated deletions; it only ranks a pair higher.
    Closer search texts score higher, so each earlier edit is paired with the retry edit
    nearest to it.
    """
    closeness = _closeness(edit.search, earlier.search)
    old, new = earlier.replace.strip(), edit.replace.strip()
    if not old:
        matched = (
            not new
            and closeness >= _DELETION_CLOSENESS
            and _DIGIT_RUNS.findall(edit.search) == _DIGIT_RUNS.findall(earlier.search)
        )
    else:
        matched = bool(new) and (old in new or new in old)
    if not matched:
        return None
    same_reason = bool(edit.reason.strip()) and edit.reason.strip() == earlier.reason.strip()
    return 1.0 + closeness + (1.0 if same_reason else 0.0)


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


def _carries_answers(edit: Edit) -> bool:
    """Whether a retry edit says which failed edits it makes: its ``answers`` field is
    set, also to an empty list. A plain :class:`Edit`, or one whose model left the field
    out, does not."""
    return "answers" in getattr(edit, "model_fields_set", ())


def _owners(previous: dict[str, Edit], edits: list[Edit]) -> dict[int, list[str]]:
    """Which earlier failed edits each retry edit makes, as {retry index: failed ids}.

    A retry edit that carries ``answers`` makes exactly the failed edits it names there,
    one or several; each id is taken by the first edit that names it, and an empty list
    or an unknown id makes none of them, whatever its text. Only a retry edit without the
    field (a model or client that leaves it out) is paired with a remaining failed edit
    by its text (:func:`_answer_score`).
    """
    owner: dict[int, list[str]] = {}
    taken: set[str] = set()
    unnamed: list[int] = []
    for j, edit in enumerate(edits):
        if not _carries_answers(edit):
            unnamed.append(j)
            continue
        mine = [fid for fid in _split_ids(edit.answers) if fid in previous and fid not in taken]
        if mine:
            owner[j] = mine
            taken.update(mine)
    if unnamed:
        rest = {fid: e for fid, e in previous.items() if fid not in taken}
        by_text = _match_by_text(rest, [edits[j] for j in unnamed])
        owner.update({unnamed[k]: [fid] for k, fid in by_text.items()})
    return owner


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
            claimed = {fid for ids in owner.values() for fid in ids}
            text, done, missed = _apply(text, [_plain(e) for e in edits])
            applied.extend(done)
            # A failed edit that no retry edit makes stays failed under its id, so it is
            # asked for again and ends in ``unresolved`` rather than disappearing. One
            # whose retry edit fails too is carried once, as that retry edit, under the
            # first id it names (it stands for the others it names as well).
            failed = {fid: (e, LEFT_OUT) for fid, e in previous.items() if fid not in claimed}
            for j, edit, error in missed:
                ids = owner.get(j)
                if ids:
                    fid = ids[0]
                else:
                    made += 1
                    fid = f"F{made}"
                failed[fid] = (edit, error)
            if not failed:
                break
        return ReviewResult(
            text=text, applied=applied, unresolved=[edit for edit, _ in failed.values()]
        )
