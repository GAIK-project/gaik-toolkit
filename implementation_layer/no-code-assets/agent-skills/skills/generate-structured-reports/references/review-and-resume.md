# Review, corrections and resuming

## The run folder

```text
report-runs/<name>/
  report_spec.json
  workspace/
    normalized/          <source-id>.md per source, and sources.json      normalize
    sample_report.md     only when the spec has a sample report            normalize, update-sample
    knowledge/           <section-id>.json per evidence section            curate
    report/              sections/NN_<id>.md, review_log.json,
                         report.md, report.docx                            synthesize, rebuild
    diagnostics/         run_record.json, normalization.json,
                         curation.json, synthesis.json                     the helper
```

Never put an input in the workspace's stage folders (`normalized/`, `knowledge/`,
`report/`, `diagnostics/`) or at `workspace/sample_report.md`: the stages delete or overwrite
them. Every command that writes refuses a source, sample report or spec found there, and a
stage folder that is a link or junction to somewhere else: the stage would delete what it
points to.

Diagnostics stay out of `workspace/knowledge/`: `KnowledgeBase.load()` reads every JSON file
in that folder as a section's knowledge. The workspace holds the user's content; it never goes
into the plugin, fixtures or a repository.

`normalize`, `curate` and `synthesize` each replace their own folder. The helper refuses unless
given `--replace`: before using it in an existing workspace, say which folder will be replaced,
and use it only when the user's request covers that.

## What the diagnostics hold

| File | Holds | Why the helper keeps it |
|---|---|---|
| `normalization.json` | Each source's converter, class and text length; usage of transcription and vision; every `update-sample` | Usage is not saved by gaik |
| `curation.json` | Per section: fact count, missing items, resolved and unresolved conflicts; the **dropped** facts and why; usage | `dropped` and usage are lost once the knowledge is saved |
| `synthesis.json` | Usage; `(missing: …)` count; applied and unresolved reviewer edits; the Word export as `ok`, `off` or `failed` | Usage is lost if export fails inside synthesis |
| `run_record.json` | What each stage was built from (below) | To tell a current report from a stale one |

Report only supportable costs: token counts, and audio seconds for duration-billed
transcription. Do not price an unknown model.

## The evidence checkpoint

After `curate`, summarize for the user, per section: the required items no source covers
(`missing`), the conflicts left `unresolved`, and the dropped facts. Ask whether to proceed
with these marked in the report, or to correct the evidence first. With nothing material open
and the go-ahead already given, proceed without a long confirmation.

### Correcting the evidence

A section's knowledge file looks like this:

```json
{
  "section_id": "building_services",
  "units": [
    {
      "id": "building_services-01",
      "topic": "ventilation system age",
      "time_qualifier": "1998",
      "summary": "Mechanical ventilation was installed in the 1998 renovation.",
      "quote": "Mechanical ventilation system installed during 1998 renovation.",
      "source": {"file": "renovation_report_1998.pdf", "locator": "page 3"},
      "source_class": "secondary",
      "confidence": "high"
    }
  ],
  "missing": ["latest sewer camera inspection"],
  "conflicts": []
}
```

- To fix a fact, edit its `summary`, or delete the unit. A `quote` must stay a verbatim passage
  of the cited source.
- To resolve a conflict, set its `status` to `resolved` and say why in `description`, or delete
  one of its units.
- A new fact the user supplies goes into a **new source file** (for example
  `inputs/clarifications_by_user.txt`) added to the spec; then normalize and curate again. Do not
  type it into a knowledge file: it would have no source to verify.
- A correction to the source text itself goes into `workspace/normalized/<source-id>.md`, then
  curate again. Record it as a documented correction, not as a verification of the original.

Then run:

```bash
python <skill>/scripts/run_report.py validate-knowledge --spec SPEC --workspace WS
```

It loads the files through gaik's models and adds what gaik does not check: every quote is found
in its source (`KnowledgeBase.verify_quotes`, whitespace may differ), unit ids are unique within
each section (the models allow duplicates, which make conflict references ambiguous), each
conflict refers to units that exist, and each unit's `source_class` matches its source.
`synthesize` runs the same checks and stops on a failure. A passing check proves that the
quotes are present, not that a summary reads its quote correctly or that the source is true.

## Word export

The helper writes the report with Word output switched off, in an in-memory copy of the spec,
and exports afterwards through `rebuild`. Inside one call, a failed conversion would lose the
returned report with its usage, and an earlier run's `report.docx` would be left beside the new
Markdown. Split, a failed export only records `failed` with the reason; `report/report.md` stands and
no old Word file remains. To recover: install Pandoc and run `rebuild`, or set `settings.docx`
to `false`. Never synthesize again to get the Word file: it costs a full run.

## The sample report

`synthesize` reads only `workspace/sample_report.md`. To use a new or changed sample, update the
spec and run:

```bash
python <skill>/scripts/run_report.py update-sample --spec SPEC --workspace WS
```

It builds the normalizer exactly as `ReportWriter.normalize()` does (the spec's vision and
transcription models and transcription language), accepts only types that convert without a
model call (Word, Markdown, text, a PDF with a text layer), and replaces the file only after the
conversion succeeded. When the spec has no sample report any more, it deletes the file, as
`normalize` would. Normalizing again for a sample change would transcribe every recording and
describe every image again.

## The run record

`diagnostics/run_record.json` holds one entry per stage, written when the stage completes:

- a run id and the time;
- hashes of what the stage read: for `normalize`, each source file and the spec fields that
  affect conversion; for `curate`, the sections, instructions and curator settings; for
  `synthesize`, the remaining fields that affect writing;
- the upstream run it consumed, and, for `synthesize`, the sample conversion it used (the sample
  file's hash is recorded when it is converted);
- the provider and the effective model names of the stage; never keys, endpoints or headers;
- warnings inherited from upstream, and the installed gaik version.

The report is **current** only when every link holds: `synthesize` used the latest `curate`,
`curate` the latest `normalize`, the sample file still matches its conversion, and each stage's
inputs, provider and models still match. Every command reports what no longer holds. A later
stage never clears a warning: if `synthesize` runs on knowledge built from a source that has
since changed, the report stays not current until `normalize`, `curate` and `synthesize` have
run again. Version 1 warns; it does not block.

The record does not hash the stages' own outputs, so it does not notice hand edits to
`normalized/`, `knowledge/` or `report/sections/`. Those edits are legitimate and are checked by
`validate-knowledge` and by the stages that follow.

## What to rerun after a change

| Change | Rerun |
|---|---|
| A source file, or `sources`, `models.vision`, `models.transcription`, `transcription_language` | normalize, curate, synthesize |
| A normalized text, edited by hand | curate, synthesize |
| The structure or the report instructions (apply them with `apply-spec`, or the sections alone with `set-sections`) | curate, synthesize (keep the normalized texts) |
| Curated facts or conflicts, edited by hand | validate-knowledge, synthesize |
| The writer or reviewer model, or a writing setting | synthesize |
| The provider, or a model chosen by the environment | the stages that used it |
| The sample report | update-sample, synthesize |
| The wording of report sections | rebuild |
| Word output only | rebuild |

## Editing the report by hand

Edit `workspace/report/sections/NN_<id>.md`, keeping its first line `## <section title>`, then:

```bash
python <skill>/scripts/run_report.py rebuild --spec SPEC --workspace WS
```

`rebuild` makes no model call and reviews nothing: `review_log.json` describes the generated
text, not the edits. A summary that depends on an edited section is not updated; tell the user,
and offer to edit it too or to synthesize again.
