# Multi-Source Report Generator — Example

Generates a user-defined Markdown report from a folder of mixed source files.

## Run

1. Put source files in `sample_inputs/` — any mix of supported types:
   - works with the base install: `.md`, `.txt`, `.csv`
   - need GAIK extras: `.pdf`, `.docx`, `.xlsx`, audio/video, images
2. Set credentials in a `.env` at the repo root (`AZURE_API_KEY`, `AZURE_ENDPOINT`, `AZURE_API_VERSION`, `AZURE_DEPLOYMENT` — or `OPENAI_API_KEY`).
3. Run:

   ```bash
   python report_generation_example.py
   ```

The assembled report and per-section files are written to `output/`:

```text
output/
    report.md
    evidence_index.json
    usage.json
    sections/
        01_background.md
        02_findings.md
        03_recommendations.md
    evidence/
        normalized_sources.md
```

## What it shows

- `input_paths` with a folder of mixed file types (expanded recursively)
- a fully user-defined report structure (titles + per-section instructions)
- `sample_report_path` — an example report (`sample_report.md`) whose format and style the writer strictly follows (content still comes only from the evidence)
- PDF parser selection via `parser_choice`
- image handling via `image_options` (`"parse"` for general parsing, `"structured"` for `VisionExtractor`)
- Markdown output

`sample_report.md` is a generic structure/style exemplar — edit it (or point `sample_report_path` at your own `.txt`/`.md`/`.pdf`/`.docx`) to control the look of the generated report.

See the module documentation at
`implementation_layer/src/gaik/software_modules/multi_source_report_generator/README.md`.
