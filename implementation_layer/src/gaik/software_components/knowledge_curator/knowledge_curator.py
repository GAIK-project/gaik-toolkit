"""Section-bound curation of fact units with verified verbatim quotes.

This module implements KnowledgeCurator, which extracts, for each non-derived report
section, the fact units, missing required items and source conflicts from normalized
sources, and checks every quote against the source it cites.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gaik.software_components.llm import create_llm_client
from gaik.software_components.llm.base import usage_since
from gaik.software_components.source_normalizer.models import NormalizedSources

from .models import (
    Conflict,
    DroppedUnit,
    FactUnit,
    KnowledgeBase,
    SectionKnowledge,
    SectionSpec,
    SourceRef,
    check_sections,
    quote_in_text,
)
from .prompts import SYSTEM_PROMPT, build_retry_prompt, build_user_prompt

logger = logging.getLogger(__name__)


class CuratedUnit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(description="Short noun phrase naming what the fact is about.")
    time_qualifier: str | None = Field(
        description="When the fact holds, e.g. '1998' or 'at inspection'; null if not time-bound."
    )
    summary: str = Field(description="The fact in one or two sentences, in the report language.")
    quote: str = Field(
        description="Exact words copied letter for letter from the cited source: a short "
        "contiguous span, no ellipses, no paraphrase."
    )
    source: SourceRef
    confidence: Literal["high", "medium", "low"] = Field(
        description="How clearly the source states the fact."
    )


class CuratedConflict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(description="The topic the sources disagree on.")
    description: str = Field(
        description="What each source says and, if resolved, which side the source "
        "hierarchy follows and why."
    )
    status: Literal["resolved", "unresolved"] = Field(
        description="'resolved' if the source hierarchy decides the conflict, else 'unresolved'."
    )
    unit_numbers: list[int] = Field(
        description="1-based positions in units of the units that disagree, both sides."
    )


class CurationResponse(BaseModel):
    """The curated knowledge of one report section."""

    model_config = ConfigDict(extra="forbid")

    units: list[CuratedUnit] = Field(description="Facts relevant to the section, one per unit.")
    missing: list[str] = Field(
        description="Required items that no source covers, each phrased as the item."
    )
    conflicts: list[CuratedConflict] = Field(
        description="Disagreements between sources on the same topic."
    )


def _failing_units(
    answer: CurationResponse, sources: NormalizedSources
) -> list[tuple[int, str, str]]:
    """``(position, reason, message)`` of every unit whose quote fails the check."""
    texts = {s.file: s.text for s in sources.sources}
    failures = []
    for n, unit in enumerate(answer.units, start=1):
        if unit.source.file not in texts:
            failures.append(
                (
                    n,
                    "file is not a source",
                    f'unit {n}: file "{unit.source.file}" is not a source; quote "{unit.quote}"',
                )
            )
        elif not quote_in_text(unit.quote, texts[unit.source.file]):
            failures.append(
                (
                    n,
                    "quote not found in source",
                    f'unit {n}: quote "{unit.quote}" not found in "{unit.source.file}"',
                )
            )
    return failures


def _check_conflicts(section: SectionSpec, answer: CurationResponse) -> None:
    """Raise ``ValueError`` if a conflict refers to a unit position that does not exist."""
    for c in answer.conflicts:
        bad = [n for n in c.unit_numbers if not 1 <= n <= len(answer.units)]
        if bad:
            raise ValueError(
                f"Section {section.id!r}: conflict {c.topic!r} refers to unit positions {bad}, "
                f"but the section has {len(answer.units)} units"
            )


def _without_units(answer: CurationResponse, dropped: set[int]) -> CurationResponse:
    """The answer without the units at the 1-based positions ``dropped``.

    Conflicts are renumbered to the remaining units; a conflict left with fewer than two
    units has no two sides any more and is removed. Positions must have been checked.
    """
    kept = [n for n in range(1, len(answer.units) + 1) if n not in dropped]
    renumber = {old: new for new, old in enumerate(kept, start=1)}
    conflicts = []
    for c in answer.conflicts:
        numbers = [renumber[n] for n in c.unit_numbers if n in renumber]
        if len(set(numbers)) >= 2:
            conflicts.append(c.model_copy(update={"unit_numbers": numbers}))
    return answer.model_copy(
        update={"units": [answer.units[n - 1] for n in kept], "conflicts": conflicts}
    )


def _to_knowledge(
    section: SectionSpec, answer: CurationResponse, sources: NormalizedSources
) -> SectionKnowledge:
    _check_conflicts(section, answer)
    ids = [f"{section.id}-{n:02d}" for n in range(1, len(answer.units) + 1)]
    units = [
        FactUnit(id=uid, source_class=sources.get(u.source.file).source_class, **u.model_dump())
        for uid, u in zip(ids, answer.units, strict=True)
    ]
    conflicts = []
    for c in answer.conflicts:
        conflicts.append(
            Conflict(
                topic=c.topic,
                description=c.description,
                status=c.status,
                unit_ids=[ids[n - 1] for n in c.unit_numbers],
            )
        )
    return SectionKnowledge(
        section_id=section.id, units=units, missing=answer.missing, conflicts=conflicts
    )


class KnowledgeCurator:
    """Curate section-bound fact units with verbatim quotes from normalized sources."""

    def __init__(
        self,
        config: dict,
        model: str | None = None,
        *,
        max_workers: int = 4,
        chat_options: dict | None = None,
        drop_unverified: bool = True,
    ):
        """
        Args:
            config: LLM config from `get_llm_config()`.
            model: Optional model override. Defaults to the config's model.
            max_workers: Number of sections curated in parallel.
            chat_options: Extra options for every curator call, such as
                `reasoning_effort` or `temperature`.
            drop_unverified: If a quote still fails the check after the retry, drop the
                failing facts, keep the rest of the section and list them in
                `KnowledgeBase.dropped`. With `False`, `curate()` raises `ValueError`.
        """
        self.max_workers = max_workers
        self.drop_unverified = drop_unverified
        self.chat_options = chat_options or {}
        self.client = create_llm_client({**config, "model": model} if model else config)

    def curate(
        self,
        sources: NormalizedSources,
        sections: Sequence[SectionSpec],
        *,
        instructions: str = "",
        progress_callback: Callable[[str], None] | None = None,
    ) -> KnowledgeBase:
        """Curate every non-derived section, one LLM call per section, in parallel.

        Args:
            sources: The normalized sources.
            sections: The report sections; derived sections are skipped.
            instructions: Report-level instructions: source hierarchy, scope and style.
            progress_callback: Called with a status line when a section starts and ends,
                possibly from a worker thread. An exception it raises stops the run.

        Raises:
            ValueError: If there are no sources or no section to curate, a conflict
                refers to a unit that does not exist, or, with `drop_unverified=False`,
                a quote still fails the check after one retry.
        """
        check_sections(sections)
        if not sources.sources:
            raise ValueError("No sources to curate from")
        curated = [s for s in sections if not s.derived]
        if not curated:
            raise ValueError("No non-derived section to curate")
        before = self.client.usage.snapshot()
        pool = ThreadPoolExecutor(max_workers=self.max_workers)
        try:
            futures = [
                pool.submit(self._curate_section, sources, s, instructions, progress_callback)
                for s in curated
            ]
            results = [f.result() for f in futures]
            return KnowledgeBase(
                sections=[knowledge for knowledge, _ in results],
                usage=usage_since(before, self.client.usage.snapshot()),
                dropped=[unit for _, dropped in results for unit in dropped],
            )
        finally:
            pool.shutdown(cancel_futures=True)

    def _curate_section(
        self,
        sources: NormalizedSources,
        section: SectionSpec,
        instructions: str,
        progress_callback: Callable[[str], None] | None,
    ) -> tuple[SectionKnowledge, list[DroppedUnit]]:
        if progress_callback:
            progress_callback(f"Curating {section.title}")
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(sources, section, instructions)},
        ]
        answer = self.client.chat_parsed(
            messages, response_format=CurationResponse, **self.chat_options
        )
        failing = _failing_units(answer, sources)
        if failing:
            failures = [message for _, _, message in failing]
            logger.warning("Section %r: retrying after quote failures %s", section.id, failures)
            messages = [
                *messages,
                {"role": "assistant", "content": answer.model_dump_json()},
                {"role": "user", "content": build_retry_prompt(failures)},
            ]
            answer = self.client.chat_parsed(
                messages, response_format=CurationResponse, **self.chat_options
            )
            failing = _failing_units(answer, sources)
            if failing and not self.drop_unverified:
                raise ValueError(
                    f"Section {section.id!r}: quotes not found in their sources after one "
                    f"retry: {[message for _, _, message in failing]}"
                )
        dropped: list[DroppedUnit] = []
        if failing:
            # Range-check before the positions change, so a bad conflict still raises.
            _check_conflicts(section, answer)
            dropped = [
                DroppedUnit(
                    section_id=section.id,
                    topic=answer.units[n - 1].topic,
                    summary=answer.units[n - 1].summary,
                    quote=answer.units[n - 1].quote,
                    file=answer.units[n - 1].source.file,
                    reason=reason,
                )
                for n, reason, _ in failing
            ]
            logger.warning(
                "Section %r: dropped %d unit(s) whose quote failed the check after the retry: %s",
                section.id,
                len(dropped),
                [message for _, _, message in failing],
            )
            answer = _without_units(answer, {n for n, _, _ in failing})
            if progress_callback:
                progress_callback(
                    f"Dropped {len(dropped)} fact(s) of {section.title}: "
                    "the quote is not in its source"
                )
        knowledge = _to_knowledge(section, answer, sources)
        if progress_callback:
            progress_callback(
                f"Curated {section.title}: {len(knowledge.units)} units, "
                f"{len(knowledge.missing)} missing, {len(knowledge.conflicts)} conflicts"
            )
        return knowledge, dropped
