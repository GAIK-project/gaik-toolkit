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
from gaik.software_components.source_material import (
    SourceMaterial,
    with_source_material_instruction,
)

from .models import Report, ReportSection, ReviewEntry
from .prompts import build_review_checks, build_writer_prompt, writer_system_prompt


def _merge(left: dict, right: dict) -> dict:
    """Reducer for the dicts written by parallel section nodes."""
    return {**left, **right}


class _State(TypedDict):
    sections: Annotated[dict[str, ReportSection], _merge]
    reviews: Annotated[dict[str, ReviewEntry], _merge]


def _heading_words(text: str) -> str:
    """A heading's words for comparing: no numbering or punctuation, lower case."""
    text = re.sub(r"^\d+([.)]\d*)*[.)]?\s+", "", text.strip())
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def _without_echoed_title(draft: str, title: str) -> str:
    """``draft`` without a first line that is a heading repeating the section ``title``.

    The writer is told to leave the heading out; one it echoes anyway goes, also
    numbered. Any other first heading, such as the ``### Roof`` of a section that
    mirrors a sample report's subsections, is the section's own and stays.
    """
    first, _, rest = draft.partition("\n")
    match = re.fullmatch(r"#{1,6}[ \t]+(.*?)[ \t#]*", first.strip())
    if match and _heading_words(match.group(1)) == _heading_words(title):
        return rest.strip()
    return draft


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
        strict_review: bool = True,
        review_attempts: int = 5,
        writer_options: dict | None = None,
        reviewer_options: dict | None = None,
        citations: bool = True,
    ):
        """
        Args:
            config: LLM config from `get_llm_config()`.
            model: Optional writer model override. Defaults to the config's model.
            reviewer_model: Optional reviewer model override. Defaults to the config's model.
            strict_review: Raise when a reviewer edit cannot be applied (the
                default), so a report is never returned as reviewed with a
                correction left out. ``False`` logs it in the review log instead.
            review_attempts: Most reviewer requests per section, the first one included.
            writer_options: Extra options for every writer call, such as
                `reasoning_effort` or `temperature`.
            reviewer_options: The same for every reviewer call.
            citations: Cite the source file and locator of each fact. With `False` the
                writers and the reviewer leave citations out, even if `instructions` ask
                for them.
        """
        self.config = config
        self.model = model
        self.reviewer_model = reviewer_model
        self.strict_review = strict_review
        self.review_attempts = review_attempts
        self.writer_options = writer_options or {}
        self.reviewer_options = reviewer_options or {}
        self.citations = citations

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
            instructions: Report-level rules: wording per kind of source, missing data,
                citation style. They go to every writer and to the reviewer checks.
                Which side of a conflict a section follows comes from the knowledge
                (the curator's ``source_precedence``), not from these rules.
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
                material: str | dict[str, str]
                if section.derived:
                    # Each reviewed prerequisite goes in its own block, labelled with its
                    # id and title.
                    material = {
                        f"section {d}: {titles[d]}": state["sections"][d].text
                        for d in section.depends_on
                    }
                else:
                    material = knowledge.get(section.id).model_dump_json(indent=2)
                notify(f"Writing {section.title}")
                blocks = SourceMaterial()
                prompt = build_writer_prompt(
                    section,
                    material,
                    title=title,
                    language=language,
                    instructions=instructions,
                    sample_report=sample_report,
                    blocks=blocks,
                )
                response = client.chat(
                    [
                        {
                            "role": "system",
                            "content": with_source_material_instruction(
                                writer_system_prompt(self.citations)
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    **self.writer_options,
                )
                draft = _without_echoed_title(
                    blocks.strip_echo(response.text).strip(), section.title
                )
                if not draft:
                    raise RuntimeError(
                        f"Section {section.id!r}: the writer returned an empty answer"
                    )
                notify(f"Reviewing {section.title}")
                result = reviewer.review(
                    draft,
                    reference=material,
                    instructions=build_review_checks(section, instructions, self.citations),
                )
                if not result.text.strip():
                    raise RuntimeError(f"Section {section.id!r} is empty after review")
                if self.strict_review and result.unresolved:
                    raise RuntimeError(
                        f"Section {section.id!r} ({section.title!r}): "
                        f"{len(result.unresolved)} reviewer edit(s) could not be applied "
                        "(strict_review=True). Run the report again, or pass "
                        "strict_review=False and read review_log for the unresolved edits."
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
