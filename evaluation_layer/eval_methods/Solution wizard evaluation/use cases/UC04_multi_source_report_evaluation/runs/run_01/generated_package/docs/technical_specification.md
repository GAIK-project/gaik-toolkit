# Technical Specification — Q2 2026 Supplier Performance Report — Multi-Source Synthesis

> Generated from `use_case.blueprint.json`. Source of truth is the blueprint; regenerate after any change.

## Overview
GAIK synthesises four quarterly procurement documents (KPI spreadsheet, quality-audit report, meeting notes, incident log) into a structured, cited Markdown report with evidence index; a procurement manager reviews and approves the draft before release.

- **Use-case id:** `uc04_supplier_performance_report`
- **Domain:** manufacturing_procurement
- **Primary language:** English
- **Runtime interface:** cli

## Inputs and outputs
- **Input types:** spreadsheet, pdf, markdown, csv
- **Input formats:** xlsx, pdf, md, csv
- **Output types:** markdown, json
- **Data sources:** local files resolved relative to poc_input_bundle.json

## Selected components
- **MultiSourceReportGenerator** (module) — End-to-end module for mixed document inputs to narrative report. Subsumes all parsing, evidence curation, section writing, and review steps. Supports agentic mode, strict review, source references, and evidence index — all required by this use case.

**MultiSourceReportGenerator** — selected because it is the canonical end-to-end module for the `multi_source_report` pattern: it accepts all four input formats (xlsx, text-based PDF, Markdown, CSV), manages internal parsing without separate parser steps, and natively writes both report.md and evidence_index.json. Non-default options set: `agentic=True` (six-section hierarchical report with `depends_on` chains requires per-section drafting and fact-check repair); `strict_review=True` (raises before persisting output if the reviewer has unresolved edits — required by the accuracy-critical fixture test and the human-review gate); `include_source_references=True` (inline [source_file] citations required by acceptance criteria); `verbose=True` (per-section progress to CLI); `writer_options` and `review_options` both set to `gpt-5.4 / temperature 1.0 / reasoning_effort medium` per user specification; `output_docx=False`, `curate_evidence=False`, `polish=False` per explicit user instructions.

## Workflow
| Step | Type | Component | Inputs | Outputs |
|------|------|-----------|--------|---------|
| upload_sources | user_task | — <br/>opts: bundle_format=poc_input_bundle.json, path_resolution=relative to bundle file | — | kpi_spreadsheet, quality_audit_pdf, meeting_notes_md, incident_log_csv |
| synthesise_report | automated_task | MultiSourceReportGenerator <br/>opts: parser_choice=auto, agentic=True, strict_review=True, include_source_references=True, include_evidence_index=True, sample_report_path=report_template.md, report_language=English, report_title=Q2 2026 Supplier Performance Report, output_docx=False, curate_evidence=False, polish=False, verbose=True, report_description=Internal management report for procurement leadership covering Q2 supplier delivery, quality, spend, risks, and agreed actions., writer_options={'model': 'gpt-5.4', 'temperature': 1.0, 'reasoning_effort': 'medium'}, review_options={'model': 'gpt-5.4', 'temperature': 1.0, 'reasoning_effort': 'medium'}, report_spec=report_spec.json, sections=[{'id': 'executive_summary', 'title': 'Executive Summary', 'instructions': 'Summarize overall Q2 supplier performance, identify the main concern, and state the management decision. Use only supplied evidence and cite source filenames inline.'}, {'id': 'kpi_overview', 'title': 'KPI Overview', 'instructions': 'Create a Markdown table for Nordic Components, Baltic Fasteners, Alpine Sensors, and Overall. Show total deliveries, on-time delivery percentage, total units, defective units percentage, and spend in EUR. Calculate from the KPI workbook and round percentages to one decimal place.'}, {'id': 'supplier_findings', 'title': 'Supplier Findings', 'instructions': 'Give a separate evidence-grounded finding for each supplier, combining the KPI workbook with relevant audit, incident, and meeting evidence.', 'depends_on': ['kpi_overview']}, {'id': 'risks', 'title': 'Quality and Delivery Risks', 'instructions': 'Describe supported quality and delivery risks. Explicitly identify the approximate EUR 410,000 meeting-note figure versus the exact workbook spend instead of silently choosing the approximate number.', 'depends_on': ['kpi_overview', 'supplier_findings']}, {'id': 'actions', 'title': 'Actions and Owners', 'instructions': 'Create a table with Action, Owner, Due Date, and Completion Condition. Include only actions explicitly stated in the evidence. Place source citations [filename] in the Action column only; do not add citations in the Owner, Due Date, or Completion Condition columns.', 'depends_on': ['supplier_findings', 'risks']}, {'id': 'source_references', 'title': 'Source References', 'instructions': 'List every source file used in the report. Use exact filenames.'}] | kpi_spreadsheet, quality_audit_pdf, meeting_notes_md, incident_log_csv | synthesised_report, evidence_index |
| notify_manager | automated_task | — <br/>opts: notification_method=manual handoff (PoC scope — no system integration) | synthesised_report | — |
| manager_review | human_review | — <br/>opts: decision=approve or return for rework, rework_path=analyst revises inputs and re-runs pipeline | synthesised_report, evidence_index | — |

### Artifacts
- `kpi_spreadsheet` — document, source: user_upload
- `quality_audit_pdf` — pdf, source: user_upload
- `meeting_notes_md` — text, source: user_upload
- `incident_log_csv` — text, source: user_upload
- `synthesised_report` — text, source: generated (final output)
- `evidence_index` — text, source: generated (final output)

## Output schema
- **Schema name:** SupplierPerformanceReport
- **Field count:** 6
- **Required fields:** executive_summary, kpi_overview, supplier_findings, risks, actions, source_references
- **Missing-value policy:** state unavailable and omit the claim rather than speculate

**Fields:**
- {'id': 'executive_summary', 'title': 'Executive Summary', 'instructions': 'Summarize overall Q2 supplier performance, identify the main concern, and state the management decision. Use only supplied evidence and cite source filenames inline.'}
- {'id': 'kpi_overview', 'title': 'KPI Overview', 'instructions': 'Create a Markdown table for Nordic Components, Baltic Fasteners, Alpine Sensors, and Overall. Show total deliveries, on-time delivery percentage, total units, defective units percentage, and spend in EUR. Calculate from the KPI workbook and round percentages to one decimal place.'}
- {'id': 'supplier_findings', 'title': 'Supplier Findings', 'instructions': 'Give a separate evidence-grounded finding for each supplier, combining the KPI workbook with relevant audit, incident, and meeting evidence.', 'depends_on': ['kpi_overview']}
- {'id': 'risks', 'title': 'Quality and Delivery Risks', 'instructions': 'Describe supported quality and delivery risks. Explicitly identify the approximate EUR 410,000 meeting-note figure versus the exact workbook spend instead of silently choosing the approximate number.', 'depends_on': ['kpi_overview', 'supplier_findings']}
- {'id': 'actions', 'title': 'Actions and Owners', 'instructions': 'Create a table with Action, Owner, Due Date, and Completion Condition. Include only actions explicitly stated in the evidence. Place source citations [filename] in the Action column only; do not add citations in the Owner, Due Date, or Completion Condition columns.', 'depends_on': ['supplier_findings', 'risks']}
- {'id': 'source_references', 'title': 'Source References', 'instructions': 'List every source file used in the report. Use exact filenames.'}

**Validation rules:**
- All KPI percentages rounded to one decimal place
- EUR 405,000 (workbook) used as authoritative Nordic spend; EUR 410,000 (meeting note) disclosed as approximation
- All material claims cite exact source filename in square brackets
- No invented actions, owners, dates, or external facts

## Model configuration
- **Model provider:** azure_openai
- **Model preferences:** generation_model: gpt-5.4, review_model: gpt-5.4, temperature: 1.0, reasoning_effort: medium

## Runtime and integration assumptions
- **Integration targets:** _none_
- **Human review:** yes

## Security and governance
- **Security constraints:** Use only supplied evidence — no web browsing or external enrichment, External model API (Azure OpenAI) is permitted, Synthetic internal procurement data — no personal data, Evidence index provides the PoC audit trail
- **Contains personal data:** false
- **Output sensitivity:** internal
- **Audit log required:** yes

## Evaluation method
test_fixture: fixtures/expected_report_results.json, required_facts: ['F01', 'F02', 'F03', 'F04', 'F05', 'F06', 'F07', 'F08', 'F09', 'F10'], acceptance_policy: {'semantic_matching': True, 'numeric_values_must_be_correct': True, 'required_citation_format': '[source_file]', 'extra_unsupported_claims_are_failures': True}, prohibited_behavior: ['Do not invent actions, owners, deadlines, suppliers, or external market facts', 'Do not silently use EUR 410,000 as the exact Nordic spend', 'Do not claim the report is manager-approved; the PoC produces a draft for review']
