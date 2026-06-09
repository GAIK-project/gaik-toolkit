# Multi-Source Report Generator

Generate a **user-defined long-form report** from many mixed source files using an LLM.

You provide a set of files (PDF, Word, Excel/CSV, text, Markdown, audio/video, images) and a report structure (section titles + per-section instructions). The module normalises every file into Markdown evidence using the appropriate GAIK parser, transcriber, or extractor, then writes the whole report (optionally following a sample report's format) and returns the Markdown plus a per-section breakdown.

## GAIK's software components used

`MultiSourceReportGenerator` orchestrates several existing GAIK software **components**. Each component is used for a specific source type:

| Component | Role in this module |
|---|---|
| `PyMuPDFParser` | Fast local PDF text extraction (default for `parser_choice="auto"`) |
| `VisionParser` | PDF-to-Markdown via vision model; also used for general image-to-Markdown (`VisionParser.convert_image()`) |
| `MultimodalParser` | PDF-to-Markdown using OpenAI, Claude, or Google in one multimodal call |
| `DoclingParser` | Advanced PDF parsing with OCR and table extraction |
| `DocxParser` | Word document (`.docx`) text extraction |
| `Transcriber` | Audio/video transcription; handles compression and chunking for long files |
| `VisionExtractor` | Structured field extraction from images or PDFs in a single multimodal call |

The individual components each handle one source type and return raw text or structured data. This module accepts any mix of source types, routes each file to the right component automatically, combines all extracted content into a unified evidence pack, and writes the whole report in a single LLM call using the section structure you define.

## Installation

```bash
pip install "gaik[multi-source-report-generator]"
```

Text/Markdown/CSV inputs work with the base install. Additional source types pull in optional dependencies:

| Source type | Extra required |
|---|---|
| PDF (vision/multimodal/docling parser) | `gaik[parser]` |
| Word (`.docx`) | `gaik[parser]` |
| Audio/Video | `gaik[transcriber]` |
| Images | `gaik[parser]` (VisionParser) or `gaik[extract]` (VisionExtractor) |
| Excel (`.xlsx`) | `openpyxl` |


## Constructor

```python
MultiSourceReportGenerator(*, api_config: dict | None = None, use_azure: bool = True)
```

| Option | Purpose |
|---|---|
| `api_config` | Shared API config dict. If `None`, built via `get_openai_config(use_azure)`. |
| `use_azure` | Build a default Azure OpenAI config when `api_config` is not provided. |

Per-run settings live in `run(...)`, not the constructor — consistent with other GAIK modules.

## Quick start

```python
from gaik.software_modules.multi_source_report_generator import MultiSourceReportGenerator

gen = MultiSourceReportGenerator(
    api_config=None,   # built from env vars when None
    use_azure=True,    # set False for standard OpenAI
)

result = gen.run(
    # ── Input ────────────────────────────────────────────────────────────────
    input_paths=[                          # files or folders (expanded recursively)
        "materials/specification.pdf",
        "materials/meeting_notes.docx",
        "materials/interview.mp3",
        "materials/photo_1.jpg",
        "materials/table.xlsx",
        "materials/notes/",                # folder — all supported files inside
    ],

    # ── Report structure ─────────────────────────────────────────────────────
    report_title="Project Assessment Report",
    sections=[
        {"title": "Background",      "instructions": "Summarize the project context."},
        {"title": "Findings",        "instructions": "Describe key findings from the evidence."},
        {"title": "Recommendations", "instructions": "Give practical recommendations based only on the evidence."},
    ],

    # ── Optional format template ──────────────────────────────────────────────
    # When provided, the writer strictly follows its tone, style, and structure.
    # Supported formats: .txt, .md, .pdf, .docx
    sample_report_path="templates/previous_report.md",

    # ── Output ────────────────────────────────────────────────────────────────
    output_dir="output/report",            # writes report.md, sections/, evidence/
    report_language="English",             # optional; omit to let the model decide
    include_source_references=True,        # cite source filenames in the report

    # ── Parsing options ───────────────────────────────────────────────────────
    # PDF parser: "auto" (→ pymupdf), "pymupdf", "vision", "multimodal", "docling"
    parser_choice="auto",
    parser_options={},                     # forwarded to the chosen parser

    # ── Transcription options ─────────────────────────────────────────────────
    transcriber_options={
        "ctor": {
            "compress_audio": True,
            "output_dir": "output/transcripts",   # saves raw transcript files
        },
    },

    # ── Image options ─────────────────────────────────────────────────────────
    # mode "parse"      → VisionParser.convert_image() — general text/content extraction
    # mode "structured" → VisionExtractor.extract()    — structured field extraction
    image_options={"mode": "parse"},
    # image_options={"mode": "structured", "user_requirements": "Extract all measurements."},

    # ── LLM / writer options ──────────────────────────────────────────────────
    writer_options={
        "model": "gpt-5.4",
        "temperature": 0,
        "reasoning_effort": "medium",      # any extra kwargs forwarded to the LLM call
    },

    # ── Evidence size limit ───────────────────────────────────────────────────
    max_evidence_chars=200_000,            # truncate evidence pack if too large; None = no limit
)

print(result.markdown_path)   # output/report/report.md
print(result.markdown)        # the full report as a string
print(result.usage)           # token usage dict
```
```

## Supported input types

| Type | Extensions | GAIK component used |
|---|---|---|
| Text | `.txt` | direct read |
| Markdown | `.md`, `.markdown` | direct read |
| CSV | `.csv` | stdlib `csv` → Markdown table |
| Excel | `.xlsx`, `.xls` | `openpyxl` → Markdown table |
| PDF | `.pdf` | `PyMuPDFParser` / `VisionParser` / `MultimodalParser` / `DoclingParser` (selected by `parser_choice`) |
| Word | `.docx` | `DocxParser` |
| Audio/Video | `.mp3`, `.wav`, `.m4a`, `.mp4`, … | `Transcriber` |
| Images | `.png`, `.jpg`, `.jpeg`, `.webp`, `.tiff`, … | `VisionParser.convert_image()` or `VisionExtractor` (selected by `image_options`) |

### Image handling

`image_options={"mode": ...}` selects how images become evidence:

- `"parse"` (default) — `VisionParser.convert_image()`: sends the image to a vision model and returns all visible content as Markdown. Use for general text/content extraction.
- `"structured"` — `VisionExtractor.extract()` with `image_options["user_requirements"]`: returns structured fields as a dict, serialised to Markdown. Use when you need specific fields.

```python
# General parsing (default)
image_options={"mode": "parse"}

# Structured extraction
image_options={"mode": "structured", "user_requirements": "Extract all measurements from the table."}
```

### Following a sample report format

Pass any existing report as a strict format/style template:

```python
result = gen.run(
    input_paths=["materials/"],
    sections=[{"title": "Findings", "instructions": "Summarize key findings."}],
    sample_report_path="templates/previous_report.docx",
)
```

When a sample is provided, the writer analyses it and **adheres to its tone, style, and structure**: section layout, use of prose vs bullet vs numbered lists, item length, bold lead-in pattern, and citation style. All content still comes only from the evidence — facts and wording are never copied from the sample, and section titles still come from `sections`. When no sample is given, the writer uses its own clean professional format.

## Output files (when `output_dir` is set)

```text
output_dir/
    report.md                       # assembled report
    evidence_index.json             # source files + metadata
    usage.json                      # token usage
    sections/
        01_background.md
        02_findings.md
        ...
    evidence/
        normalized_sources.md       # full evidence pack sent to the LLM
```

Output is compatible with the report-writing evaluation framework in `eval_methods/report_writing_eval/`.

## Environment / API keys

Uses the same configuration as other GAIK components. Set `AZURE_API_KEY`, `AZURE_ENDPOINT`, `AZURE_API_VERSION`, `AZURE_DEPLOYMENT` for Azure OpenAI, or `OPENAI_API_KEY` for standard OpenAI. See `get_openai_config()` in `gaik.software_components.config`.

## Example

See `implementation_layer/examples/software_modules/multi_source_report_generator/report_generation_example.py`.
