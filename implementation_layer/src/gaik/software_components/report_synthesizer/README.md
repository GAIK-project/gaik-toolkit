# Report Synthesizer

Stage 3 of CURACT report writing. Writes a report section by section from curated
knowledge. Each technical section is written from its own knowledge file only, and
derived sections such as recommendations and a summary are written afterwards from the
reviewed texts of the sections they depend on. A reviewer model checks every draft
against the same material with exact search-and-replace edits, and a review log records
them.

## Installation

```bash
pip install "gaik[report-synthesizer]"
```

Installs LangGraph and `pypandoc`. DOCX export also needs the Pandoc binary
(https://pandoc.org/installing.html, or `winget install JohnMacFarlane.Pandoc`,
`brew install pandoc`, `apt install pandoc`). Works with any provider supported by
`get_llm_config` (Azure, OpenAI, Anthropic, Google and others).

---

## Quick Start

The knowledge usually comes from `KnowledgeCurator`, but it is plain data, so it can also
be written by hand:

```python
from gaik.software_components.knowledge_curator import (
    FactUnit,
    KnowledgeBase,
    SectionKnowledge,
    SectionSpec,
    SourceRef,
)
from gaik.software_components.report_synthesizer import ReportSynthesizer, get_llm_config

sections = [
    SectionSpec(
        id="summary",
        title="Summary",
        instructions="Overall condition in 3-5 sentences.",
        depends_on=["building_services"],
    ),
    SectionSpec(
        id="building_services",
        title="Building services",
        required_items=["ventilation system and its age", "latest sewer camera inspection"],
    ),
]
knowledge = KnowledgeBase(
    sections=[
        SectionKnowledge(
            section_id="building_services",
            units=[
                FactUnit(
                    id="building_services-01",
                    topic="ventilation system age",
                    time_qualifier="1998",
                    summary="Mechanical ventilation was installed in the 1998 renovation.",
                    quote="Mechanical ventilation system installed during 1998 renovation.",
                    source=SourceRef(file="renovation_report_1998.pdf", locator="page 3"),
                    source_class="secondary",
                    confidence="high",
                )
            ],
            missing=["latest sewer camera inspection"],
            conflicts=[],
        )
    ]
)

synthesizer = ReportSynthesizer(get_llm_config())
# optional: model="...", reviewer_model="...", strict_review=True, review_attempts=5,
#           writer_options={"reasoning_effort": "medium"}, reviewer_options={...}
report = synthesizer.synthesize(
    knowledge,
    sections,
    title="Condition assessment",
    instructions='Attribute document content: "According to the 1998 renovation report ...".',
    progress_callback=print,
)
print(report.markdown)
report.save("workspace/report")  # sections/, review_log.json, report.md, report.docx
```

- `model` is the writer model and `reviewer_model` the reviewer model; both default to
  the config's model. `writer_options` and `reviewer_options` go to every call of that
  step, and `review_attempts` is the reviewer's `max_attempts`.
- `knowledge` must hold exactly one entry for each non-derived section and nothing else.
- `instructions` are the report-wide rules: source hierarchy, missing data and citation
  style. They go to every writer and to every review.
- `sample_report` is optional Markdown text that the writers use as a format reference
  for structure, length and tone only. It contributes no content and never goes to the
  reviewer.
- `language` (default `"English"`) is the language the sections are written in.
- `progress_callback` receives `Writing <title>`, `Reviewing <title>` and
  `Finished <title>: N edits applied, M unresolved`, possibly from a worker thread. An
  exception it raises stops the run and propagates out of `synthesize()`.
- Before any LLM call, `synthesize()` raises `ValueError` for an empty title or section
  list, duplicate section ids, a dependency on an unknown section, a dependency cycle, a
  non-derived section without knowledge, or knowledge for a section that is not a
  non-derived section of the list.

## The chain

```python
from gaik.software_components.knowledge_curator import KnowledgeCurator
from gaik.software_components.source_normalizer import SourceNormalizer

config = get_llm_config()
sources = SourceNormalizer(config).normalize(
    {"primary": ["rec1.mp3"], "secondary": ["renovation_report_1998.pdf"]}
)
knowledge = KnowledgeCurator(config).curate(sources, sections, instructions=instructions)
report = ReportSynthesizer(config).synthesize(
    knowledge, sections, title="Condition assessment", instructions=instructions
)
```

`SourceNormalizer` → `KnowledgeCurator` → `ReportSynthesizer`, with the same `sections`
and `instructions` for the last two. The `ReportWriter` module runs all three with a
workspace folder between the stages.

---

## How sections are written

Each section is one LangGraph node: the writer drafts the section and the reviewer checks
the draft right away. Sections without dependencies start in parallel; a derived section
starts once all of its prerequisites are reviewed.

- **Technical section** (no `depends_on`): written from its own `SectionKnowledge` as
  JSON, never another section's, plus its title, instructions and required items and the
  report-wide inputs. Fact units carry `source.file`, `locator`, `source_class` and
  `time_qualifier`, so the writer can cite and attribute them as the instructions say.
- **Derived section** (with `depends_on`): written only from the reviewed texts of its
  prerequisites, each wrapped as `<section id=".." title="..">`, with no knowledge JSON.
  Derived sections can depend on other derived sections, e.g. `recommendations` on the
  technical sections and `summary` on everything.
- The writer uses only the facts in its material, writes `(missing: <item>)` for each
  `missing` entry and each required item the material does not cover, and states both
  sides of an unresolved conflict, marked `Unresolved:`.
- The section heading is added by the code; a heading the writer emits anyway is
  stripped. An empty writer answer raises `RuntimeError` naming the section.
- Sections are returned in the order of the `sections` list, not the writing order, so a
  summary can come first.

## Review and strict_review

Each draft goes to a `DraftReviewer` with `reviewer_model`. The `reference` is the
section's knowledge JSON, or the prerequisite texts for a derived section. The checks
replace the reviewer's defaults and cover unsupported claims; numbers, dates and
attributions; a `(missing: …)` marker for every uncovered required item; hierarchy
phrasing and citation format per the report instructions; and the section's
instructions. They tell the reviewer not to rewrite the style.

The reviewed text is the section text, and it is what derived sections are written from.
Each section's applied and unresolved edits go into `report.review_log`. With
`strict_review=True`, a section with unresolved edits raises `RuntimeError` naming the
section, which stops the run.

## Saving and editing

`report.save(directory)` writes `sections/NN_<id>.md`, `review_log.json`, `report.md`
and `report.docx` (`docx=False` skips the DOCX). The section files can be edited by
hand; load them back and save to rebuild the report files:

```python
from gaik.software_components.report_synthesizer import Report

Report.load("workspace/report").save("workspace/report")
```

## Known limitation

`report.usage` counts the writer and reviewer calls. It is not saved, so it is empty
after `Report.load`.

See the [example](../../../../examples/software_components/report_synthesizer/report_synthesizer_example.py)
for a complete script.

## License

MIT - see [LICENSE](../../../../../LICENSE)
