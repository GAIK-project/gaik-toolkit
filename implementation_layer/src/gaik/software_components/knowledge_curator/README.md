# Knowledge Curator

Stage 2 of CURACT report writing. For each section of a report template, an LLM reads the
normalized sources and extracts **fact units**: a short summary paired with the exact
words of the source it came from. It also lists the required items that no source covers
and the conflicts between sources. Every quote is checked against the source it cites.
The result is one editable JSON file per section, from which a writer drafts the report.

## Installation

```bash
pip install "gaik[knowledge-curator]"
```

Core dependencies only. Works with any provider supported by `get_llm_config`
(Azure, OpenAI, Anthropic, Google and others).

---

## Quick Start

```python
from gaik.software_components.knowledge_curator import (
    KnowledgeCurator,
    SectionSpec,
    get_llm_config,
)
from gaik.software_components.source_normalizer.models import NormalizedSources

sources = NormalizedSources.from_texts(
    {"site_notes.txt": "The supply-air unit vibrates and the housing is rusty."},
    source_class="primary",
)
sections = [
    SectionSpec(
        id="building_services",
        title="Building services",
        required_items=["ventilation system and its age", "latest sewer camera inspection"],
    ),
]

curator = KnowledgeCurator(get_llm_config())
# optional: model="...", max_workers=4, chat_options={"reasoning_effort": "low"}
knowledge = curator.curate(
    sources,
    sections,
    instructions="Site notes are primary sources. Customer documents are secondary.",
    progress_callback=print,
)
knowledge.save("workspace/knowledge")  # one <section_id>.json per section
```

- One structured-output call per section, run in parallel (`max_workers`).
  `chat_options` go to every call.
- `knowledge.usage` holds the token usage of the calls. It is not saved, so it is empty
  after `KnowledgeBase.load`.
- Derived sections, those with `depends_on`, are not curated: they are written later from
  the drafts they depend on. A template with no other section raises `ValueError`.
- `instructions` are the report-level rules: source hierarchy, scope and style. The
  curator uses the hierarchy to mark each conflict as resolved or unresolved.
- `progress_callback` is called when a section starts and ends, possibly from a worker
  thread. An exception it raises stops the run.

## The chain

```python
from gaik.software_components.report_synthesizer import ReportSynthesizer
from gaik.software_components.source_normalizer import SourceNormalizer

config = get_llm_config()
sources = SourceNormalizer(config).normalize(
    {"primary": ["rec1.mp3"], "secondary": ["renovation_report_1998.pdf"]}
)
knowledge = KnowledgeCurator(config).curate(sources, sections, instructions=instructions)
report = ReportSynthesizer(config).synthesize(knowledge, sections, title="Condition assessment")
```

`SourceNormalizer` → `KnowledgeCurator` → `ReportSynthesizer`. The `ReportWriter` module
runs all three with a workspace folder between the stages.

---

## Fact units

Each section's knowledge file looks like this:

```json
{
  "section_id": "building_services",
  "units": [
    {
      "id": "building_services-01",
      "topic": "ventilation system age",
      "time_qualifier": "1998",
      "summary": "Mechanical ventilation was installed in the 1998 renovation with a 25-year design life.",
      "quote": "Mechanical ventilation system installed during 1998 renovation. Design life 25 years.",
      "source": { "file": "renovation_report_1998.pdf", "locator": "page 3" },
      "source_class": "secondary",
      "confidence": "high"
    }
  ],
  "missing": ["latest sewer camera inspection"],
  "conflicts": [
    {
      "topic": "attic underlay",
      "description": "The 2012 report says the underlay was renewed; the inspector was unsure.",
      "status": "unresolved",
      "unit_ids": ["structures-04", "structures-07"]
    }
  ]
}
```

- `id` is `<section_id>-NN`; `source_class` is copied from the cited source.
- `locator` is `page N` from the `[Page N]` markers, `sheet <name>, row <n>` for
  spreadsheets, the nearest heading for other structured documents, and `null` for
  recordings and plain text.
- `missing` lists the section's required items that no source covers, phrased as the
  item. The writer turns each into a `(missing: …)` marker.
- A conflict is `resolved` when the source hierarchy in `instructions` decides it (a clear
  field observation over an older document, a newer document over an older one), and
  `unresolved` otherwise. Both sides are present as units.

## Quote check

A unit fails when its `source.file` is not one of the sources, or when its `quote` does
not occur verbatim in that source's text. Only whitespace may differ (`quote_in_text`).
If any unit of a section fails, the whole section is requested again once, with the
failing quotes as feedback. If the second answer still fails, `curate()` raises
`ValueError` naming the section and the quotes. A conflict that refers to a unit that
does not exist also raises `ValueError`.

## Editing knowledge files

The files are plain JSON, so an expert can correct, delete or add a unit before the report
is written. Reload them and re-check the quotes:

```python
from gaik.software_components.knowledge_curator import KnowledgeBase

knowledge = KnowledgeBase.load("workspace/knowledge")
assert knowledge.verify_quotes(sources) == []  # units whose quote is not in its source
```

`KnowledgeBase.load` validates every file against the models, so a malformed edit raises.

See the [example](../../../../examples/software_components/knowledge_curator/knowledge_curator_example.py)
for a complete script.

## License

MIT - see [LICENSE](../../../../../LICENSE)
