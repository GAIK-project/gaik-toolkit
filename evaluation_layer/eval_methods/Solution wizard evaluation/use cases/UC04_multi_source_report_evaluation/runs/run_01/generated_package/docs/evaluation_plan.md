# Evaluation Plan — Q2 2026 Supplier Performance Report — Multi-Source Synthesis

> How the quality of this solution is measured. Generated from the blueprint.

## Goal
Demonstrate: Given poc_input_bundle.json (four synthetic Q2 2026 sources), running 'python run_poc.py --input <path-to-poc_input_bundle.json>' must produce non-empty output/report.md and parseable output/evidence_index.json. The report must: carry the exact title 'Q2 2026 Supplier Performance Report'; contain all six required sections (Executive Summary, KPI Overview, Supplier Findings, Quality and Delivery Risks, Actions and Owners, Source References); include a KPI table with values Overall 299/91.6%/26550/2.0%/EUR867000, Nordic 135/85.2%/13500/3.1%/EUR405000, Baltic 97/96.9%/9700/1.0%/EUR194000, Alpine 67/97.0%/3350/0.6%/EUR268000; reference all four source filenames with [source_file] citations; disclose the EUR 410,000 meeting-note approximation vs EUR 405,000 workbook figure; capture audit score 72/100, major findings, three Nordic incidents with two assembly delays, conditional status and 85/100 release threshold, named owners Lena Hoffmann and Marko Laine with due dates, Baltic preference, and Alpine single-source risk. Use Windows-safe ASCII console status text.

Success criteria:
- Complete cited draft produced faster than manual method
- All KPI calculations are correct and rounded to one decimal place
- Data conflicts (e.g. EUR 410,000 vs EUR 405,000) are explicitly disclosed rather than silently resolved
- Only manager-approved report is released

## Stated evaluation requirements
test_fixture: fixtures/expected_report_results.json, required_facts: ['F01', 'F02', 'F03', 'F04', 'F05', 'F06', 'F07', 'F08', 'F09', 'F10'], acceptance_policy: {'semantic_matching': True, 'numeric_values_must_be_correct': True, 'required_citation_format': '[source_file]', 'extra_unsupported_claims_are_failures': True}, prohibited_behavior: ['Do not invent actions, owners, deadlines, suppliers, or external market facts', 'Do not silently use EUR 410,000 as the exact Nordic spend', 'Do not claim the report is manager-approved; the PoC produces a draft for review']

The PoC is evaluated against `fixtures/expected_report_results.json` using the `report_writing_eval` framework. Each of the ten required facts (F01–F10) is checked for presence and correctness in the report. Pass requires all ten facts to be present and semantically correct; any single missing or wrong fact is a failure. In addition, the three prohibited behaviors are checked: inventing facts/owners/dates, silently using EUR 410,000, or claiming the report is approved.

## Recommended metrics
- **Output type:** markdown, json (schema: `SupplierPerformanceReport`)
- For structured extraction, use the GAIK `extraction_eval` framework (field-level Precision / Recall / F1, hallucination rate) via `ExtractionEvaluator`.
- For RAG / answers, use `RAG_eval` (faithfulness, answer relevance, context precision/recall) via `RAGEvaluator`.
- For transcription, use `transcription_eval`; for translation, `translation_eval`; for report writing, `report_writing_eval`.

Use the **`report_writing_eval`** framework. Evaluation dimensions:

| Dimension | Check | Pass criterion |
|-----------|-------|----------------|
| Structure | Title and all six section headings present | Exact match |
| Numeric accuracy | KPI table values for all four suppliers + Overall | Exact numeric match (percentages to 1 d.p.) |
| Source coverage | All four source filenames referenced | All four present |
| Citation format | Material claims cited as [filename] | No uncited material claims |
| Conflict disclosure | EUR 410k vs EUR 405k discrepancy | Explicitly stated |
| Required facts | F01–F10 from expected_report_results.json | All 10 pass semantic match |
| Prohibited behavior | No invented facts, owners, dates; no approval claim | Zero violations |

## Test data
- **Data sources:** local files resolved relative to poc_input_bundle.json
- Place ground-truth examples under `evals/ground_truth/` and predictions under `evals/predictions/`.

The test set for the PoC is a single run of the four synthetic Q2 2026 source files supplied in `fixtures/poc_input/sources/`. Ground truth is established by `fixtures/expected_report_results.json` (ten required facts, three prohibited behaviors, acceptance policy) and `fixtures/report_fixture_facts.txt` (plain-text fact list). These fixtures are frozen (SHA-256 hashes in `fixture_manifest.json`). For future quarters, new fixtures must be created from the updated source documents and reviewed by the procurement analyst before being committed as ground truth.

## Thresholds and acceptance
- All KPI percentages rounded to one decimal place
- EUR 405,000 (workbook) used as authoritative Nordic spend; EUR 410,000 (meeting note) disclosed as approximation
- All material claims cite exact source filename in square brackets
- No invented actions, owners, dates, or external facts

All thresholds are binary (pass / fail) per the acceptance policy:

- All 10 required facts present and semantically correct — **all 10 must pass**
- All numeric values correct (no rounding error beyond 1 d.p.) — **zero numeric errors**
- All four source filenames referenced — **all four must appear**
- Citation format `[source_file]` used on material claims — **zero uncited material claims**
- EUR 410k vs EUR 405k discrepancy explicitly disclosed — **must be present**
- Zero prohibited behavior violations — **zero tolerance**

No partial credit. A report that passes nine of ten facts is a failure.

## Human review
- **Required:** yes
- **Reviewers:** Procurement manager

## Limitations
- **Single test case:** evaluation is over one quarterly input bundle. A single run is sufficient to validate the pipeline but is not statistically representative of production variation across quarters or suppliers.
- **Synthetic data:** the four source files are synthetic. Real-world documents may have different formatting, missing fields, or inconsistent terminology that the pipeline has not been tested against.
- **Semantic matching is model-assisted:** facts F05–F10 require semantic judgment (e.g. "Nordic audit score 72/100" must be present but may be phrased differently). The evaluator uses model-based semantic matching, which may have false positives on paraphrased or partial matches.
- **No numeric tolerance beyond 1 d.p.:** percentages must match to one decimal place. If the model rounds differently (e.g. 91.64% → 91.7% instead of 91.6%), the test will catch it — this is intentional.
- **No production volume or latency data:** the PoC runs a single document set; throughput, cost per run, and latency at quarterly scale have not been measured.
