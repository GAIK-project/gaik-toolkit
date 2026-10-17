# The report spec

One JSON file defines the report and its sources. Load it with `ReportSpec.load()`, which
resolves source paths against the spec's own folder; never change the working directory to
make a path resolve. The schema is closed: an unknown key, including any helper metadata or a
credential such as `api_key`, is rejected. Keep approvals, notes and diagnostics outside it.

```python
from gaik.software_modules.report_writer import ReportSpec

spec = ReportSpec.load("report-runs/koivukuja/report_spec.json")
```

## Example

```json
{
  "title": "Condition assessment, Koivukuja 5",
  "description": "Pre-sale condition assessment of a detached house.",
  "language": "English",
  "sections": [
    {
      "id": "building_services",
      "title": "Building services",
      "instructions": "Heating, ventilation, water and sewer, as observed on site.",
      "required_items": ["ventilation system and its age", "latest sewer camera inspection"]
    },
    {
      "id": "summary",
      "title": "Summary",
      "instructions": "The main findings in one paragraph.",
      "depends_on": ["building_services"]
    }
  ],
  "instructions": "Site recordings are primary sources and outrank the documents. Cite each fact by its source file, and add the page, sheet or heading only when the source has one; recordings and photos have none, so cite them by file name alone. Use the (missing: ...) marker only for the items listed as missing and for a section's required items, never for other information the sources do not give.",
  "sources": {
    "primary": ["inputs/site_visit.m4a", "inputs/inspection_notes.txt"],
    "secondary": ["inputs/renovation_report_1998.pdf", "inputs/maintenance_log.xlsx"]
  },
  "sample_report": "templates/earlier_report.docx",
  "settings": {"docx": true}
}
```

## Keys

| Key | Meaning |
|---|---|
| `title` | The report title, the top heading of the report |
| `description` | For people only. **Not sent to any model**: purpose, audience and tone that must shape the text go into `instructions` |
| `language` | The language the report is written in (default English); not the transcription language |
| `sections` | The report structure, in report order (below). Proposed with every other key by `run_report.py propose-spec`, agreed with the user after normalization and written by `apply-spec` |
| `instructions` | Rules for every section: source hierarchy, scope, tone, citation style |
| `sources` | Files grouped as `primary` and/or `secondary`; at least one file; every file name unique |
| `sample_report` | Optional report whose structure, length and tone the new one follows; never its facts |
| `models` | Optional model or deployment name per step: `vision`, `transcription`, `curator`, `writer`, `reviewer`. A `null` curator, writer or reviewer takes `GAIK_REPORT_<STEP>_MODEL`, else the default for the provider (README, "Changing the provider and the models"), else the provider's configured model; the helper fills these in at run time and never rewrites the spec |
| `settings` | Optional; how the stages run (below) |

### Sections

| Key | Meaning |
|---|---|
| `id` | Letters, digits, `_` and `-` only, unique in the spec. `set-sections` makes it from the title |
| `title` | The heading, in the report's own words and language |
| `instructions` | What the section covers and how |
| `required_items` | Facts the section must cover. Each one no source covers becomes `(missing: <item>)`. Name a fact ("ventilation system and its age"), not a topic ("details"); vague items cannot be checked |
| `depends_on` | Makes the section *derived*: it has no facts of its own and is written from the reviewed text of these sections. Use it for summaries and recommendations that need no new evidence. At least one section must not be derived, and dependencies must not form a cycle |

### Proposed models

`propose-spec` names a model for every step, by the selected provider (`--provider`, else
`LLM_PROVIDER`, else `openai`). A `GAIK_REPORT_<STEP>_MODEL` variable overrides the curator,
writer or reviewer default. `null` leaves the step to the provider's configured model.

| Provider | vision | transcription | curator | writer | reviewer |
|---|---|---|---|---|---|
| `openai`, `azure` | null | `gpt-4o-transcribe` | `gpt-6-luna` | `gpt-6-luna` | `gpt-6.1-sol` |
| `anthropic`, `anthropic_foundry` | null | null (cannot transcribe) | `claude-sonnet-5` | `claude-sonnet-5` | `claude-sonnet-5-5` |
| `google`, `vertex` | null | null (cannot transcribe) | `gemini-3.6-flash` | `gemini-3.6-flash` | `gemini-3.8-flash` |
| others | null | null | null | null | null |

### Settings

`propose-spec` proposes `transcription_language` `en` and `strict_review` `true`; the other
settings start at the library defaults below. The user accepts or changes each one.

| Key | Default | Meaning |
|---|---|---|
| `transcription_language` | `auto` | Language of the recordings, e.g. `fi` |
| `curator_workers` | 4 | Sections curated in parallel |
| `review_attempts` | 5 | Most reviewer requests per section |
| `strict_review` | `false` | `true` fails synthesis when a reviewer edit cannot be applied. It does not mean every unsupported statement is found |
| `docx` | `true` | Word output. Needs Pandoc; set `false` for Markdown only |
| `citations` | `true` | Cite the source file and place of each fact. `false` removes visible provenance: tell the user |
| `curator`, `writer`, `reviewer` | unset | `reasoning_effort` and `temperature` for every call of that step. Set `reasoning_effort` only for models that support it; the skill passes none by default |

## Citations and gap markers

Put these sentences into every report's `instructions` unless the user wants otherwise. The
citation sentence goes in only when the user wants citations (`settings.citations` `true`, the
default; the agent asks at intake). With `citations: false` leave it out: gaik then strips
citations from the text anyway.

Citation sentence, only with citations:

> Cite each fact by its source file, and add the page, sheet or heading only when the source has one; recordings and photos have none, so cite them by file name alone.

Gap markers, always:

> Use the (missing: ...) marker only for the items listed as missing and for a section's required items, never for other information the sources do not give. Where the evidence is missing, do not invent anything: write only the marker and add no inferred or loosely related text for that item or section. When a section's only content is the missing marker, write nothing else in that section, even if loosely related facts exist.

An instruction that asks for a page for every fact makes the writer add a missing-page marker
after each fact from a recording or a photo, which have no pages. gaik's default, the file and
its locator where there is one, avoids that; the first sentence keeps that behaviour when the
user wants the citation style written out. Without the second sentence the writer may also mark
gaps nobody asked about, and the real gaps, the required items no source covers, get lost among
them. The marker's own rule says only to add it, so the writer still writes up any loosely related
fact the curator filed under the section; the added wording stops that.

## Source classes and priority

`sources` accepts only `primary` and `secondary`. The curator copies the class onto every fact,
and its prompt gives "a clear primary field observation over an older document" and "a newer
document over an older one" as examples of a hierarchy. So the class is not neutral, and file
type alone never decides it: a recording is not automatically primary.

**When the user states no priority**, put every source in `primary` and write this into
`instructions`:

> No source has automatic priority, by class or by date. Preserve unresolved contradictions
> concerning the same subject and applicable context; do not treat historical changes alone as
> contradictions.

The second sentence matters: two sources describing different dates or versions (an
inspection in 2019 and another in 2024) are not a conflict. Facts carry a `time_qualifier` for
that difference.

**When the user states a priority**, map it to the two classes and also write it into
`instructions` in words, because the curator decides conflicts from the instructions.

## Files the pipeline reads

| Kind | Types |
|---|---|
| Sources | PDF with a text layer, Word (.docx), Excel (.xlsx), CSV, text and Markdown, recordings (.mp3, .wav, .m4a, .ogg, .flac, .webm, .mp4, .mpeg, .mpga), images (.png, .jpg, .jpeg, .webp) |
| Sample report | Word (.docx), Markdown, text, or a PDF with a text layer: types that convert without a model call |
| Not read | PowerPoint, .doc, .xls, TIFF, scanned PDFs. Convert them first; never drop one silently. Preflight refuses a PDF with no text on any page, lists pages without text, and warns about pages with so little text that they may be scans (a short document such as a one-line receipt is fine) |

Recordings are transcribed with the provider of the whole run, so a run with recordings needs
an OpenAI or Azure OpenAI provider; a fact's locator from a recording is empty, since the
transcript has no per-sentence times. Images are described by the vision model, which must
accept images. Text inside a PDF or Word file is read; its figures are not.
