"""Section-bound curation of fact units with verified verbatim quotes.

This module implements KnowledgeCurator, which extracts, for each non-derived report
section, the fact units, missing required items and source conflicts from normalized
sources, and checks every quote against the source it cites.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gaik.software_components.llm import create_llm_client
from gaik.software_components.llm.base import usage_since
from gaik.software_components.source_material import (
    _ANGLE,
    SourceMaterial,
    clean_label,
    source_material_messages,
)
from gaik.software_components.source_normalizer.models import NormalizedSources

from .models import (
    Conflict,
    DroppedUnit,
    FactUnit,
    KnowledgeBase,
    SectionKnowledge,
    SectionSpec,
    SourceRef,
    _quote_in_squashed,
    _squash,
    check_sections,
)
from .prompts import SYSTEM_PROMPT, build_retry_prompt, build_user_prompt, source_labels

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
    description: str = Field(description="What each source says, without deciding between them.")
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


class _Cited:
    """What the checks of one run need about the sources, computed once per run.

    ``texts`` holds each source's text with its whitespace squashed, by file name;
    ``labels`` the block label of each file (:func:`source_labels`); ``files`` the file
    a label, or the cleaned form of a file name, stands for.
    """

    def __init__(self, sources: NormalizedSources) -> None:
        self.texts = {s.file: _squash(s.text) for s in sources.sources}
        self.labels = source_labels(sources)
        self.files: dict[str, str] = {}
        cleaned: dict[str, list[str]] = {}
        for file in self.texts:
            cleaned.setdefault(clean_label(file), []).append(file)
        for name, files in cleaned.items():
            if name and len(files) == 1 and name not in self.texts:
                self.files[name] = files[0]
        for file, label in self.labels.items():
            if label != file:
                self.files[label] = file

    def label(self, file: str) -> str:
        """The label a file was shown with; any other name as it is."""
        return self.labels.get(file, file)


def _verbatim_quote(quote: str, squashed_text: str) -> str | None:
    """The source's own words for a quote that holds an escaped closing tag, or None.

    A closing block tag written in a source reaches the model with its bracket escaped
    as ``&lt;``. Each ``&lt;`` of the quote may stand for one such bracket, ``<`` or one
    of its look-alikes (or for itself); the span found is copied from the source, so it
    is verbatim. A quote with nothing but ``&lt;`` stands for no words of the source.
    """
    parts = _squash(quote).split("&lt;")
    if not any(part.strip() for part in parts):
        return None
    found = re.search(f"(?:&lt;|[{_ANGLE}])".join(re.escape(p) for p in parts), squashed_text)
    return found.group(0) if found else None


def _as_cited(answer: CurationResponse, cited: _Cited) -> CurationResponse:
    """The answer with each unit's source named by its file and its quote as the source has it.

    A unit cites the label of its source's block, which is the file name except for a
    file name that is not a clean label (see :func:`source_labels`); such a label, or
    the cleaned form of the file name, is turned back into the file name. A quote of a
    closing block tag in a source gets the source's own words back
    (:func:`_verbatim_quote`), so the quote check and ``verify_quotes`` find it.
    """
    units = []
    for unit in answer.units:
        file = unit.source.file
        if file not in cited.texts:
            file = cited.files.get(file, file)
        quote = unit.quote
        text = cited.texts.get(file)
        if text is not None and "&lt;" in quote and not _quote_in_squashed(quote, text):
            quote = _verbatim_quote(quote, text) or quote
        if file != unit.source.file or quote != unit.quote:
            unit = unit.model_copy(
                update={"quote": quote, "source": unit.source.model_copy(update={"file": file})}
            )
        units.append(unit)
    return answer.model_copy(update={"units": units})


# A number: a digit run, or groups of three digits with one thousands separator between
# them ("1 200", "1,200", "1.200", "1,250,500"). Any other separator splits numbers, so a
# date such as 14.3.2026 is 14, 3 and 2026, a decimal 1,5 is 1 and 5, and 1,250.500 is
# 1250 and 500, however a source writes it.
_NUMBER = re.compile(
    r"(?<![^\W_])(?:\d{1,3}(?P<sep>[.,\u00a0\u202f ])\d{3}(?:(?P=sep)\d{3})*(?!\d)|\d+)"
)
# A number glued to letters before it, such as the 2 in m2, CO2 or ISO9001, is part of a
# unit or a name, not a figure of the fact: the lookbehind above leaves it out, and it
# never starts inside a digit run, so it does not take the 001 of ISO9001 either.
_SEPARATORS = re.compile(r"[.,\u00a0\u202f ]")
# Every digit run, glued to letters or not: what a quote gives. "ISO9001" in a quote
# supports "ISO 9001" in the summary.
_DIGIT_RUN = re.compile(r"\d+")
# A date: the day, the month and the year; None for a day or a year it does not give
# ("March 2026" has no day).
_Date = tuple[int | None, int, int | None]

_ENGLISH_MONTHS = {
    name: n
    for n, names in enumerate(
        [
            ("january", "jan"),
            ("february", "feb"),
            ("march", "mar"),
            ("april", "apr"),
            ("may",),
            ("june", "jun"),
            ("july", "jul"),
            ("august", "aug"),
            ("september", "sep", "sept"),
            ("october", "oct"),
            ("november", "nov"),
            ("december", "dec"),
        ],
        start=1,
    )
    for name in names
}
# Also ordinary words ("may", "mar"): they count only next to a day before or a year after.
_AMBIGUOUS_MONTHS = frozenset({"may", "mar"})
_FINNISH_MONTHS = ("tammi helmi maalis huhti touko kesä heinä elo syys loka marras joulu").split()
_WORD = re.compile(r"[^\W\d_]+")
# The day before a month name: "14 March", "14th of March", "14.maaliskuuta",
# "14. päivänä maaliskuuta".
_DAY_BEFORE = re.compile(
    r"(?<!\d)(\d{1,2})(?:st|nd|rd|th)?(?:\.\s*|\s+)(?:(?:of|p\u00e4iv\u00e4n\u00e4)\s+)?$",
    re.IGNORECASE,
)
_DAY_AFTER = re.compile(r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?!\d)")
_YEAR_AFTER = re.compile(r"\.?\s+(?:\d{1,2}(?:st|nd|rd|th)?,?\s+)?(\d{4})(?!\d)")
# A date written with numbers: 14.3.2026, 14.3. (the closing dot tells it from 14.3, a
# decimal), 2026-03-14, or a month and a year, 3/2026.
_NUMERIC_DATE = re.compile(
    r"(?<![\d.])(?P<d>\d{1,2})\.(?P<m>\d{1,2})\.(?P<y>\d{4}(?!\d))?"
    r"|(?<![\d-])(?P<iy>\d{4})-(?P<im>\d{1,2})-(?P<id>\d{1,2})(?!\d)"
    r"|(?<![\d./])(?P<mm>\d{1,2})/(?P<my>\d{4})(?!\d)"
)


def _month_number(word: str) -> int | None:
    """The number of a month name, English or Finnish, in any case or inflection
    ("March", "MARCH", "maaliskuuta", "maaliskuussa"); None for any other word."""
    lower = word.lower()
    if lower in _ENGLISH_MONTHS:
        return _ENGLISH_MONTHS[lower]
    for n, stem in enumerate(_FINNISH_MONTHS, start=1):
        if lower.startswith(stem + "kuu"):
            return n
    return None


def _word_dates(text: str) -> set[_Date]:
    """Every date in ``text`` whose month is a word: "14 March 2026", "the 14th of March",
    "14. maaliskuuta", "March 14, 2026", and a month with a year, "maaliskuussa 2026". A
    month name with neither a day nor a year beside it gives none; "may" and "mar" count
    only after a day or before a year, since they are also words."""
    dates: set[_Date] = set()
    for match in _WORD.finditer(text):
        word = match.group(0)
        month = _month_number(word)
        if month is None:
            continue
        before = _DAY_BEFORE.search(text, 0, match.start())
        after = _DAY_AFTER.match(text, match.end())
        year = _YEAR_AFTER.match(text, match.end())
        if word.lower() in _AMBIGUOUS_MONTHS and not before and not year:
            continue  # "May 2 units fail": a day after "May" alone is not a date
        day = int(before.group(1)) if before else int(after.group(1)) if after else None
        if day is not None and not 1 <= day <= 31:
            continue
        if day is None and not year:
            continue
        dates.add((day, month, int(year.group(1)) if year else None))
    return dates


def _numeric_dates(text: str) -> list[tuple[_Date, list[tuple[int, int]], int | None]]:
    """Every date in ``text`` written with numbers, with the spans of its day and month
    and the start of its year (None without one)."""
    found: list[tuple[_Date, list[tuple[int, int]], int | None]] = []
    for match in _NUMERIC_DATE.finditer(text):
        if match.group("mm") is not None:
            month = int(match.group("mm"))
            if 1 <= month <= 12:
                year = int(match.group("my"))
                found.append(((None, month, year), [match.span("mm")], match.start("my")))
            continue
        if match.group("d") is not None:
            d, m, y = "d", "m", "y"
        else:
            d, m, y = "id", "im", "iy"
        day, month = int(match.group(d)), int(match.group(m))
        if not (1 <= day <= 31 and 1 <= month <= 12):
            continue
        year = int(match.group(y)) if match.group(y) else None
        spans = [match.span(d), match.span(m)]
        found.append(((day, month, year), spans, match.start(y) if year is not None else None))
    return found


def _dates(text: str) -> set[_Date]:
    """Every date in ``text``, its month written as a word or as a number."""
    return _word_dates(text) | {date for date, _, _ in _numeric_dates(text)}


def _same_day(date: _Date, given: set[_Date]) -> _Date | None:
    """A date of ``given`` on the same day and month as ``date``, with the same year if
    both have one; one with the same year first. A month and a year (no day) needs the
    same month and year."""
    day, month, year = date
    if day is None:
        matches = [g for g in given if g[1] == month and g[2] == year]
    else:
        matches = [
            g for g in given if g[:2] == (day, month) and (year is None or g[2] in (year, None))
        ]
    return max(matches, key=lambda g: g[2] == year, default=None)


def _confirmed(date: _Date, in_source: set[_Date]) -> _Date | None:
    """``date`` as far as the source has it: its day and month, and its year only when
    the source's date has the same year; None when the source has no such date."""
    match = _same_day(date, in_source)
    if match is None:
        return None
    return date if match[2] == date[2] else (date[0], date[1], None)


def _digits(number: str) -> str:
    """A number's digits without separators or leading zeros: "1 200,50" -> "120050"."""
    return _SEPARATORS.sub("", number).lstrip("0") or "0"


def _numbers(text: str) -> list[str]:
    """Every number in ``text`` as written, by :data:`_NUMBER`."""
    return [m.group(0) for m in _NUMBER.finditer(text)]


def _given_numbers(text: str) -> set[str]:
    """The digits of every number in ``text``, of each group of a grouped one, and of
    every digit run glued to letters.

    "4 120" may be one figure or two (a count and an area), so both readings count; the
    9001 of "ISO9001" counts too, so a summary may write it "ISO 9001". A month written as
    a word gives no number here: it supports only the same date (:func:`_dated_numbers`).
    """
    given = {_digits(run) for run in _DIGIT_RUN.findall(text)}
    for n in _numbers(text):
        given.add(_digits(n))
        given.update(_digits(part) for part in _SEPARATORS.split(n) if part)
    return given


def _dated_numbers(summary: str, given: set[_Date]) -> set[int]:
    """The start of each number in ``summary`` that a date of ``given`` supports.

    A date the summary writes with numbers, 14.3.2026 or 14.3., is supported by the same
    day and month in ``given``, however the source writes it ("14 March 2026"); its year
    only when that date has the same year, otherwise the year is checked like any number.
    """
    starts: set[int] = set()
    for date, spans, year_start in _numeric_dates(summary):
        match = _same_day(date, given)
        if match is None:
            continue
        starts.update(start for start, _ in spans)
        if year_start is not None and match[2] == date[2]:
            starts.add(year_start)
    return starts


def _unsupported_numbers(unit: CuratedUnit, source_text: str | None = None) -> list[str]:
    """The numbers of the summary that neither the quote nor the time qualifier gives.

    The quote check confirms only that the quote is in its source; this confirms that the
    summary states no number of its own, such as an age computed from a year or a figure
    copied from another part of the source. Numbers are compared by their digits, so
    "1 200" in the quote supports "1200" and "03" supports "3". A date the summary writes
    with numbers (14.3.2026) is also supported by the same date with its month as a word
    ("14 March 2026"); the month's number supports nothing else. A number the summary
    writes in words is not checked.
    """
    given = _given_numbers(unit.quote)
    dates = _dates(unit.quote)
    # The time qualifier is the model's own text: its numbers and dates count only where
    # the cited source has them too.
    qualifier = _given_numbers(unit.time_qualifier or "")
    qualifier_dates = _dates(unit.time_qualifier or "")
    if source_text is not None:
        qualifier &= _given_numbers(source_text)
        in_source = _dates(source_text)
        qualifier_dates = {
            confirmed
            for date in qualifier_dates
            if (confirmed := _confirmed(date, in_source)) is not None
        }
    given |= qualifier
    dated = _dated_numbers(unit.summary, dates | qualifier_dates)
    return [
        m.group(0)
        for m in _NUMBER.finditer(unit.summary)
        if m.start() not in dated and _digits(m.group(0)) not in given
    ]


def _failing_units(answer: CurationResponse, cited: _Cited) -> list[tuple[int, str, str]]:
    """``(position, reason, message)`` of every unit whose quote fails the check, or
    whose summary states a number its quote does not give.

    The message names a source by the label the model saw it under.
    """
    failures = []
    for n, unit in enumerate(answer.units, start=1):
        if unit.source.file not in cited.texts:
            failures.append(
                (
                    n,
                    "file is not a source",
                    f'unit {n}: file "{unit.source.file}" is not a source; quote "{unit.quote}"',
                )
            )
        elif not _quote_in_squashed(unit.quote, cited.texts[unit.source.file]):
            failures.append(
                (
                    n,
                    "quote not found in source",
                    f'unit {n}: quote "{unit.quote}" not found in '
                    f'"{cited.label(unit.source.file)}"',
                )
            )
        elif unsupported := _unsupported_numbers(unit, cited.texts[unit.source.file]):
            failures.append(
                (
                    n,
                    "summary states a number the quote does not",
                    f"unit {n}: the summary states {unsupported}, which the quote "
                    f'"{unit.quote}" does not give',
                )
            )
    return failures


def _log_summary(failing: list[tuple[int, str, str]], bad_conflicts: list[str]) -> list[str]:
    """What a log line says about failures: unit positions and reasons, no source text.

    The full messages quote the sources and name the conflicts' topics; they
    go back to the model in the retry prompt and into the raised error, not
    into the log.
    """
    summary = [f"unit {n}: {reason}" for n, reason, _ in failing]
    if bad_conflicts:
        summary.append(f"{len(bad_conflicts)} conflict(s) refer to missing units")
    return summary


def _failing_conflicts(answer: CurationResponse) -> list[str]:
    """A message for every conflict that refers to a unit position that does not exist."""
    count = len(answer.units)
    failures = []
    for c in answer.conflicts:
        bad = [n for n in c.unit_numbers if not 1 <= n <= count]
        if bad:
            failures.append(
                f'conflict "{c.topic}" refers to unit positions {bad}, '
                f"but the section has {count} units"
            )
    return failures


def _check_conflicts(section: SectionSpec, answer: CurationResponse) -> None:
    """Raise ``ValueError`` if a conflict refers to a unit position that does not exist."""
    failures = _failing_conflicts(answer)
    if failures:
        raise ValueError(f"Section {section.id!r}: {'; '.join(failures)}")


def _without_units(answer: CurationResponse, dropped: set[int]) -> CurationResponse:
    """The answer without the units at the 1-based positions ``dropped``.

    Conflicts are renumbered to the remaining units, and positions that are not a unit are
    left out; a conflict left with fewer than two units has no two sides any more and is
    removed.
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


def _check_precedence(source_precedence: Sequence[str] | None) -> tuple[str, ...]:
    """The precedence as a tuple; raise ``ValueError`` on a blank, a repeat or a bare string."""
    if source_precedence is None:
        return ()
    if isinstance(source_precedence, str):
        raise ValueError(
            "source_precedence takes a list of source classes, highest first, "
            "e.g. ['primary', 'secondary']"
        )
    ranked = tuple(source_precedence)
    if any(not isinstance(c, str) or not c.strip() for c in ranked):
        raise ValueError("source_precedence entries must be non-blank source class names")
    repeated = sorted({c for c in ranked if ranked.count(c) > 1})
    if repeated:
        raise ValueError(f"source_precedence names a class more than once: {repeated}")
    return ranked


def _decide(
    units: Sequence[FactUnit], source_precedence: tuple[str, ...]
) -> tuple[Literal["resolved", "unresolved"], list[str], str | None]:
    """``(status, preferred_unit_ids, resolved_by)`` of one conflict, decided in code.

    Resolved only when every unit's source class is in ``source_precedence`` and exactly
    one unit has the highest-ranked class among them: that unit is the side the report
    follows. Two units of the top class may disagree with each other, so they leave the
    conflict unresolved, as do units of one class only, a class the precedence does not
    name, or no precedence at all: a person decides. So does a top unit of ``low``
    confidence, a source that is itself unsure: the class does not make it right.
    """
    # Fewer than two distinct units (an empty unit_numbers list, or one unit named twice)
    # is no disagreement to rank: a person decides.
    if not source_precedence or len(units) < 2:
        return "unresolved", [], None
    rank = {c: i for i, c in enumerate(source_precedence)}
    classes = [u.source_class for u in units]
    if any(c not in rank for c in classes):
        return "unresolved", [], None
    top = min(classes, key=rank.__getitem__)
    preferred = [u.id for u in units if u.source_class == top]
    if len(preferred) != 1:
        return "unresolved", [], None
    if next(u for u in units if u.source_class == top).confidence == "low":
        return "unresolved", [], None
    return "resolved", preferred, top


def _to_knowledge(
    section: SectionSpec,
    answer: CurationResponse,
    sources: NormalizedSources,
    source_precedence: tuple[str, ...] = (),
) -> SectionKnowledge:
    _check_conflicts(section, answer)
    ids = [f"{section.id}-{n:02d}" for n in range(1, len(answer.units) + 1)]
    units = [
        FactUnit(id=uid, source_class=sources.get(u.source.file).source_class, **u.model_dump())
        for uid, u in zip(ids, answer.units, strict=True)
    ]
    conflicts = []
    for c in answer.conflicts:
        involved = [units[n - 1] for n in dict.fromkeys(c.unit_numbers)]
        status, preferred, resolved_by = _decide(involved, source_precedence)
        conflicts.append(
            Conflict(
                topic=c.topic,
                description=c.description,
                status=status,
                unit_ids=[ids[n - 1] for n in c.unit_numbers],
                preferred_unit_ids=preferred,
                resolved_by=resolved_by,
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
                `KnowledgeBase.dropped`. A conflict that still refers to a unit that does
                not exist loses that reference, and is removed if fewer than two units are
                left. With `False`, `curate()` raises `ValueError` in both cases.
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
        source_precedence: Sequence[str] | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> KnowledgeBase:
        """Curate every non-derived section, one LLM call per section, in parallel.

        Args:
            sources: The normalized sources.
            sections: The report sections; derived sections are skipped.
            instructions: Report-level instructions: scope, style and how the report
                words each kind of source. They do not decide conflicts.
            source_precedence: Source classes, highest first, e.g.
                ``["primary", "secondary"]``. A conflict is resolved in code when one
                unit of the conflict has the highest-ranked class among them; the report
                then follows that side. Without it, or when the classes do not decide,
                every conflict is unresolved and the report gives both sides.
            progress_callback: Called with a status line when a section starts and ends,
                possibly from a worker thread. An exception it raises stops the run.

        Raises:
            ValueError: If there are no sources or no section to curate,
                ``source_precedence`` is a bare string or names a class twice, or, with
                `drop_unverified=False`, a quote still fails the check or a conflict still
                refers to a unit that does not exist after one retry.
        """
        check_sections(sections)
        precedence = _check_precedence(source_precedence)
        if not sources.sources:
            raise ValueError("No sources to curate from")
        curated = [s for s in sections if not s.derived]
        if not curated:
            raise ValueError("No non-derived section to curate")
        before = self.client.usage.snapshot()
        pool = ThreadPoolExecutor(max_workers=self.max_workers)
        try:
            cited = _Cited(sources)
            futures = [
                pool.submit(
                    self._curate_section,
                    sources,
                    cited,
                    s,
                    instructions,
                    precedence,
                    progress_callback,
                )
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
        cited: _Cited,
        section: SectionSpec,
        instructions: str,
        source_precedence: tuple[str, ...],
        progress_callback: Callable[[str], None] | None,
    ) -> tuple[SectionKnowledge, list[DroppedUnit]]:
        if progress_callback:
            progress_callback(f"Curating {section.title}")
        # Each source in its own block with a random id for this call; the rules stay in
        # the system message, the section and the report instructions outside the blocks.
        messages = source_material_messages(
            SYSTEM_PROMPT,
            build_user_prompt(sources, section, instructions, SourceMaterial(), cited.labels),
        )
        raw = self.client.chat_parsed(
            messages, response_format=CurationResponse, **self.chat_options
        )
        answer = _as_cited(raw, cited)
        failing = _failing_units(answer, cited)
        bad_conflicts = _failing_conflicts(answer)
        if failing or bad_conflicts:
            failures = [message for _, _, message in failing]
            logger.warning(
                "Section %r: retrying after failures %s",
                section.id,
                _log_summary(failing, bad_conflicts),
            )
            messages = [
                *messages,
                # the answer as the model gave it, citing the labels it saw
                {"role": "assistant", "content": raw.model_dump_json()},
                {"role": "user", "content": build_retry_prompt(failures, bad_conflicts)},
            ]
            answer = self.client.chat_parsed(
                messages, response_format=CurationResponse, **self.chat_options
            )
            answer = _as_cited(answer, cited)
            failing = _failing_units(answer, cited)
            bad_conflicts = _failing_conflicts(answer)
            if not self.drop_unverified:
                if failing:
                    raise ValueError(
                        f"Section {section.id!r}: units failed the quote check after one "
                        f"retry: {[message for _, _, message in failing]}"
                    )
                _check_conflicts(section, answer)
        if bad_conflicts:
            logger.warning(
                "Section %r: removed conflict references to units that do not exist after "
                "the retry: %d conflict(s)",
                section.id,
                len(bad_conflicts),
            )
            if progress_callback:
                progress_callback(
                    f"Removed references to missing units from {len(bad_conflicts)} "
                    f"conflict(s) of {section.title}"
                )
        dropped: list[DroppedUnit] = []
        if failing:
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
                "Section %r: dropped %d unit(s) that failed the quote check after the retry: %s",
                section.id,
                len(dropped),
                _log_summary(failing, []),
            )
            if progress_callback:
                progress_callback(
                    f"Dropped {len(dropped)} fact(s) of {section.title}: "
                    "the quote is not in its source or does not give the summary's numbers"
                )
        if failing or bad_conflicts:
            answer = _without_units(answer, {n for n, _, _ in failing})
        knowledge = _to_knowledge(section, answer, sources, source_precedence)
        if progress_callback:
            progress_callback(
                f"Curated {section.title}: {len(knowledge.units)} units, "
                f"{len(knowledge.missing)} missing, {len(knowledge.conflicts)} conflicts"
            )
        return knowledge, dropped
