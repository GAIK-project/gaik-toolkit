# Multi-Source Report Generator

Generate a **user-defined long-form report** from many mixed source files using an LLM.

You provide a set of files (PDF, Word, Excel/CSV, text, Markdown, audio/video, images) and a report structure (section titles + per-section instructions). The module normalizes every file into Markdown "evidence", then writes the **whole report in a single LLM call** (all sections at once, optionally following a sample report's format) and returns the Markdown plus a per-section breakdown.

It is **generic**: there is no document classification, relevance scoring, file selection, timeline construction, or domain-specific templates. Every input file is treated as potentially relevant evidence; the report structure is entirely yours.

## How it differs from other GAIK components

| Component | Output |
|---|---|
| `Extractor` | Structured JSON from text/documents |
| `VisionExtractor` | Document/image parsing + structured extraction in one multimodal call |
| **`MultiSourceReportGenerator`** | **Long-form Markdown reports** from many mixed source files, using user-defined sections |

## Installation

The core module needs the base GAIK dependencies plus the extras for whichever source types you use:

```bash
pip install "gaik[multi-source-report-generator]"
```

Markdown/text/CSV inputs work with the base install. PDF/DOCX parsing, transcription, image parsing, and `.xlsx` support pull in their respective optional dependencies (`gaik[parser]`, `gaik[transcriber]`, `openpyxl`).

## Quick start

```python
from gaik.software_modules.multi_source_report_generator import MultiSourceReportGenerator

gen = MultiSourceReportGenerator(use_azure=True)

result = gen.run(
    input_paths=[
        "materials/specification.pdf",
        "materials/meeting_notes.docx",
        "materials/interview.mp3",
        "materials/photo_1.jpg",
        "materials/table.xlsx",
    ],
    report_title="Project Assessment Report",
    sections=[
        {"title": "Background",        "instructions": "Summarize the project context."},
        {"title": "Findings",          "instructions": "Describe key findings from the evidence."},
        {"title": "Recommendations",   "instructions": "Give practical recommendations based only on the evidence."},
    ],
    output_dir="output/report",
    writer_options={"model": "gpt-5.4"},
)

print(result.markdown_path)   # output/report/report.md
print(result.markdown)        # the full report as a string
```

## Constructor

```python
MultiSourceReportGenerator(*, api_config: dict | None = None, use_azure: bool = True)
```

| Option | Purpose |
|---|---|
| `api_config` | Shared API config dict. If `None`, built via `get_openai_config(use_azure)`. |
| `use_azure` | Build a default Azure OpenAI config when `api_config` is not provided. |

Per-run settings (model, parser choice, output options, …) live in `run(...)`, not the constructor — consistent with other GAIK modules.

## `run(...)`

| Argument | Default | Purpose |
|---|---|---|
| `input_paths` | — | Files and/or folders. Folders are expanded recursively; only supported extensions are kept. |
| `sections` | — | List of `ReportSectionSpec` or dicts (`{"title", "instructions", "required"}`). |
| `report_title` | `"Generated Report"` | Title rendered at the top of the report. |
| `report_language` | `None` | e.g. `"Finnish"`, `"English"`. |
| `sample_report_path` | `None` | Optional example report (`.txt`, `.md`, `.pdf`, `.docx`). When given, the writer **strictly adheres to its tone, style, and structure** (layout, list styles, brevity, citation style). Its content is never copied — only its format. When omitted, the writer uses its own clean default format. The section *titles* always come from `sections`, not the sample. |
| `output_dir` | `None` | If set, writes `report.md`, `sections/`, `evidence/`, and index/usage JSON. |
| `include_evidence_index` | `True` | Write `evidence_index.json`. |
| `include_source_references` | `True` | Ask the writer to cite source filenames where useful. |
| `max_evidence_chars` | `None` | Deterministically truncate the evidence pack if it exceeds this size. |
| `section_context_mode` | `"all_evidence"` | Reserved. The whole report is written in one call, so all evidence is always available to every section. |
| `parser_choice` | `"auto"` | PDF parser: `auto` (→ `pymupdf`), `pymupdf`, `vision`, `multimodal`, `docling`. |
| `parser_options` | `None` | Forwarded to the chosen parser (`{"ctor": {...}}`, `{"openai_config": ...}`). |
| `transcriber_options` | `None` | Forwarded to the transcriber (`{"ctor": {...}, "call": {...}}`). |
| `image_options` | `None` | Image handling (see below). |
| `writer_options` | `None` | `model`, `provider`, and any extra LLM chat kwargs (`temperature`, `reasoning_effort`, …). `model`/`provider` are consumed; the rest are forwarded to the LLM call. |

## Supported input types

| Type | Extensions | Processing |
|---|---|---|
| Text | `.txt` | direct read |
| Markdown | `.md`, `.markdown` | direct read |
| CSV | `.csv` | stdlib `csv` → Markdown table |
| Excel | `.xlsx`, `.xls` | `openpyxl` → Markdown table (skipped with a note if `openpyxl` is missing) |
| PDF | `.pdf` | `parser_choice`: pymupdf / vision / multimodal / docling |
| Word | `.docx` | `DocxParser` |
| Audio/Video | `.mp3`, `.wav`, `.m4a`, `.mp4`, … | `Transcriber` |
| Images | `.png`, `.jpg`, `.jpeg`, `.webp`, `.tiff`, … | see below |

### Image handling

`image_options={"mode": ...}` selects how images become evidence:

- `"parse"` (default) — general parsing to Markdown via `VisionParser.convert_image()`. Use when you want all of the image's content as text.
- `"structured"` — `VisionExtractor.extract()` with `image_options["user_requirements"]`; the returned dict is serialized to Markdown. Use when you want specific structured fields.

```python
image_options={"mode": "structured", "user_requirements": "Extract the table of measurements."}
```

### Following a sample report format

Pass an existing report as a strict format/style template:

```python
result = gen.run(
    input_paths=["materials/"],
    sections=[{"title": "Findings", "instructions": "Summarize key findings."}],
    sample_report_path="templates/previous_report.docx",
)
```

When a sample is provided, the writer **strictly adheres to its tone, style, and structure** — section layout (e.g. intro paragraph then bullets), prose vs bullet vs numbered lists, bold lead-in pattern, brevity per item, and citation style — while taking **all content only from the evidence** (it never copies the sample's facts or wording, and section titles still come from `sections`). When no sample is given, the writer uses its own clean professional format. Supported sample formats: `.txt`, `.md`, `.pdf`, `.docx`.

## Output files (when `output_dir` is set)

```text
output_dir/
    report.md                       # the assembled report
    evidence_index.json             # source files + metadata (include_evidence_index=True)
    usage.json                      # token usage, when available
    sections/
        01_background.md
        02_findings.md
        ...
    evidence/
        normalized_sources.md       # the full evidence pack sent to the writer
```

These outputs are compatible with the report-writing evaluation framework in `eval_methods/report_writing_eval/`.

## Environment / API keys

Uses the same configuration as other GAIK components. For Azure OpenAI set `AZURE_API_KEY`, `AZURE_ENDPOINT`, `AZURE_API_VERSION`, `AZURE_DEPLOYMENT`; for standard OpenAI set `OPENAI_API_KEY`. See `get_openai_config()` in `gaik.software_components.config`.

## V1 limitations

- The whole report is written in one LLM call with all evidence in context (no per-section retrieval). Use `max_evidence_chars` for very large inputs; retrieval is a future enhancement.
- Markdown is the only output format (DOCX is a planned later phase).
- No per-source descriptions/roles (`input_paths` only); richer `input_sources` is deferred.

## Example

See `implementation_layer/examples/software_modules/multi_source_report_generator/report_generation_example.py`.
