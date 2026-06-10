# Multi-Source Report Generator

Generate a user-defined Markdown report from mixed source files.

You provide:

- input files or folders
- a report title
- section titles and instructions
- optional sample report for style/format

The module normalizes all input files into Markdown evidence, then writes a report using either:

- the default single-call workflow
- the optional agentic workflow, where each section is drafted, reviewed, repaired, and optionally polished

The module is generic. It does not classify documents, select files, add report sections, or use domain-specific templates. Every report section comes from the `sections` argument.

## Components Used

| Component | Used for |
|---|---|
| `PyMuPDFParser` | Fast local PDF text extraction, default for `parser_choice="auto"` |
| `VisionParser` | Vision-based PDF/image parsing |
| `MultimodalParser` | Multimodal PDF parsing with OpenAI, Claude, or Google |
| `DoclingParser` | Advanced PDF parsing with OCR/table support |
| `DocxParser` | Word document parsing |
| `Transcriber` | Audio/video transcription |
| `VisionExtractor` | Optional structured extraction from images |

## Installation

```bash
pip install "gaik[multi-source-report-generator]"
```

For the optional agentic workflow:

```bash
pip install "gaik[multi-source-report-generator-agentic]"
```

## Environment

Uses the same API configuration as other GAIK components.

For Azure OpenAI:

```text
AZURE_API_KEY
AZURE_ENDPOINT
AZURE_API_VERSION
AZURE_DEPLOYMENT
```

For standard OpenAI:

```text
OPENAI_API_KEY
```

## Constructor

```python
MultiSourceReportGenerator(*, api_config: dict | None = None, use_azure: bool = True)
```

| Option | Default | Purpose |
|---|---:|---|
| `api_config` | `None` | Shared LLM/API config. If `None`, the module builds one with `get_openai_config(use_azure=use_azure)`. |
| `use_azure` | `True` | Used only when `api_config=None`. `True` loads Azure OpenAI settings; `False` loads standard OpenAI settings. |

Provider/model choices normally belong in `writer_options`, `review_options`, parser options, or transcriber options, not in the constructor.

## Complete Usage

```python
from gaik.software_modules.multi_source_report_generator import MultiSourceReportGenerator

generator = MultiSourceReportGenerator(
    api_config=None,
    use_azure=True,
)

result = generator.run(
    # Inputs: files or folders. Folders are expanded recursively.
    input_paths=[
        "materials/specification.pdf",
        "materials/meeting_notes.docx",
        "materials/interview.mp3",
        "materials/photo_1.jpg",
        "materials/table.xlsx",
        "materials/notes/",
    ],

    # User-defined report structure.
    report_title="Project Assessment Report",
    report_description=(
        "Assess the current project state, summarize the evidence, "
        "and identify practical next steps for the client."
    ),
    sections=[
        {
            "title": "Background",
            "instructions": "Summarize the project context.",
            "required": True,
        },
        {
            "title": "Findings",
            "instructions": "Describe key findings from the evidence.",
        },
        {
            "title": "Recommendations",
            "instructions": "Give practical recommendations based only on the evidence.",
        },
    ],
    report_language="English",

    # Optional sample report. Supported: .txt, .md, .markdown, .pdf, .docx.
    sample_report_path="templates/previous_report.md",

    # Output files. If None, the result is returned in memory only.
    output_dir="output/report",
    include_evidence_index=True,
    include_source_references=True,

    # Evidence size control.
    max_evidence_chars=200_000,
    section_context_mode="all_evidence",  # reserved; current behavior always uses all evidence

    # PDF parser selection.
    parser_choice="auto",  # auto, pymupdf, vision, multimodal, docling
    parser_options={
        "ctor": {},
        # "openai_config": custom_config,
    },

    # Audio/video transcription options.
    transcriber_options={
        "ctor": {
            "compress_audio": True,
            "output_dir": "output/transcripts",
        },
        "call": {},
    },

    # Image handling.
    image_options={
        "mode": "parse",  # parse or structured
        # "user_requirements": "Extract all visible measurements.",
        # "ctor": {},
        # "openai_config": custom_config,
    },

    # Main report writer LLM options.
    writer_options={
        "model": "gpt-5.4",
        "temperature": 0,
        "reasoning_effort": "medium",
    },

    # Optional agentic workflow.
    agentic=False,
    review_options=None,
    polish=False,
    strict_review=False,
    curate_evidence=False,
    verbose=False,
    progress_callback=None,
)

print(result.markdown)
print(result.markdown_path)
print(result.usage)
for section in result.sections:
    print(section.title, section.revision_warnings)
```

## `run(...)` Options

| Option | Default | Purpose |
|---|---:|---|
| `input_paths` | required | Files or folders. Folders are expanded recursively and unsupported extensions are ignored. |
| `sections` | required | List of `ReportSectionSpec` or dicts with `title`, `instructions`, and optional `required`. |
| `report_title` | `"Generated Report"` | H1 title of the assembled report. |
| `report_description` | `None` | Optional overall purpose/context for the report. Used by the writer, and in agentic mode also by curation, review, and polish prompts. |
| `report_language` | `None` | Optional language instruction, for example `"Finnish"` or `"English"`. |
| `sample_report_path` | `None` | Optional sample report used only as a style/format reference. |
| `output_dir` | `None` | If set, writes `report.md`, section files, evidence files, and metadata JSON. |
| `include_evidence_index` | `True` | Writes `evidence_index.json` when `output_dir` is set. |
| `include_source_references` | `True` | Asks the writer to reference source filenames where useful. |
| `max_evidence_chars` | `None` | Truncates the normalized evidence pack before report writing. |
| `section_context_mode` | `"all_evidence"` | Reserved for future retrieval/section-context modes. Current behavior uses all evidence. |
| `parser_choice` | `"auto"` | PDF parser choice: `auto`, `pymupdf`, `vision`, `multimodal`, or `docling`. |
| `parser_options` | `None` | Parser constructor/config options. Supports `{"ctor": {...}}` and `{"openai_config": ...}` for relevant parsers. |
| `transcriber_options` | `None` | Transcriber options: `{"ctor": {...}, "call": {...}}`. |
| `image_options` | `None` | Image handling options. `{"mode": "parse"}` uses `VisionParser`; `{"mode": "structured"}` uses `VisionExtractor`. |
| `writer_options` | `None` | LLM options for the report writer. `model` and `provider` select the client; remaining keys are forwarded to `client.chat(...)`. |
| `agentic` | `False` | If `False`, writes the whole report in one LLM call. If `True`, uses per-section agentic drafting and review. |
| `review_options` | `None` | Optional separate LLM options for the agentic reviewer. If `None`, reviewer reuses the writer client/config. |
| `polish` | `False` | Agentic only. Runs a final style/proofreading pass after mandatory review repair. |
| `strict_review` | `False` | Agentic only. If unresolved reviewer edits remain, raise before final report outputs are written. |
| `curate_evidence` | `False` | Agentic only. Creates one section-specific evidence brief before drafting each section. |
| `verbose` | `False` | Agentic only. Prints workflow progress events. |
| `progress_callback` | `None` | Agentic only. Callable receiving progress strings. Overrides default printing behavior. |

## Supported Input Types

| Type | Extensions | Processing |
|---|---|---|
| Text | `.txt` | Read directly |
| Markdown | `.md`, `.markdown` | Read directly |
| CSV | `.csv` | Converted to Markdown table with Python stdlib `csv` |
| Excel | `.xlsx`, `.xls` | Converted to Markdown table with `openpyxl` |
| PDF | `.pdf` | Parsed by `parser_choice` |
| Word | `.docx` | Parsed by `DocxParser` |
| Audio | `.mp3`, `.wav`, `.m4a`, `.aac`, `.flac`, `.ogg` | Transcribed by `Transcriber` |
| Video | `.mp4`, `.mov`, `.mkv`, `.avi`, `.webm` | Transcribed by `Transcriber` |
| Images | `.png`, `.jpg`, `.jpeg`, `.webp`, `.tiff`, `.tif`, `.bmp`, `.gif` | Parsed by `VisionParser` or extracted by `VisionExtractor` |

## Workflow: Default Single-Call Mode

This is the default when `agentic=False`.

```text
input files
-> normalize every source to Markdown evidence
-> optionally normalize sample report
-> assemble one global evidence pack
-> one LLM call writes the complete report
-> split the generated report into section objects
-> optionally write output files
```

In this mode, the entire sample report is used as the format reference. This works because the model writes the whole report in one call.

Minimum report-writing API calls:

```text
1
```

Additional API calls may happen during parsing, transcription, image parsing, or sample-report parsing, depending on file types and parser choices.

## Workflow: Agentic Mode

Enable with:

```python
agentic=True
```

Install the extra first:

```bash
pip install "gaik[multi-source-report-generator-agentic]"
```

Agentic mode writes sections independently and in parallel:

```text
input files
-> normalize every source to Markdown evidence
-> optionally normalize and split sample report by headings
-> for each section:
     -> optional section-specific knowledge curation
     -> draft section
     -> mandatory reviewer / diff-editor repair
     -> optional style polish
-> assemble final report in the user's original section order
-> optionally write output files
```

### Agentic API Calls

For `N` sections:

| Mode | Minimum report-writing API calls |
|---|---:|
| No curation, no polish | `N draft + N reviewer` |
| With curation | `N curator + N draft + N reviewer` |
| With curation and polish | `N curator + N draft + N reviewer + N polish` |

Reviewer retries add more `chat_parsed(...)` calls when proposed edits cannot be applied.

### Agentic Review Behavior

In agentic mode, every section is reviewed before final assembly.

The reviewer:

- receives the same evidence used by the writer
- checks factual grounding against the evidence
- checks section instruction coverage
- checks sample-section format/style when a matching sample section exists
- proposes targeted search/replace corrections
- applies corrections locally with exact and fuzzy matching
- retries failed corrections up to the configured retry limit

Unresolved reviewer edits become `section.revision_warnings` by default.

With `strict_review=True`, unresolved reviewer edits raise before final report files such as `report.md` and `sections/` are written. Intermediate curation artifacts may already exist if `curate_evidence=True`.

### Agentic Curation

When `curate_evidence=False`, each section writer receives the full normalized evidence pack.

When `curate_evidence=True`, each section first gets a curator call:

```text
section title + section instructions + full evidence pack
-> section-specific curated brief
```

The section writer and reviewer then use the curated brief instead of the full evidence pack.

If `output_dir` is set, curated briefs are also saved to:

```text
output_dir/evidence/curated_sections/<section_slug>.md
```

If `output_dir=None`, curated briefs stay in memory only.

### Agentic Sample Report Handling

In single-call mode, the whole sample report is used as the format reference.

In agentic mode, the sample report is split into sections. For each requested section:

- first try exact heading match
- then try normalized heading match
- pass only the matched sample section to that section's writer and reviewer

The writer never copies sample facts or wording. The sample is only a format/style reference.

If no matching sample section is found:

- the section is written in a generic professional format
- a warning is added to that section's `revision_warnings`
- the reviewer does not penalize the section for not matching the sample

Main sample sections should normally use Markdown `##` headings. Lower-level headings such as `###` remain inside their parent section.

### Agentic Progress

Use `verbose=True` for CLI messages:

```text
Writing 3 section(s) in parallel: Background, Findings, Recommendations
[Findings] evidence loaded -> curation
[Findings] curated evidence -> drafting
[Findings] draft written (240 words) -> reviewer
[Findings] reviewer: 2 correction(s) proposed, 2 applied
[Findings] style polish applied
[Findings] done
Assembling report in requested order -> report.md
```

Or pass a callback:

```python
events = []
result = generator.run(
    input_paths=["materials/"],
    sections=[{"title": "Findings", "instructions": "Summarize findings."}],
    agentic=True,
    progress_callback=events.append,
)
```

## Option Dictionaries

### `parser_options`

```python
parser_options={
    "ctor": {
        # forwarded to parser constructor when supported
    },
    "openai_config": custom_config,  # used by VisionParser paths
}
```

### `transcriber_options`

```python
transcriber_options={
    "ctor": {
        "compress_audio": True,
        "output_dir": "output/transcripts",
    },
    "call": {
        # forwarded to Transcriber.transcribe(...)
    },
}
```

### `image_options`

General image parsing:

```python
image_options={"mode": "parse"}
```

Structured image extraction:

```python
image_options={
    "mode": "structured",
    "user_requirements": "Extract all measurements and labels.",
    "ctor": {},
}
```

### `writer_options`

```python
writer_options={
    "model": "gpt-5.4",
    "provider": "openai",       # optional; depends on config/client
    "temperature": 0,
    "reasoning_effort": "medium",
}
```

`model` and `provider` are consumed while creating the client. Other keys are forwarded to the LLM call.

### `review_options`

Agentic only:

```python
review_options={
    "model": "gpt-5.4",
    "temperature": 0,
}
```

If `review_options=None`, the reviewer and polish pass reuse the writer client/config.

## Output Files

When `output_dir` is set:

```text
output_dir/
    report.md
    evidence_index.json
    usage.json
    sections/
        01_background.md
        02_findings.md
    evidence/
        normalized_sources.md
        curated_sections/       # only agentic=True and curate_evidence=True
            background.md
            findings.md
```

The returned `ReportGenerationResult` contains:

| Field | Meaning |
|---|---|
| `title` | Report title |
| `evidence_items` | Normalized source records |
| `sections` | Generated section objects |
| `markdown` | Full assembled Markdown report |
| `markdown_path` | Path to `report.md`, or `None` |
| `usage` | Best-effort token usage from calls that expose usage |

Each `GeneratedSection` contains:

| Field | Meaning |
|---|---|
| `title` | Section title |
| `content_markdown` | Section body |
| `usage` | Best-effort per-section usage |
| `revision_warnings` | Non-fatal warnings from agentic generation |

Note: reviewer calls use `chat_parsed(...)`; provider clients may not expose usage for parsed calls. Agentic `usage` can therefore undercount total cost until parsed-call usage is surfaced by the shared LLM interface.

## Example

See:

```text
implementation_layer/examples/software_modules/multi_source_report_generator/report_generation_example.py
```
