"""Report Synthesizer Example

Writes a short condition report from a hand-written knowledge base: two technical
sections, each with a missing item and an unresolved conflict, and a summary written from
their reviewed texts. Prints the report and the review log and saves them.
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Allow running without `pip install -e .`
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.knowledge_curator import (  # noqa: E402
    Conflict,
    FactUnit,
    KnowledgeBase,
    SectionKnowledge,
    SectionSpec,
    SourceRef,
)
from gaik.software_components.report_synthesizer import (  # noqa: E402
    ReportSynthesizer,
    get_llm_config,
)

OUTPUT_DIR = Path(__file__).parent / "output"

SECTIONS = [
    SectionSpec(
        id="summary",
        title="Summary",
        instructions="Overall condition in 3-5 sentences and the most urgent action.",
        depends_on=["structures", "building_services"],
    ),
    SectionSpec(
        id="structures",
        title="Structures and roof",
        required_items=["roof covering", "attic and roof underlay", "external walls"],
    ),
    SectionSpec(
        id="building_services",
        title="Building services",
        required_items=["ventilation system and its age", "latest sewer camera inspection"],
    ),
]

INSTRUCTIONS = """Source hierarchy
- Site recordings are primary sources. Customer documents are secondary sources.
- Narrate observations directly ("It was observed that ...") and cite them as
  [field observation, date].
- Attribute document content ("According to the 1998 renovation report ...") and
  cite the document.
- When an uncertain observation contradicts a document, write "Unresolved: ..."
  and give both views.

Missing data
- If a required item is not covered by any source, write (missing: item).

Style
- English, third person, past tense for observations. Short paragraphs."""


def unit(uid, topic, when, summary, quote, file, locator, source_class, confidence="high"):
    """One fact unit, as KnowledgeCurator would write it."""
    return FactUnit(
        id=uid,
        topic=topic,
        time_qualifier=when,
        summary=summary,
        quote=quote,
        source=SourceRef(file=file, locator=locator),
        source_class=source_class,
        confidence=confidence,
    )


KNOWLEDGE = KnowledgeBase(
    sections=[
        SectionKnowledge(
            section_id="structures",
            units=[
                unit(
                    "structures-01",
                    "roof covering",
                    "site visit, 2026-03-14",
                    "The bitumen felt roof covering had cracks near the chimney.",
                    "the felt is cracked next to the chimney",
                    "site_recording.mp3",
                    None,
                    "primary",
                ),
                unit(
                    "structures-02",
                    "attic underlay",
                    "2012 roof renovation",
                    "The attic underlay was renewed in the 2012 roof renovation.",
                    "Roof underlay renewed in the attic.",
                    "roof_renovation_2012.pdf",
                    "page 2",
                    "secondary",
                ),
                unit(
                    "structures-03",
                    "attic underlay",
                    "site visit, 2026-03-14",
                    "The inspector was not sure whether the attic underlay was original.",
                    "not sure if the underlay is the original one",
                    "site_recording.mp3",
                    None,
                    "primary",
                    confidence="low",
                ),
            ],
            missing=["external walls"],
            conflicts=[
                Conflict(
                    topic="attic underlay",
                    description="The 2012 report says the underlay was renewed; the "
                    "inspector was unsure whether it is original.",
                    status="unresolved",
                    unit_ids=["structures-02", "structures-03"],
                )
            ],
        ),
        SectionKnowledge(
            section_id="building_services",
            units=[
                unit(
                    "building_services-01",
                    "ventilation system age",
                    "1998",
                    "Mechanical ventilation was installed in the 1998 renovation with a "
                    "25-year design life.",
                    "Mechanical ventilation system installed during 1998 renovation. "
                    "Design life 25 years.",
                    "renovation_report_1998.pdf",
                    "page 3",
                    "secondary",
                ),
                unit(
                    "building_services-02",
                    "ventilation unit condition",
                    "site visit, 2026-03-14",
                    "The supply-air unit vibrated and had surface rust on the housing.",
                    "it vibrates quite a lot and the housing is rusty",
                    "site_recording.mp3",
                    None,
                    "primary",
                    confidence="medium",
                ),
                unit(
                    "building_services-03",
                    "ventilation system age",
                    "2019",
                    "The owner's maintenance log says the ventilation unit was replaced in 2019.",
                    "Ventilation unit replaced",
                    "maintenance_log.xlsx",
                    "sheet Log, row 7",
                    "secondary",
                ),
            ],
            missing=["latest sewer camera inspection"],
            conflicts=[
                Conflict(
                    topic="ventilation system age",
                    description="The 1998 report dates the system to 1998; the maintenance "
                    "log says the unit was replaced in 2019. The log does not say whether "
                    "the whole system or only the unit was replaced.",
                    status="unresolved",
                    unit_ids=["building_services-01", "building_services-03"],
                )
            ],
        ),
    ]
)


def synthesize_example() -> None:
    """Write the report, print it with the review log and save it."""
    synthesizer = ReportSynthesizer(get_llm_config())
    report = synthesizer.synthesize(
        KNOWLEDGE,
        SECTIONS,
        title="Condition assessment, Tammikatu 4",
        instructions=INSTRUCTIONS,
        progress_callback=print,
    )

    print(f"\n{report.markdown}")
    for entry in report.review_log:
        print(f"=== review of {entry.section_id}")
        for edit in entry.applied:
            print(f"  applied {edit.search!r} -> {edit.replace!r}: {edit.reason}")
        for edit in entry.unresolved:
            print(f"  unresolved {edit.search!r} -> {edit.replace!r}: {edit.reason}")
    print(f"Writer token usage: {report.usage}")

    # report.docx needs the Pandoc binary; use docx=False without it.
    paths = report.save(OUTPUT_DIR)
    print(f"\nSaved: {[str(p) for p in paths.values()]}")


if __name__ == "__main__":
    synthesize_example()
