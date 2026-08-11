# UC04 Scripted Answers

Use only the matching answer when the wizard asks the corresponding topic.

## SA01 - business_context_and_stakeholders

**Trigger:** Who uses the solution, what is the current reporting process, what problem should be solved, who reviews it, or who else is involved?

**Answer:** A procurement analyst is the main user and prepares the quarterly supplier-performance report for procurement management. Today the analyst manually combines KPI spreadsheets, quality audits, meeting notes, and incident logs. This is slow and can produce inconsistent calculations, wording, and source traceability. Category owners and the Procurement Quality Team maintain or provide evidence. A procurement manager reviews every draft before release. The expected value is faster, consistent, evidence-grounded reporting with reliable calculations and source references.

## SA02 - source_inputs_formats_and_language

**Trigger:** What sources, files, formats, languages, locations, or quality conditions must be supported?

**Answer:** The evaluated bundle contains four synthetic English sources: supplier_kpis_q2_2026.xlsx, nordic_components_quality_audit.pdf, procurement_meeting_notes_q2_2026.md, and delivery_incidents_q2_2026.csv. The PDF is text based. Preserve the exact source filename and available page, sheet, table, or row context during normalization. The first PoC uses these local files and resolves their paths relative to poc_input_bundle.json. A live repository or external web source is outside scope.

## SA03 - report_output_structure_and_references

**Trigger:** What report, output format, title, sections, tables, references, fields, or required content should be generated?

**Answer:** Generate an English Markdown draft titled 'Q2 2026 Supplier Performance Report' for 1 April through 30 June 2026, plus evidence_index.json. Required sections are Executive Summary; KPI Overview; Supplier Findings; Quality and Delivery Risks; Actions and Owners; and Source References. KPI Overview must be a Markdown table showing total deliveries, on-time percentage, total units, defective percentage, and EUR spend for each supplier and Overall. Actions and Owners must contain Action, Owner, Due Date, and Completion Condition. Material factual claims cite exact filenames as [source_file]. Source References lists all files used.

## SA04 - grounding_calculation_uncertainty_and_conflicts

**Trigger:** How should grounding, calculations, missing evidence, uncertainty, conflicts, approximations, or unsupported claims be handled?

**Answer:** Use only supplied evidence and cite every material claim. Calculate KPI metrics from the workbook, use it as authoritative for exact spend, and round percentages to one decimal. If evidence is absent, state that it is unavailable and omit the claim rather than speculate. Identify conflicts or approximations and cite the relevant sources. In particular, disclose that meeting notes say approximately EUR 410,000 for Nordic Components while the workbook gives the exact EUR 405,000. Do not fabricate references, actions, owners, dates, thresholds, or external facts.

## SA05 - employee_interaction_review_and_return_path

**Trigger:** How will employees interact with the system, who reviews the report, and what happens when a draft is returned?

**Answer:** Employees use a web application. A procurement analyst uploads one or more files, selects the saved report configuration, generates a draft, and downloads it. The procurement manager reviews the draft, calculations, actions, and source references. If the manager returns it, the analyst corrects the source data or report instructions and regenerates the draft; the review cycle repeats. The AI output remains a draft until manager approval. The first PoC may use CLI input and Markdown/JSON output.

## SA06 - security_storage_and_external_boundaries

**Trigger:** What privacy, security, storage, retention, access, authentication, audit, or provider constraints apply?

**Answer:** The synthetic files are internal procurement information and contain no personal data. External model APIs are allowed. Only supplied evidence may be used; web browsing and external enrichment are not allowed. The evidence index provides the PoC audit trail. No exact retention period, data-residency target, SLA, enterprise authentication product, or deployment topology is specified. Those may be recorded as assumptions if needed.

## SA07 - poc_goal_interface_and_evaluation

**Trigger:** What should the first proof-of-concept demonstrate, what interface should it use, what fixture should it process, or what acceptance criteria apply?

**Answer:** The first PoC must support python run_poc.py --input <path-to-poc_input_bundle.json>, resolve every source, report_spec.json, and report_template.md relative to the bundle, process all four supplied sources, and create non-empty output/report.md plus parseable output/evidence_index.json. Use Windows-safe ASCII console status text. The report must contain the exact title and six required sections, reference all four filenames, and semantically match fixtures/expected_report_results.json. Key values are: Overall 299 deliveries, 91.6% on time, 26,550 units, 2.0% defective, EUR 867,000; Nordic 135, 85.2%, 13,500, 3.1%, EUR 405,000; Baltic 97, 96.9%, 9,700, 1.0%, EUR 194,000; Alpine 67, 97.0%, 3,350, 0.6%, EUR 268,000. It must also capture the audit score 72/100, major findings, three Nordic incidents with two assembly delays, conditional status, the 85/100 release threshold, named owners and dates, Baltic preference, Alpine single-source risk, and the EUR 410,000 versus EUR 405,000 discrepancy. Web UI, external sources, enterprise integration, and DOCX/Pandoc are outside the first PoC.

## SA08 - provider_model_scale_and_budget

**Trigger:** Which provider, model, reasoning, temperature, deployment, SLA, volume, latency, or budget should be used?

**Answer:** Use Azure OpenAI gpt-5.4 for writing and review, temperature 1.0, and reasoning effort medium. No numerical SLA, throughput, latency, source-volume, budget, cost-saving, accuracy, or adoption target is specified. Valid implementation defaults must be labelled as assumptions.

## SA09 - business_success_and_risks

**Trigger:** What does business success mean, what risks should be considered, and is there a quantified target?

**Answer:** Business success means a complete cited draft is produced faster, calculations and actions are correct, conflicts are visible, and only a manager-approved report is released. No numerical improvement target is specified. Key risks are hallucinated facts, calculation errors, missing or wrong references, silent conflict resolution, omitted actions, unsupported recommendations, and premature release of an unapproved draft.

## SA10 - report_module_and_options

**Trigger:** Which report-writing approach, module options, parsing mode, review mode, sample, source-reference, or output options should apply?

**Answer:** Use MultiSourceReportGenerator as the single primary end-to-end module. Do not create duplicate standalone PDF, spreadsheet, or text parsing stages that the module already subsumes. Set parser_choice='auto', agentic=true, strict_review=true, include_source_references=true, include_evidence_index=true, sample_report_path to the bundle's report_template.md, report_language='English', report_title='Q2 2026 Supplier Performance Report', output_docx=false, curate_evidence=false, polish=false, verbose=true, and writer/reviewer model gpt-5.4. Configure the six section specifications and their depends_on relationships from report_spec.json.

## SA11 - validation_and_release_rules

**Trigger:** What validation rules, review gates, special instructions, or exceptions should apply?

**Answer:** Require the exact title, all six headings, a KPI table with one-decimal calculations, an action table with supported owners and dates, inline [source_file] references, and an evidence index that covers all four source files. Explicitly disclose the approximate spend discrepancy. Reject unsupported facts, actions, references, or a claim that the PoC draft is already approved. The procurement manager either approves the draft for release or returns it for analyst rework and regeneration.

## Routine confirmation policy

Answer every routine confirmation before original PoC execution with:

> Yes. Proceed without changes.

## Unexpected question

> Not specified for this evaluation. If a value is required, record it as an explicit assumption for user confirmation.
