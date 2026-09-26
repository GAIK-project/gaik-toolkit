"""Knowledge Curator Example

Curates two short synthetic sources into section-bound fact units with verbatim quotes,
prints them and saves one knowledge file per section.
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Allow running without `pip install -e .`
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.knowledge_curator import (  # noqa: E402
    KnowledgeBase,
    KnowledgeCurator,
    SectionSpec,
    get_llm_config,
)
from gaik.software_components.source_normalizer.models import NormalizedSources  # noqa: E402

OUTPUT_DIR = Path(__file__).parent / "output" / "knowledge"

SITE_NOTES = (
    "14 March 2026, 11:20, technical room in the basement. The supply-air unit runs, but "
    "it vibrates unusually and there is surface rust on the housing. Heating is district "
    "heating; the substation looks tidy. The main distribution board is on the wall next "
    "to the door."
)

RENOVATION_REPORT = """[Page 1]
Renovation report 1998

Mechanical ventilation system installed during 1998 renovation. Design life 25 years.
The ventilation unit was commissioned and found in good condition.

[Page 2]
The main distribution board was replaced with a new board with automatic fuses.

| Item | Cost (FIM) |
|------|------------|
| Ventilation | 48 000 |
| Electrical work | 21 000 |
"""

SECTIONS = [
    SectionSpec(
        id="building_services",
        title="Building services",
        required_items=[
            "heating system",
            "ventilation system and its age",
            "latest sewer camera inspection",
        ],
    ),
    SectionSpec(
        id="electrical",
        title="Electrical systems",
        required_items=["main distribution board", "latest electrical inspection record"],
    ),
]

INSTRUCTIONS = """Source hierarchy
- Site notes are primary sources. Customer documents are secondary sources.
- When a clear observation contradicts a document, follow the observation.
- When two documents disagree on the same topic, follow the newer one.

Style
- English, third person."""


def build_sources() -> NormalizedSources:
    """Wrap the synthetic texts as one primary and one secondary source."""
    primary = NormalizedSources.from_texts({"site_notes.txt": SITE_NOTES}, source_class="primary")
    secondary = NormalizedSources.from_texts(
        {"renovation_report_1998.txt": RENOVATION_REPORT}, source_class="secondary"
    )
    return NormalizedSources(sources=primary.sources + secondary.sources)


def curate_example() -> None:
    """Curate both sections, print the knowledge, save it and re-check the quotes."""
    sources = build_sources()
    curator = KnowledgeCurator(get_llm_config())
    knowledge = curator.curate(
        sources, SECTIONS, instructions=INSTRUCTIONS, progress_callback=print
    )

    for section in knowledge.sections:
        print(f"\n=== {section.section_id}")
        for unit in section.units:
            print(f"{unit.id} [{unit.source_class}, {unit.confidence}] {unit.summary}")
            print(f'    "{unit.quote}" ({unit.source.file}, {unit.source.locator})')
        print(f"missing: {section.missing}")
        for conflict in section.conflicts:
            print(f"conflict ({conflict.status}) {conflict.unit_ids}: {conflict.description}")

    paths = knowledge.save(OUTPUT_DIR)
    print(f"\nSaved: {[str(p) for p in paths.values()]}")

    # The knowledge files can be edited by hand; reload them and re-check every quote.
    reloaded = KnowledgeBase.load(OUTPUT_DIR)
    print(f"Quotes not found in their sources: {reloaded.verify_quotes(sources)}")


if __name__ == "__main__":
    curate_example()
