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
# optional: model="...", max_workers=4, chat_options={"reasoning_effort": "low"},
# drop_unverified=False (raise instead of dropping a fact whose quote cannot be verified)
knowledge = curator.curate(
    sources,
    sections,
    instructions="Site notes are primary sources. Customer documents are secondary.",
    source_precedence=["primary", "secondary"],  # decides conflicts; optional
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
- `instructions` are the report-level rules: scope, style and how each kind of source is
  worded. They do not decide conflicts.
- `source_precedence` lists source classes, highest first. It decides conflicts in code
  (see [Conflicts](#conflicts)); without it every conflict is unresolved.
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
      "unit_ids": ["structures-04", "structures-07"],
      "preferred_unit_ids": [],
      "resolved_by": null
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
- A conflict lists the units of both sides. Its `status` is set in code, not by the
  model (see [Conflicts](#conflicts)).

## Conflicts

The model records that sources disagree and describes each side; it does not decide which
side the report follows. The curator decides that in code from `source_precedence`:

- A conflict is `resolved` when every unit's `source_class` is in `source_precedence` and
  exactly one unit has the highest-ranked class among them, and that unit is not of `low`
  confidence. `preferred_unit_ids` names
  that unit and `resolved_by` its class; the writer follows it.
- It is `unresolved` when two or more units share the top class (they may disagree with
  each other), when the top unit has `low` confidence (its source is itself unsure), when
  the units share one class, when a class is not in `source_precedence`, or when there is
  no `source_precedence`. The writer gives both
  sides, marked `Unresolved:`, for a person to settle.
- A rule the classes cannot express, such as a newer document over an older one, is
  settled by a person: set `status`, `preferred_unit_ids` and `resolved_by` in the
  knowledge file before the report is written (see [Editing knowledge files](#editing-knowledge-files)).

The model no longer marks a conflict resolved, and a description cannot pick the side.
The code decides from the model's own work, though: which source each unit cites and which
units form a conflict. A source can still steer those (a unit citing the wrong file with a
generic quote, or a conflict left out), so a person checks the resolved conflicts and the
side each follows at the evidence checkpoint before the report is written.

## Sources stay data

Each source reaches the model in its own `<source_material>` block with a random id for
each call ([`gaik.software_components.source_material`](../source_material.py)), labelled
with the file name that `source.file` cites. A file name that is not a clean one-line
label (quotes, angle brackets, runs of spaces, over 200 characters) is labelled with its
source id instead, and the citation is turned back into the file name. The rules stay in
the system message; the source list (one JSON object per source with its label, class
and type, so a file name cannot set a class), the report instructions and the section
stay outside the blocks. A sentence in a source cannot close
its block, and the curator is told that a source does not decide what is extracted or
what is missing; conflicts are decided in code (see [Conflicts](#conflicts)).

This lowers the chance that one source steers the others; it does not remove it. The
units, `missing` and `conflicts` are model output: the quote check verifies every unit,
while `missing` and the conflicts are only reported, in the knowledge files a person can
check and edit before the report is written (see below).

## Quote check

A unit fails when its `source.file` is not one of the sources, when its `quote` does
not occur verbatim in that source's text (only whitespace may differ, `quote_in_text`),
or when its `summary` states a number that neither the quote nor the `time_qualifier`
(where the cited source has that number too) gives, such as an age computed from a year. Numbers are compared by their digits, so
"1 200" supports "1200" and also "1" and "200", and a digit glued to letters (the 2 of
m2) is not a figure. A grouped number keeps one thousands separator: "1,250.500" is 1250
and 500, not 1250500. A date the summary writes with numbers (14.3.2026, 14.3. or
2026-03-14) is also supported by the same date with its month as a word ("14 March
2026", "the 14th of March", "March 14", "14. maaliskuuta", "14. päivänä maaliskuuta"),
and a month and a year (3/2026) by the same month and year ("maaliskuussa 2026", "March
2026"); a year counts only when that date has the same year. The month's number supports
nothing else, so "14 March" does not support "3 floors". Month names count in any case,
but "may" and "mar" only after a day or before a year, since they are also words. A
number the summary
writes in words is not checked, and the check does not
confirm that the summary's wording matches the quote. It is a sanity check, not a
verification of figures: digits are compared as a set, so their order (1,5 and 5,1) and
a sign (-1,5) are not checked.
If any unit of a section fails, the whole section is requested again once, with the
failing units as feedback. If the second answer still fails, the failing units are
dropped and the rest of the section is kept, so one bad quote does not stop the run:

```python
knowledge = curator.curate(sources, sections)
for unit in knowledge.dropped:  # DroppedUnit: section_id, topic, summary, quote, file, reason
    print(unit.section_id, unit.reason, unit.quote)
```

- The remaining units are renumbered without gaps. A conflict keeps only its remaining
  units and is removed if fewer than two are left.
- A required item that only a dropped unit covered is not added to `missing`; the writer
  still marks an item the material does not cover.
- `progress_callback` gets a "Dropped N fact(s) of ..." line, and each drop is logged as a
  warning. `knowledge.dropped` is not saved, so it is empty after `KnowledgeBase.load`.
- `KnowledgeCurator(config, drop_unverified=False)` restores the strict behaviour:
  `curate()` raises `ValueError` naming the section and the failing units.

A conflict that refers to a unit that does not exist is part of the same retry, with the
bad positions as feedback. If it still does after the retry, the bad positions are left
out and the conflict is removed if fewer than two units are left; the change is logged as
a warning and reported to `progress_callback`. With `drop_unverified=False`, `curate()`
raises `ValueError` instead.

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
