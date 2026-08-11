# User Guide — Q2 2026 Supplier Performance Report — Multi-Source Synthesis

> How to run the solution, provide input, inspect output, and adjust settings.

## What this does
GAIK synthesises four quarterly procurement documents (KPI spreadsheet, quality-audit report, meeting notes, incident log) into a structured, cited Markdown report with evidence index; a procurement manager reviews and approves the draft before release.

This proof of concept demonstrates: Given poc_input_bundle.json (four synthetic Q2 2026 sources), running 'python run_poc.py --input <path-to-poc_input_bundle.json>' must produce non-empty output/report.md and parseable output/evidence_index.json. The report must: carry the exact title 'Q2 2026 Supplier Performance Report'; contain all six required sections (Executive Summary, KPI Overview, Supplier Findings, Quality and Delivery Risks, Actions and Owners, Source References); include a KPI table with values Overall 299/91.6%/26550/2.0%/EUR867000, Nordic 135/85.2%/13500/3.1%/EUR405000, Baltic 97/96.9%/9700/1.0%/EUR194000, Alpine 67/97.0%/3350/0.6%/EUR268000; reference all four source filenames with [source_file] citations; disclose the EUR 410,000 meeting-note approximation vs EUR 405,000 workbook figure; capture audit score 72/100, major findings, three Nordic incidents with two assembly delays, conditional status and 85/100 release threshold, named owners Lena Hoffmann and Marko Laine with due dates, Baltic preference, and Alpine single-source risk. Use Windows-safe ASCII console status text.

## Prerequisites
- Python 3.11+
- Install dependencies: `pip install -r poc/requirements.txt`
- Copy `poc/.env.example` to `poc/.env` and fill in your model-provider credentials (provider: azure_openai).

## Providing input
- **Expected input:** spreadsheet, pdf, markdown, csv (formats: xlsx, pdf, md, csv)
- Place your input file(s) in `poc/sample_input/`.

The pipeline reads all source files from a bundle manifest — do **not** place files in `sample_input/` directly. Instead, pass a `poc_input_bundle.json` file that lists the four source paths (resolved relative to the bundle). The supplied fixture bundle is at `C:\Users\h02317\Downloads\fixtures\poc_input_bundle.json` and references:

| File | Format | Role |
|------|--------|------|
| `supplier_kpis_q2_2026.xlsx` | Excel workbook | Authoritative KPI and spend figures |
| `nordic_components_quality_audit.pdf` | Text-based PDF | Audit score, findings, CAPA status |
| `procurement_meeting_notes_q2_2026.md` | Markdown | Decisions, owners, due dates |
| `delivery_incidents_q2_2026.csv` | CSV | Incident records with delay impact |

All paths in the bundle are resolved relative to the directory that contains the bundle file.

## Running
```bash
python poc/run_poc.py --input <path-to-poc_input_bundle.json>
```

Example using the supplied fixtures:

```bash
python poc/run_poc.py --input "C:\Users\h02317\Downloads\fixtures\poc_input_bundle.json"
```

The pipeline prints `[INFO]` / `[OK]` / `[ERROR]` status lines as it runs (Windows-safe ASCII). Per-section progress is shown during the agentic synthesis pass.

## Inspecting the output
- Results are written to `poc/output/`.
- The output is markdown, json following the `SupplierPerformanceReport` schema.
- **Human review:** yes

**output/report.md** — open in any Markdown viewer or text editor. A correct draft contains:
- Title line: `# Q2 2026 Supplier Performance Report`
- Six `##` headings in order: Executive Summary, KPI Overview, Supplier Findings, Quality and Delivery Risks, Actions and Owners, Source References
- A KPI table with five columns (Supplier, Deliveries, On-Time %, Units, Defective %, Spend EUR) and correct values for Nordic/Baltic/Alpine/Overall
- Inline citations in `[filename]` format on every material claim
- An explicit note disclosing that the meeting notes cite approximately EUR 410,000 for Nordic Components while the workbook gives the authoritative EUR 405,000
- An Actions and Owners table with named owners (Lena Hoffmann, Marko Laine) and due dates supported by the evidence

**output/evidence_index.json** — open in any text editor or `python -m json.tool output/evidence_index.json`. It must parse without error and list entries for all four source files.

The **procurement manager** should check: are all facts traceable to a cited source? Are any claims speculative or unsupported? Is the EUR spend discrepancy disclosed? Once satisfied, the manager approves the report for release. If corrections are needed, return to the analyst who adjusts the inputs and re-runs the pipeline.

## Adjusting settings
| To change... | Edit... |
|--------------|---------|
| What is extracted / the fields | `poc/prompts/extraction_requirements.md` then re-run (schema regenerates) |
| Output structure | `poc/schemas/output_schema.py` |
| Model / temperature | `poc/config.yaml` |

## Privacy note
Personal data: false · output sensitivity: internal. Handle outputs accordingly.
