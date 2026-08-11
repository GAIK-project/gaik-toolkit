# Evaluation Plan — Quarterly Supplier Performance Report Generator

> How the quality of this solution is measured. Generated from the blueprint.

## Goal
Demonstrate: Run as 'python run_poc.py --input <path-to-poc_input_bundle.json>'. Resolve all source paths relative to the bundle. Process all four sources. Produce non-empty output/report.md and parseable output/evidence_index.json. Report must carry the exact title 'Q2 2026 Supplier Performance Report', all six required sections, references to all four source filenames, and semantically match fixtures/expected_report_results.json. Key KPI values: Overall 299/91.6%/26,550/2.0%/EUR 867,000; Nordic 135/85.2%/13,500/3.1%/EUR 405,000; Baltic 97/96.9%/9,700/1.0%/EUR 194,000; Alpine 67/97.0%/3,350/0.6%/EUR 268,000. Also captures: audit score 72/100, three Nordic incidents with two assembly delays, conditional status, 85/100 release threshold, named owners and dates, Baltic preference, Alpine single-source risk, EUR 410,000 vs EUR 405,000 discrepancy. Windows-safe ASCII console output.

Success criteria:
- Complete cited draft is produced faster than the manual process
- All KPI calculations and stated actions are correct and sourced
- Source conflicts are explicitly identified and disclosed (e.g. EUR 410,000 vs EUR 405,000 Nordic spend)
- Only procurement-manager-approved reports are released

## Stated evaluation requirements
semantic_match_to_fixtures: fixtures/expected_report_results.json, required_sections: 6, required_source_file_coverage: 4, required_kpi_values: Overall 299/91.6%/26550/2.0%/867000; Nordic 135/85.2%/13500/3.1%/405000; Baltic 97/96.9%/9700/1.0%/194000; Alpine 67/97.0%/3350/0.6%/268000

Quality is assessed against `fixtures/expected_report_results.json` using six concrete checks: (1) **Section presence** — all six headings must appear in order; (2) **KPI numeric accuracy** — the four supplier rows and Overall row must contain the exact fixture values (F01–F04); (3) **Semantic fact coverage** — all ten required facts (F01–F10) must be semantically present and attributed to the correct source; (4) **Citation coverage** — all four source filenames must appear as `[filename]` inline citations; (5) **Conflict disclosure** — the EUR 410,000/405,000 discrepancy (F10) must be explicitly identified, not silently resolved; (6) **Prohibited-behaviour absence** — no invented actions, owners, deadlines, or claims that the draft is already approved.

## Recommended metrics
- **Output type:** markdown, json (schema: `_not specified_`)
Use the GAIK `report_writing_eval` framework for the narrative quality dimension (section completeness, source coverage, factual grounding). Structural and numeric checks (KPI values, section headings, citation coverage) can be automated with a custom script that parses `output/report.md` against `fixtures/expected_report_results.json`. Semantic fact coverage (F05–F09) requires manual review by the procurement manager.

## Test data
- **Data sources:** local files referenced via poc_input_bundle.json
- Place ground-truth examples under `evals/ground_truth/` and predictions under `evals/predictions/`.

The PoC uses one evaluation bundle: `C:\Users\h02317\Downloads\fixtures\poc_input_bundle.json` with four synthetic English source files covering Q2 2026. Ground truth is `fixtures/expected_report_results.json` (10 required facts, 6 required sections, 4 required source citations, and a prohibited-behaviour list). Each PoC run produces one prediction (`poc/output/report.md`). Structural and numeric checks are automatable; semantic fact coverage (F05–F09) requires manual review. To build a larger test set, create additional bundles with different synthetic quarters and extend the fixture accordingly.

## Thresholds and acceptance
No numerical threshold has been specified by the user. Pass/fail for the PoC is binary per check: all six sections present; all KPI numeric values exact (F01–F04); EUR 410,000/405,000 discrepancy disclosed (F10); all four source filenames cited; no prohibited behaviour triggered. For semantic facts F05–F09, pass if the claim is present and attributed to the correct source file. A run that fails any single check is a PoC failure.

## Human review
- **Required:** yes
- **Reviewers:** procurement_manager

## Limitations
The ground truth covers one synthetic quarter only — accuracy on real production procurement data has not been validated. Semantic fact coverage (F05–F09) requires manual review; there is no automated semantic scorer wired to the evaluation pipeline. The model temperature is 1.0 per user specification, which introduces output variability; a single PoC run may not be fully representative — consider averaging findings over three to five runs for a more stable signal. The fixtures use "Baltic Fasteners" and "Alpine Sensors" as supplier names; the blueprint spec used slightly different names — always defer to the fixture and source files as the canonical names.
