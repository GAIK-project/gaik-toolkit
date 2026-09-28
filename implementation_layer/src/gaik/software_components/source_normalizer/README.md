# Source Normalizer

Converts mixed source files (PDF, Word, spreadsheets, text, recordings and images) to
Markdown texts that keep their provenance. It is the first stage of the report writer:
`KnowledgeCurator` reads the texts and cites each fact by the source's file name.

## Installation

```bash
pip install "gaik[source-normalizer]"
```

**Note:** Documents are parsed locally. Recordings and images need an LLM config:
recordings go to the `Transcriber` (OpenAI or Azure OpenAI) and images to the
`VisionParser`.

---

## Quick Start

```python
from gaik.software_components.knowledge_curator import KnowledgeCurator, SectionSpec
from gaik.software_components.llm import get_llm_config
from gaik.software_components.source_normalizer import SourceNormalizer

config = get_llm_config()  # Azure unless LLM_PROVIDER says otherwise

sources = SourceNormalizer(config).normalize(
    {
        "primary": ["site_visit.m4a", "inspection_notes.txt", "roof.jpg"],
        "secondary": ["previous_report.pdf", "maintenance_log.xlsx"],
    },
    progress_callback=print,
)
sources.save("output/sources")

sections = [
    SectionSpec(id="roof", title="Roof", instructions="Condition, damage and repair needs."),
]
knowledge = KnowledgeCurator(config).curate(
    sources, sections, instructions="Prefer primary sources over secondary ones."
)
```

`sources` is either `{source_class: [paths]}` or a plain list of paths, which gives
`source_class=None`. Files are converted in input order into `NormalizedSources`, a list
of `NormalizedSource`:

| Field | Value |
|-------|-------|
| `id` | Order and an ASCII slug of the file stem, e.g. `01_site_visit`, or `01_floor_plan_1` for `floor_plan (1).png`; names the saved Markdown file |
| `file` | Original file name, the citation key of downstream facts |
| `source_class` | The group the file was given in, e.g. `primary`, or `None` |
| `source_type` | `pdf`, `docx`, `spreadsheet`, `text`, `audio` or `image` |
| `tool` | What produced the text, e.g. `PyMuPDFParser` or `Transcriber` |
| `text` | The Markdown text |

`to_markdown(path)` converts one file with the same dispatch and returns its text, e.g.
to turn a sample report into Markdown.

---

## File Types

| Extension | `source_type` | `tool` | Text |
|-----------|---------------|--------|------|
| `.pdf` | `pdf` | `PyMuPDFParser` | Text layer with a `[Page N]` line before each page |
| `.docx` | `docx` | `DocxParser` | Headings as `#` headings, paragraphs and tables in document order |
| `.xlsx`, `.csv` | `spreadsheet` | `SpreadsheetParser` | A Markdown table per sheet with a `Row` column of source row numbers |
| `.txt`, `.md` | `text` | `text` | The file as UTF-8 |
| `.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac`, `.webm`, `.mp4`, `.mpeg`, `.mpga` | `audio` | `Transcriber` | Raw transcript (needs a config) |
| `.png`, `.jpg`, `.jpeg`, `.webp` | `image` | `VisionParser` | Markdown description (needs a config) |

Options: `vision_model` overrides the model for images, `transcription_model` selects
the Transcriber model (e.g. `gpt-4o-transcribe`), and `language` sets the transcription
language (default `auto`).

`sources.usage` holds the usage of the transcription and vision calls of that
`normalize` call; `normalizer.usage` keeps a running total. Usage is not saved.

A file that cannot be converted fully raises instead of being skipped:

- another file type (`.pptx`, `.doc`, `.xls`, ...), a missing path or a directory;
- two files with the same name, even from different folders, since the name is the
  citation key;
- a recording or an image without a config;
- a PDF with no text layer (e.g. a scan), a transcript with a failed segment, or a file
  that yields no text.

All files are checked before the first conversion, so a bad path fails fast.

**Recordings have no timestamps.** The transcript carries no per-utterance times (a long
recording split into chunks only gets a `[Timestamp: start - end]` line per chunk), so
the locator of a fact from a recording is null downstream.

---

## Save and Load

```python
from gaik.software_components.source_normalizer import NormalizedSources

paths = sources.save("output/sources")  # <id>.md per source + sources.json manifest
sources = NormalizedSources.load("output/sources")

text = sources.get("maintenance_log.xlsx").text
```

The saved Markdown files can be read and edited before curation. Texts that are already
available can be wrapped with `NormalizedSources.from_texts({"notes.txt": text})`.

See the [example](../../../../examples/software_components/source_normalizer/source_normalizer_example.py)
for a complete working script.

---

## Environment Variables (recordings and images only)

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_API_KEY` | Azure only | Azure OpenAI API key |
| `AZURE_ENDPOINT` | Azure only | Azure OpenAI endpoint URL |
| `AZURE_DEPLOYMENT` | Azure only | Azure deployment name |
| `OPENAI_API_KEY` | OpenAI only | Standard OpenAI API key |

## License

MIT - see [LICENSE](../../../../../LICENSE)
