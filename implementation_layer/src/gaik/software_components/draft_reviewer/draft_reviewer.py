"""Fact-check generated text against reference material with exact search-and-replace edits."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict

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


def _apply(text: str, edits: list[Edit]) -> tuple[str, list[Edit], list[tuple[Edit, str]]]:
    """Apply edits in order where the search text occurs exactly once."""
    applied: list[Edit] = []
    failed: list[tuple[Edit, str]] = []
    for edit in edits:
        count = text.count(edit.search)
        if not edit.search:
            failed.append((edit, "the search text is empty"))
        elif count == 0:
            failed.append((edit, "not found in the text"))
        elif count > 1:
            failed.append((edit, f"found {count} times, add surrounding words to make it unique"))
        else:
            text = text.replace(edit.search, edit.replace, 1)
            applied.append(edit)
    return text, applied, failed


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
        failed: list[tuple[Edit, str]] = []
        material = SourceMaterial()
        for attempt in range(1, self.max_attempts + 1):
            # The same block id for every request of this review, so the instruction
            # stays the same across retries; a new one only when an applied or failed
            # edit has written the current id into what is sent.
            sent = [text] + [f"{e.search}\n{e.replace}\n{e.reason}" for e, _ in failed]
            if any(material.boundary in piece for piece in sent):
                material = SourceMaterial()
            prompt = (
                retry_prompt(text, failed, attempt - 1, material)
                if failed
                else check_prompt(text, material)
            )
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": review_instruction(reference, instructions, material)},
                {"role": "user", "content": prompt},
            ]
            edits = self.client.chat_parsed(
                messages, response_format=EditList, **self.chat_options
            ).edits
            if not edits:
                break
            text, done, failed = _apply(text, edits)
            applied.extend(done)
            if not failed:
                break
        return ReviewResult(text=text, applied=applied, unresolved=[edit for edit, _ in failed])
