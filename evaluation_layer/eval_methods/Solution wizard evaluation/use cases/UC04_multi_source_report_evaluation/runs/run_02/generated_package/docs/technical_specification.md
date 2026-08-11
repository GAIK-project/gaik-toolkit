# Technical Specification — Quarterly Supplier Performance Report Generator

> Generated from `use_case.blueprint.json`. Source of truth is the blueprint; regenerate after any change.

## Overview
Synthesise KPI spreadsheet, quality audit, meeting notes, and delivery-incident log into a structured, evidence-grounded Markdown report with inline citations and an evidence index for procurement management review.

- **Use-case id:** `supplier_performance_report`
- **Domain:** manufacturing_procurement
- **Primary language:** en
- **Runtime interface:** cli

## Inputs and outputs
- **Input types:** xlsx, pdf, markdown, csv
- **Input formats:** xlsx, pdf, md, csv
- **Output types:** markdown, json
- **Data sources:** local files referenced via poc_input_bundle.json

## Selected components
- **MultiSourceReportGenerator** (module) — Pattern is multi_source_report. The module subsumes all parsing (xlsx, pdf, md, csv), synthesis, and report-writing steps end-to-end. No separate parser, transcriber, or extractor steps are required.

**MultiSourceReportGenerator** — selected because the pattern is `multi_source_report`: four heterogeneous file types (xlsx, pdf, md, csv) must be parsed and synthesised end-to-end into a narrative report without a separate extraction schema. Non-default options set: `agentic=True` (multi-section hierarchical report, accuracy-critical; each section drafted, fact-checked, and reviewer-repaired independently); `strict_review=True` (raises before writing output if reviewer corrections are unresolved — enforces the no-premature-release requirement); `include_source_references=True` (inline `[source_file]` citations required); `include_evidence_index=True` (audit trail requirement); `writer_options` and `review_options` both set to `{model: gpt-5.4, temperature: 1.0, reasoning_effort: medium}` (user-specified); `sample_report_path=report_template.md` (enforces the required six-heading structure); `output_docx=False`, `curate_evidence=False`, `polish=False` (explicitly excluded by user specification).

## Workflow
| Step | Type | Component | Inputs | Outputs |
|------|------|-----------|--------|---------|
| upload_sources | user_task | — | — | kpi_spreadsheet, quality_audit_pdf, meeting_notes_md, incident_log_csv |
| generate_report | automated_task | MultiSourceReportGenerator <br/>opts: agentic=True, parser_choice=auto, strict_review=True, include_source_references=True, include_evidence_index=True, report_language=English, report_title=Q2 2026 Supplier Performance Report, output_docx=False, curate_evidence=False, polish=False, verbose=True, writer_options={'model': 'gpt-5.4', 'temperature': 1.0, 'reasoning_effort': 'medium'}, review_options={'model': 'gpt-5.4', 'temperature': 1.0, 'reasoning_effort': 'medium'}, sample_report_path=report_template.md, sections=loaded_from_report_spec_json | kpi_spreadsheet, quality_audit_pdf, meeting_notes_md, incident_log_csv | report_draft_md, evidence_index_json |
| notify_reviewer | automated_task | — <br/>opts: note=Deliver output/report.md and output/evidence_index.json to the procurement manager. In PoC: console message confirming output files written. | report_draft_md, evidence_index_json | — |
| manager_review | human_review | — <br/>opts: decision=approve_or_return, rejection_outcome=return to analyst for rework and regeneration | report_draft_md, evidence_index_json | approved_report_md |

### Artifacts
- `kpi_spreadsheet` — document, source: user_upload
- `quality_audit_pdf` — pdf, source: user_upload
- `meeting_notes_md` — text, source: user_upload
- `incident_log_csv` — text, source: user_upload
- `report_draft_md` — text, source: generated
- `evidence_index_json` — text, source: generated (final output)
- `approved_report_md` — text, source: generated (final output)

## Output schema
- **Schema name:** _not specified_
- **Field count:** 6
- **Required fields:** executive_summary, kpi_overview, supplier_findings, quality_and_delivery_risks, actions_and_owners, source_references
- **Missing-value policy:** _not specified_

**Fields:**
- {'id': 'executive_summary', 'title': 'Executive Summary', 'instructions': 'Synthesise overall Q2 2026 supplier performance in 2-3 paragraphs. Cover the headline KPIs (total deliveries, on-time rate, units, defect rate, EUR spend), the key risks and findings, and any data conflicts. In particular, explicitly disclose that the meeting notes state approximately EUR 410,000 for Nordic Components while the authoritative workbook gives EUR 405,000. State clearly that this report is a draft pending procurement manager review and must not be released until approved.'}
- {'id': 'kpi_overview', 'title': 'KPI Overview', 'instructions': 'Present a Markdown table with one row per supplier (Nordic Components, Baltic Parts, Alpine Precision) plus an Overall row. Columns: Supplier | Total Deliveries | On-Time % | Total Units | Defective % | EUR Spend. Calculate all values from supplier_kpis_q2_2026.xlsx (authoritative for spend and units). Round percentages to one decimal place. Cite the workbook [supplier_kpis_q2_2026.xlsx] for every cell value.', 'depends_on': ['executive_summary']}
- {'id': 'supplier_findings', 'title': 'Supplier Findings', 'instructions': 'Write a per-supplier narrative subsection for each of Nordic Components, Baltic Parts, and Alpine Precision. For each: summarise KPI performance from the workbook; cite quality audit findings including the 72/100 audit score and major findings for Nordic; highlight delivery incidents (three Nordic incidents, two being assembly delays) from the incident log; note conditional status and the 85/100 release threshold from the audit; note Baltic preference and Alpine single-source risk from meeting notes. Cite exact filenames [source_file] for every material claim.', 'depends_on': ['kpi_overview']}
- {'id': 'quality_and_delivery_risks', 'title': 'Quality and Delivery Risks', 'instructions': 'List and explain risks derived strictly from nordic_components_quality_audit.pdf and delivery_incidents_q2_2026.csv. Include: audit major findings, three Nordic incidents including two assembly delays, the 72/100 audit score against the 85/100 release threshold, and Nordic conditional status. Do not speculate or introduce facts not present in these two source files. Cite each risk to its specific source file and, where available, page, row, or table reference.', 'depends_on': ['supplier_findings']}
- {'id': 'actions_and_owners', 'title': 'Actions and Owners', 'instructions': "Present a Markdown table with columns: Action | Owner | Due Date | Completion Condition. Include only actions that have named owners and due dates explicitly stated in the source documents, primarily from procurement_meeting_notes_q2_2026.md. Do not fabricate, infer, or generalise actions or owners. If a source action lacks an owner or due date, state 'not specified' in that cell and cite the source. Every row must cite [source_file].", 'depends_on': ['quality_and_delivery_risks']}
- {'id': 'source_references', 'title': 'Source References', 'instructions': 'List all four source files used in this report as a numbered list: (1) supplier_kpis_q2_2026.xlsx — KPI data and EUR spend; (2) nordic_components_quality_audit.pdf — quality audit; (3) procurement_meeting_notes_q2_2026.md — meeting decisions and actions; (4) delivery_incidents_q2_2026.csv — delivery incidents.', 'depends_on': ['executive_summary', 'kpi_overview', 'supplier_findings', 'quality_and_delivery_risks', 'actions_and_owners']}

**Validation rules:**
- _not specified_

## Model configuration
- **Model provider:** azure_openai
- **Model preferences:** model: gpt-5.4, temperature: 1.0, reasoning_effort: medium

## Runtime and integration assumptions
- **Integration targets:** _none_
- **Human review:** yes

## Security and governance
- **Security constraints:** Local files only for PoC; no external services or enterprise system integration, No PII confirmed in PoC synthetic data; production data may include supplier contact information
- **Contains personal data:** unknown
- **Output sensitivity:** internal
- **Audit log required:** yes

## Evaluation method
semantic_match_to_fixtures: fixtures/expected_report_results.json, required_sections: 6, required_source_file_coverage: 4, required_kpi_values: Overall 299/91.6%/26550/2.0%/867000; Nordic 135/85.2%/13500/3.1%/405000; Baltic 97/96.9%/9700/1.0%/194000; Alpine 67/97.0%/3350/0.6%/268000
