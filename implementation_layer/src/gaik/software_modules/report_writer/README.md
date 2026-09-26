# Report Writer

Writes a fixed-template report, such as a building condition assessment, from mixed
source files with the CURACT pipeline. One JSON **report spec** defines the report and
its sources. Three stages run in turn, and each saves plain files to a **workspace**
folder that the next stage reads:

1. **Normalize**: every source file becomes a Markdown text with its provenance.
2. **Curate**: for each section, fact units with verbatim quotes, the required items no
   source covers, and the conflicts between sources.
3. **Synthesize**: each section is written from its own knowledge only, reviewed by a
   second model, and assembled into `report.md` and `report.docx`.

A person can inspect and edit the files of any stage and rerun only the later stages. A
single-call mode writes the whole report in one call from every source, as a baseline.

## Installation

```bash
pip install "gaik[report-writer]"
```

DOCX export also needs the [Pandoc](https://pandoc.org/installing.html) binary
(`winget install JohnMacFarlane.Pandoc`, `brew install pandoc`, `apt install pandoc`).
`synthesize`, `rebuild` and `run` save `report.docx` unless the spec sets
`settings.docx` to `false`, so without Pandoc they raise.

Works with any provider supported by `get_llm_config` (Azure, OpenAI, Anthropic, Google
and others). Recordings go to the `Transcriber`, which needs OpenAI or Azure OpenAI.

---

## Quick Start

```python
from gaik.software_modules.report_writer import ReportSpec, ReportWriter, get_llm_config

spec = ReportSpec.load("report_spec.json")
writer = ReportWriter(get_llm_config())

report = writer.run(spec, "workspace", progress_callback=print)
print(report.markdown)
print(report.usage)  # token usage of the writer and reviewer calls
```

`ReportWriter(config)`. The spec's `models` and `settings` set the model and the options
of each step.

| Method | Reads | Writes |
|--------|-------|--------|
| `normalize(spec, workspace)` | the source files | `normalized/`, `sample_report.md` |
| `curate(spec, workspace)` | `normalized/` | `knowledge/` |
| `synthesize(spec, workspace)` | `knowledge/`, `sample_report.md` | `report/` |
| `rebuild(spec, workspace)` | `report/sections/` | `report/report.md`, `report/report.docx` |
| `run(spec, workspace, mode="curact")` | the source files | all of the above |
| `run(spec, workspace, mode="single_call")` | the source files | `normalized/`, `single_call/` |

`workspace` is a `str` or `Path` and is created if needed. Every stage method takes an
optional `progress_callback` that receives status lines. A missing stage input raises
`FileNotFoundError`: run the earlier stage first.

Each stage result carries the usage of its model calls in `usage`, a dict of counts:
`NormalizedSources.usage` (transcription and vision, including the sample report),
`KnowledgeBase.usage` (curator) and `Report.usage` (writer and reviewer). Chat calls
report `prompt_tokens`, `completion_tokens` and, from most providers, `total_tokens`;
duration-billed transcription models such as `whisper-1` report `audio_seconds`.

---

## The report spec

```json
{
  "title": "Condition assessment, Koivukuja 5",
  "description": "Pre-sale condition assessment of a detached house.",
  "language": "English",
  "sections": [
    {
      "id": "building_services",
      "title": "Building services",
      "instructions": "Heating, ventilation, water and sewer.",
      "required_items": ["ventilation system and its age", "latest sewer camera inspection"]
    },
    {
      "id": "summary",
      "title": "Summary",
      "instructions": "The main findings in one paragraph.",
      "depends_on": ["building_services"]
    }
  ],
  "instructions": "Site recordings are primary sources and outrank the documents.",
  "sources": {
    "primary": ["inputs/rec3_building_services.mp3"],
    "secondary": ["inputs/renovation_report_1998.pdf", "inputs/maintenance_log.xlsx"]
  },
  "sample_report": "sample_report.docx",
  "models": {
    "vision": null,
    "transcription": "gpt-4o-transcribe",
    "curator": null,
    "writer": null,
    "reviewer": null
  },
  "settings": {
    "transcription_language": "auto",
    "curator_workers": 4,
    "review_attempts": 5,
    "strict_review": false,
    "docx": true,
    "curator": {"reasoning_effort": null, "temperature": null},
    "writer": {"reasoning_effort": "medium", "temperature": null},
    "reviewer": {"reasoning_effort": null, "temperature": null}
  }
}
```

| Key | Meaning |
|-----|---------|
| `title` | The report title, the `#` heading of `report.md` |
| `description` | What the report is for; for people only, not sent to a model |
| `language` | The language the report is written in (not the transcription language) |
| `sections` | The template, in report order: `id` (letters, digits, `_`, `-`), `title`, `instructions` |
| `required_items` | Items a section must cover; each one no source covers becomes `(missing: <item>)` |
| `depends_on` | Makes a section *derived*: it has no knowledge file and is written from the reviewed texts of these sections |
| `instructions` | Rules for every section: source hierarchy, citation style, tone |
| `sources` | Files grouped by class, `primary` and/or `secondary`; file names must be unique |
| `sample_report` | Optional report whose structure, length and tone the new report follows; never its facts |
| `models` | Optional model or deployment name per step; `null` uses the model of the config |
| `settings` | Optional; how the stages run. Every key has the default shown above |
| `settings.transcription_language` | Language of the recordings, e.g. `en` or `fi`, or `auto` |
| `settings.curator_workers` | Sections curated in parallel |
| `settings.review_attempts` | Most reviewer requests per section, the first one included |
| `settings.strict_review` | `true` fails `synthesize` when a reviewer edit cannot be applied, instead of logging it in `review_log.json` |
| `settings.docx` | `false` skips `report.docx` and deletes one of an earlier run |
| `settings.curator` / `writer` / `reviewer` | `reasoning_effort` and `temperature` for every call of that step; `null` leaves the option unset. Where a model does not take `temperature` with reasoning on, it is dropped; an invalid effort raises before the call |

Relative paths are resolved against the folder of the spec file. `ReportSpec.load(path)`
makes them absolute and `spec.save(path)` writes them back relative, with `/`, so a spec
folder can be moved or shared. The spec holds model names only, never credentials: an
unknown key such as `api_key` raises, and so does a spec with no sources, duplicate
section ids or a `depends_on` on an unknown section.

The supported source types are those of
[SourceNormalizer](../../software_components/source_normalizer/README.md): PDF, DOCX,
XLSX/CSV, TXT/MD, audio and images.

---

## Workspace

```
workspace/
  normalized/          NN_<stem>.md per source + sources.json        (normalize)
  sample_report.md     only when the spec has a sample_report        (normalize)
  knowledge/           <section_id>.json per non-derived section     (curate)
  report/              sections/NN_<id>.md, review_log.json,
                       report.md, report.docx                        (synthesize, rebuild)
  single_call/         the same layout as report/, empty review log  (run mode="single_call")
```

`normalize` and `curate` delete their folder before saving, so no file of an earlier run
survives. `normalize` converts every file before it writes anything, and it deletes a
stale `sample_report.md` when the spec has no sample report.

## Resume after editing

Every stage reads only files, so a person can correct a stage and rerun from there:

```python
# Correct a fact, delete a unit or resolve a conflict in workspace/knowledge/*.json,
# then write the report again. Normalize and curate are not rerun.
report = writer.synthesize(spec, "workspace")

# Edit the text of workspace/report/sections/*.md (keep the "## <title>" first line),
# then reassemble report.md and report.docx. No LLM call.
report = writer.rebuild(spec, "workspace")
```

A section file is named `NN_<id>.md`; the number sets its order in the report.
`rebuild` keeps `review_log.json` as it is.

## Single-call baseline

```python
baseline = writer.run(spec, "workspace", mode="single_call")
```

`single_call` runs `normalize` and then writes the whole report in **one** call of the
writer model (`models.writer`), with every normalized source in full as
`<source file=".." class="..">` blocks, the sections with their instructions and
required items, the report instructions and the sample report. There is no curation and
no review. The answer must be `# <title>` followed by exactly one `## <section title>`
per spec section in spec order; a missing, extra, reordered or duplicated heading, text
before the first section or an empty section raises `ValueError`. The report is saved to
`single_call/`, next to `report/`, to compare what curation and review add.

---

## Components used

| Stage | Component | README |
|-------|-----------|--------|
| Normalize | `SourceNormalizer` (parsers, `SpreadsheetParser`, `Transcriber`, `VisionParser`) | [source_normalizer](../../software_components/source_normalizer/README.md) |
| Curate | `KnowledgeCurator` | [knowledge_curator](../../software_components/knowledge_curator/README.md) |
| Synthesize | `ReportSynthesizer` | [report_synthesizer](../../software_components/report_synthesizer/README.md) |
| Review | `DraftReviewer`, used by `ReportSynthesizer` | [draft_reviewer](../../software_components/draft_reviewer/README.md) |
| Single call | `create_llm_client` of `gaik.software_components.llm` | |

The module imports everything it exports, so one import is enough:
`ReportWriter`, `ReportSpec`, `ModelSettings`, `RunSettings`, `StepOptions`,
`SectionSpec`, `NormalizedSources`, `KnowledgeBase`, `Report` and `get_llm_config`.

## Known limitations

- `usage` is not saved, so a stage result read back with `load`, and the report that
  `rebuild` returns, have empty usage.
- The single-call baseline sends every source in full; a large source set can exceed
  the context window of the writer model, and the call then fails.

## Example

See [examples/software_modules/report_writer](../../../../examples/software_modules/report_writer/).
