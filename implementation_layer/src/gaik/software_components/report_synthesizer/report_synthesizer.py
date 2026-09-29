"""Governed report writing from curated knowledge, section by section in dependency order.

This module implements ReportSynthesizer: a LangGraph workflow that writes each technical
section from its own curated knowledge, and each derived section from the reviewed texts
of the sections it depends on. Every draft is fact-checked by a DraftReviewer.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from graphlib import CycleError, TopologicalSorter
from typing import Annotated, TypedDict

try:
    from langgraph.graph import END, START, StateGraph
except ImportError as exc:
    raise ImportError(
        "ReportSynthesizer requires 'langgraph'. Install it with:\n"
        '    pip install "gaik[report-synthesizer]"'
    ) from exc

from gaik.software_components.draft_reviewer import DraftReviewer
from gaik.software_components.knowledge_curator.models import (
    KnowledgeBase,
    SectionSpec,
    check_sections,
)
from gaik.software_components.llm import create_llm_client
from gaik.software_components.llm.base import add_usage

from .models import Report, ReportSection, ReviewEntry
from .prompts import WRITER_SYSTEM_PROMPT, build_review_checks, build_writer_prompt


def _merge(left: dict, right: dict) -> dict:
    """Reducer for the dicts written by parallel section nodes."""
    return {**left, **right}


class _State(TypedDict):
    sections: Annotated[dict[str, ReportSection], _merge]
    reviews: Annotated[dict[str, ReviewEntry], _merge]


def _node(section_id: str) -> str:
    # The space keeps node names apart from the state keys and LangGraph's reserved names.
    return f"section {section_id}"


def _validate(
    knowledge: KnowledgeBase, sections: list[SectionSpec], title: str, sample_report: str | None
) -> None:
    if not title.strip():
        raise ValueError("title is empty")
    if sample_report is not None and not sample_report.strip():
        raise ValueError("sample_report is empty; pass None for no format reference")
    if not sections:
        raise ValueError("sections is empty")
    check_sections(sections)
    try:
        TopologicalSorter({s.id: s.depends_on for s in sections}).prepare()
    except CycleError as exc:
        raise ValueError(f"Cyclic section dependencies: {exc.args[1]}") from exc
    technical = [s.id for s in sections if not s.derived]
    have = [k.section_id for k in knowledge.sections]
    missing = [i for i in technical if i not in have]
    if missing:
        raise ValueError(f"No knowledge for non-derived sections: {missing}")
    extra = sorted({i for i in have if i not in technical or have.count(i) > 1})
    if extra:
        raise ValueError(f"Knowledge for unknown, derived or duplicate sections: {extra}")


class ReportSynthesizer:
    """Write a report from curated knowledge, reviewing every section against its material."""

    def __init__(
        self,
        config: dict,
        model: str | None = None,
        *,
        reviewer_model: str | None = None,
        strict_review: bool = False,
        review_attempts: int = 5,
        writer_options: dict | None = None,
        reviewer_options: dict | None = None,
    ):
        """
        Args:
            config: LLM config from `get_llm_config()`.
            model: Optional writer model override. Defaults to the config's model.
            reviewer_model: Optional reviewer model override. Defaults to the config's model.
            strict_review: Raise when a reviewer edit cannot be applied, instead of
                logging it in the review log.
            review_attempts: Most reviewer requests per section, the first one included.
            writer_options: Extra options for every writer call, such as
                `reasoning_effort` or `temperature`.
            reviewer_options: The same for every reviewer call.
        """
        self.config = config
        self.model = model
        self.reviewer_model = reviewer_model
        self.strict_review = strict_review
        self.review_attempts = review_attempts
        self.writer_options = writer_options or {}
        self.reviewer_options = reviewer_options or {}

    def synthesize(
        self,
        knowledge: KnowledgeBase,
        sections: list[SectionSpec],
        *,
        title: str,
        language: str = "English",
        instructions: str = "",
        sample_report: str | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> Report:
        """Write, review and assemble every section.

        Args:
            knowledge: The curated knowledge of exactly the non-derived sections.
            sections: The report sections in report order.
            title: The report title.
            language: The language the sections are written in.
            instructions: Report-level rules: source hierarchy, missing data, citation
                style. They go to every writer and to the reviewer checks.
            sample_report: A Markdown sample report, given to the writers as a format
                reference for structure, length and tone only. The reviewer never sees it.
            progress_callback: Called with a status line as each section is written,
                reviewed and finished, possibly from a worker thread. An exception it
                raises stops the run.

        Raises:
            ValueError: If the title is empty, the sections are invalid or cyclic, or the
                knowledge does not match the non-derived sections one to one.
            RuntimeError: If a writer answer is empty, a reviewed section is empty, or,
                with ``strict_review``, a reviewer edit cannot be applied.
        """
        _validate(knowledge, sections, title, sample_report)
        client = create_llm_client(
            {**self.config, "model": self.model} if self.model else self.config
        )
        reviewer = DraftReviewer(
            self.config,
            self.reviewer_model,
            max_attempts=self.review_attempts,
            chat_options=self.reviewer_options,
        )
        titles = {s.id: s.title for s in sections}

        def notify(message: str) -> None:
            if progress_callback:
                progress_callback(message)

        def write(section: SectionSpec) -> Callable[[_State], dict]:
            def run(state: _State) -> dict:
                if section.derived:
                    material = "\n\n".join(
                        f'<section id="{d}" title="{titles[d]}">\n'
                        f"{state['sections'][d].text}\n</section>"
                        for d in section.depends_on
                    )
                else:
                    material = knowledge.get(section.id).model_dump_json(indent=2)
                notify(f"Writing {section.title}")
                prompt = build_writer_prompt(
                    section,
                    material,
                    title=title,
                    language=language,
                    instructions=instructions,
                    sample_report=sample_report,
                )
                response = client.chat(
                    [
                        {"role": "system", "content": WRITER_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    **self.writer_options,
                )
                draft = response.text.strip()
                if re.match(r"#{1,6}\s", draft):
                    draft = draft.partition("\n")[2].strip()
                if not draft:
                    raise RuntimeError(
                        f"Section {section.id!r}: the writer returned an empty answer"
                    )
                notify(f"Reviewing {section.title}")
                result = reviewer.review(
                    draft,
                    reference=material,
                    instructions=build_review_checks(section, instructions),
                )
                if not result.text.strip():
                    raise RuntimeError(f"Section {section.id!r} is empty after review")
                if self.strict_review and result.unresolved:
                    raise RuntimeError(
                        f"Section {section.id!r}: {len(result.unresolved)} reviewer edits could "
                        f"not be applied (strict_review): {[e.search for e in result.unresolved]}"
                    )
                notify(
                    f"Finished {section.title}: {len(result.applied)} edits applied, "
                    f"{len(result.unresolved)} unresolved"
                )
                entry = ReviewEntry(
                    section_id=section.id, applied=result.applied, unresolved=result.unresolved
                )
                return {
                    "sections": {
                        section.id: ReportSection(
                            id=section.id, title=section.title, text=result.text.strip()
                        )
                    },
                    "reviews": {section.id: entry},
                }

            return run

        graph = StateGraph(_State)
        for s in sections:
            graph.add_node(_node(s.id), write(s))
        for s in sections:
            graph.add_edge([_node(d) for d in s.depends_on] if s.derived else START, _node(s.id))
            graph.add_edge(_node(s.id), END)
        # A chain of n dependent sections takes n steps, plus one for the input.
        state = graph.compile().invoke(
            {"sections": {}, "reviews": {}},
            {"recursion_limit": len(sections) + 1},
        )
        unwritten = [s.id for s in sections if s.id not in state["sections"]]
        if unwritten:
            raise RuntimeError(f"No result for sections: {unwritten}")
        return Report(
            title=title,
            sections=[state["sections"][s.id] for s in sections],
            review_log=[state["reviews"][s.id] for s in sections],
            usage=add_usage(client.usage.snapshot(), reviewer.client.usage.snapshot()),
        )
