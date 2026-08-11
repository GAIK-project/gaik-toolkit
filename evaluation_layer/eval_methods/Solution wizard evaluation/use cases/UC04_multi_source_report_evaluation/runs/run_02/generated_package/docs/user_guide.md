# User Guide — Quarterly Supplier Performance Report Generator

> How to run the solution, provide input, inspect output, and adjust settings.

## What this does
Synthesise KPI spreadsheet, quality audit, meeting notes, and delivery-incident log into a structured, evidence-grounded Markdown report with inline citations and an evidence index for procurement management review.

This proof of concept demonstrates: Run as 'python run_poc.py --input <path-to-poc_input_bundle.json>'. Resolve all source paths relative to the bundle. Process all four sources. Produce non-empty output/report.md and parseable output/evidence_index.json. Report must carry the exact title 'Q2 2026 Supplier Performance Report', all six required sections, references to all four source filenames, and semantically match fixtures/expected_report_results.json. Key KPI values: Overall 299/91.6%/26,550/2.0%/EUR 867,000; Nordic 135/85.2%/13,500/3.1%/EUR 405,000; Baltic 97/96.9%/9,700/1.0%/EUR 194,000; Alpine 67/97.0%/3,350/0.6%/EUR 268,000. Also captures: audit score 72/100, three Nordic incidents with two assembly delays, conditional status, 85/100 release threshold, named owners and dates, Baltic preference, Alpine single-source risk, EUR 410,000 vs EUR 405,000 discrepancy. Windows-safe ASCII console output.

## Prerequisites
- Python 3.11+
- Install dependencies: `pip install -r poc/requirements.txt`
- Copy `poc/.env.example` to `poc/.env` and fill in your model-provider credentials (provider: azure_openai).

## Providing input
- **Expected input:** xlsx, pdf, markdown, csv (formats: xlsx, pdf, md, csv)
- Place your input file(s) in `poc/sample_input/`.

The pipeline reads the four source files referenced inside `poc_input_bundle.json`. All paths are resolved relative to the bundle file's directory. For the Q2 2026 PoC the ready-made bundle is at `C:\Users\h02317\Downloads\fixtures\poc_input_bundle.json`; the `poc_input/` directory alongside it must contain:

| File | Location in bundle | Format |
|---|---|---|
| `supplier_kpis_q2_2026.xlsx` | `poc_input/sources/` | Excel workbook — authoritative KPI data and EUR spend |
| `nordic_components_quality_audit.pdf` | `poc_input/sources/` | Text-based PDF |
| `procurement_meeting_notes_q2_2026.md` | `poc_input/sources/` | Markdown |
| `delivery_incidents_q2_2026.csv` | `poc_input/sources/` | CSV |
| `report_spec.json` | `poc_input/` | Section definitions (title, instructions, depends_on) |
| `report_template.md` | `poc_input/` | Six-heading Markdown skeleton |

## Running
```bash
python poc/run_poc.py --input C:\Users\h02317\Downloads\fixtures\poc_input_bundle.json
```

## Inspecting the output
- Results are written to `poc/output/`.
- The output is markdown, json following the `_not specified_` schema.
- **Human review:** yes

A correct `output/report.md` opens with `# Q2 2026 Supplier Performance Report` and contains all six sections in order. The KPI Overview section is a Markdown table with one row per supplier (Nordic Components, Baltic Fasteners, Alpine Sensors) plus an Overall row, showing exact workbook figures rounded to one decimal (e.g. Nordic EUR 405,000, not EUR 410,000). Every material claim carries a `[filename]` citation. The EUR 410,000/405,000 discrepancy is explicitly disclosed. The report closes with a statement that it is a draft pending manager approval. The console will print `[OK] Report written` and `[OK] Evidence index written` on success, or `[FAIL]` with the specific problem on failure. `output/evidence_index.json` must be valid JSON and list all four source files. **The procurement manager should open `output/report.md`, verify the KPI table figures against the workbook, check that every action has a named owner and due date from the source documents, and confirm the conflict disclosure is present before approving.**

## Adjusting settings
| To change... | Edit... |
|--------------|---------|
| What is extracted / the fields | `poc/prompts/extraction_requirements.md` then re-run (schema regenerates) |
| Output structure | `poc/schemas/output_schema.py` |
| Model / temperature | `poc/config.yaml` |

## Privacy note
Personal data: unknown · output sensitivity: internal. Handle outputs accordingly.
