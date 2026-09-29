# Report Writer Examples

`report_writer_example.py` writes a report from a `report_spec.json` with the
[ReportWriter module](../../../src/gaik/software_modules/report_writer/README.md): the
CURACT stages normalize, curate and synthesize, each saved to a workspace you can
inspect and edit.

## The two examples

| `EXAMPLE` | Report | Sources |
|-----------|--------|---------|
| `house_condition_assessment` | Condition assessment of a fictional house, with planted conflicts, gaps and distractors | 3 site recordings (primary), 2 PDFs, a DOCX, an XLSX and a floor plan image (secondary), and a sample report of another house |
| `project_meeting` | Meeting report of a product roadmap review, the legacy multi-source report generator example ported to a spec | A recording and notes (primary), a PDF, an XLSX and a sketch (secondary), from `../multi_source_report_generator/sample_inputs/` |

See [house_condition_assessment/README.md](house_condition_assessment/README.md), with
the checks in `expected_behaviours.md`, and [project_meeting/README.md](project_meeting/README.md).

The house example's recordings are synthesized from `recording_scripts/` and are not in
`inputs/` until you run `house_condition_assessment/generate_dataset.py` (a paid
text-to-speech call). Until then `normalize` stops with a `FileNotFoundError` naming the
missing `.mp3`.

## How to run

```bash
pip install "gaik[report-writer]"   # or: uv sync --all-extras
```

Install [Pandoc](https://pandoc.org/installing.html) for `report.docx`, and set the LLM
credentials of `get_llm_config()` (Azure unless `LLM_PROVIDER` says otherwise) in the
environment or in `implementation_layer/.env`. The recordings go to the Transcriber,
which needs OpenAI or Azure OpenAI.

Set the two toggles at the top of the script, then run it:

```python
EXAMPLE = "house_condition_assessment"  # or "project_meeting"
MODE = "full"  # "full", "resume" or "single_call"
```

```bash
uv run python implementation_layer/examples/software_modules/report_writer/report_writer_example.py
```

| `MODE` | Runs | Writes |
|--------|------|--------|
| `full` | normalize, curate, synthesize | `normalized/`, `knowledge/`, `report/` |
| `resume` | synthesize only, from the existing `knowledge/` | `report/` |
| `single_call` | normalize, then the whole report in one call | `normalized/`, `single_call/` |

Every run makes paid LLM calls; `resume` skips the transcription and the curation.

## The workspace

The workspace is `output/<EXAMPLE>/`, next to the script:

```
output/<EXAMPLE>/
  normalized/        NN_<stem>.md per source + sources.json
  sample_report.md   the sample report as Markdown
  knowledge/         <section_id>.json per non-derived section
  report/            sections/NN_<id>.md, review_log.json, report.md, report.docx
  single_call/       the same layout as report/, with an empty review log
```

## What to inspect

- `normalized/`: the transcripts and parsed documents the curator quotes from.
- `knowledge/*.json`: each fact unit's summary, verbatim quote and source; the `missing`
  required items; the `conflicts` between sources and whether the source hierarchy
  resolved them.
- `report/review_log.json`: the reviewer's applied and unresolved edits per section.
- `report/report.md` against `single_call/report.md`: what curation and review add over
  one call with every source. For the house example, score both against
  `expected_behaviours.md`.

To see the knowledge files at work, delete or change a fact unit in
`output/<EXAMPLE>/knowledge/`, set `MODE = "resume"` and run again: only the report is
rewritten. To change the report text without any model call, edit
`report/sections/*.md` and call `ReportWriter(config).rebuild(spec, "output/<EXAMPLE>")`.
