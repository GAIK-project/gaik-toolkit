# Developer Guide — Q2 2026 Supplier Performance Report — Multi-Source Synthesis

> Package structure, extension points, component configuration, tests, and evaluation.

## Architecture
This use case is driven by an **executable JSON blueprint** (`use_case.blueprint.json`) — the single source of truth. The PoC, the visual workflows (`workflow.mmd`, `workflow.bpmn`), and these docs are all *generated from it*. To change behaviour, edit the blueprint and regenerate; never hand-edit generated artifacts.

## Pipeline
| Step | Type | Component | Inputs | Outputs |
|------|------|-----------|--------|---------|
| upload_sources | user_task | — <br/>opts: bundle_format=poc_input_bundle.json, path_resolution=relative to bundle file | — | kpi_spreadsheet, quality_audit_pdf, meeting_notes_md, incident_log_csv |
| synthesise_report | automated_task | MultiSourceReportGenerator <br/>opts: parser_choice=auto, agentic=True, strict_review=True, include_source_references=True, include_evidence_index=True, sample_report_path=report_template.md, report_language=English, report_title=Q2 2026 Supplier Performance Report, output_docx=False, curate_evidence=False, polish=False, verbose=True, report_description=Internal management report for procurement leadership covering Q2 supplier delivery, quality, spend, risks, and agreed actions., writer_options={'model': 'gpt-5.4', 'temperature': 1.0, 'reasoning_effort': 'medium'}, review_options={'model': 'gpt-5.4', 'temperature': 1.0, 'reasoning_effort': 'medium'}, report_spec=report_spec.json, sections=[{'id': 'executive_summary', 'title': 'Executive Summary', 'instructions': 'Summarize overall Q2 supplier performance, identify the main concern, and state the management decision. Use only supplied evidence and cite source filenames inline.'}, {'id': 'kpi_overview', 'title': 'KPI Overview', 'instructions': 'Create a Markdown table for Nordic Components, Baltic Fasteners, Alpine Sensors, and Overall. Show total deliveries, on-time delivery percentage, total units, defective units percentage, and spend in EUR. Calculate from the KPI workbook and round percentages to one decimal place.'}, {'id': 'supplier_findings', 'title': 'Supplier Findings', 'instructions': 'Give a separate evidence-grounded finding for each supplier, combining the KPI workbook with relevant audit, incident, and meeting evidence.', 'depends_on': ['kpi_overview']}, {'id': 'risks', 'title': 'Quality and Delivery Risks', 'instructions': 'Describe supported quality and delivery risks. Explicitly identify the approximate EUR 410,000 meeting-note figure versus the exact workbook spend instead of silently choosing the approximate number.', 'depends_on': ['kpi_overview', 'supplier_findings']}, {'id': 'actions', 'title': 'Actions and Owners', 'instructions': 'Create a table with Action, Owner, Due Date, and Completion Condition. Include only actions explicitly stated in the evidence. Place source citations [filename] in the Action column only; do not add citations in the Owner, Due Date, or Completion Condition columns.', 'depends_on': ['supplier_findings', 'risks']}, {'id': 'source_references', 'title': 'Source References', 'instructions': 'List every source file used in the report. Use exact filenames.'}] | kpi_spreadsheet, quality_audit_pdf, meeting_notes_md, incident_log_csv | synthesised_report, evidence_index |
| notify_manager | automated_task | — <br/>opts: notification_method=manual handoff (PoC scope — no system integration) | synthesised_report | — |
| manager_review | human_review | — <br/>opts: decision=approve or return for rework, rework_path=analyst revises inputs and re-runs pipeline | synthesised_report, evidence_index | — |

### Components and their options
- **MultiSourceReportGenerator** (module) — End-to-end module for mixed document inputs to narrative report. Subsumes all parsing, evidence curation, section writing, and review steps. Supports agentic mode, strict review, source references, and evidence index — all required by this use case.

**MultiSourceReportGenerator** — constructed with `use_azure=True` (read from `config.yaml` → `use_azure`). All run-time options are passed directly in `run_poc.py`; `config.yaml` documents the intended values for reference only. Key options:

| Option | Value | Where to change |
|--------|-------|-----------------|
| `writer_options["model"]` / `review_options["model"]` | `gpt-5.4` | `run_poc.py` `writer_opts` / `review_opts` dicts |
| `temperature` | `1.0` | Same dicts |
| `reasoning_effort` | `"medium"` | Same dicts |
| `agentic` | `True` | Hard-coded in `run_poc.py`; requires `gaik[multi-source-report-generator-agentic]` |
| `strict_review` | `True` | Hard-coded in `run_poc.py`; raises if reviewer has unresolved edits after retries |
| `output_dir` | `poc/output/` | Derived from `Path(__file__).parent / "output"` in `run_poc.py` |
| Sections | Loaded from `report_spec.json` in the bundle; instruction overrides applied via `_SECTION_OVERRIDES` in `run_poc.py` | Edit `_SECTION_OVERRIDES` or the bundle's `report_spec.json` |

## Layout (PoC)
```
poc/
  run_poc.py            <- pipeline entry point
  config.yaml           <- model names, temperature, paths
  requirements.txt
  .env.example
  schemas/              <- output_schema.py (Pydantic) + requirements + hash
  prompts/              <- extraction_requirements.md, validation_rubric.md
  sample_input/  output/
  evals/                <- run_basic_eval.py
```

## Extension points
- **Add/replace a component:** update `components` + `workflow.steps` + `artifacts` in the blueprint, re-validate, regenerate.
- **Change the schema/fields:** edit `target_output_spec` (and `prompts/extraction_requirements.md`); the schema regenerates on the next run via the requirements hash.
- **Tune a component option:** set it in `workflow.steps[].parameters` (e.g. `enhanced_transcript`, `include_verification`, `hybrid_search`).

## Configuration
- **Model provider:** azure_openai
- **Model preferences:** generation_model: gpt-5.4, review_model: gpt-5.4, temperature: 1.0, reasoning_effort: medium
- **Integration targets:** _none_

## Tests and evaluation
- Evaluation requirements: test_fixture: fixtures/expected_report_results.json, required_facts: ['F01', 'F02', 'F03', 'F04', 'F05', 'F06', 'F07', 'F08', 'F09', 'F10'], acceptance_policy: {'semantic_matching': True, 'numeric_values_must_be_correct': True, 'required_citation_format': '[source_file]', 'extra_unsupported_claims_are_failures': True}, prohibited_behavior: ['Do not invent actions, owners, deadlines, suppliers, or external market facts', 'Do not silently use EUR 410,000 as the exact Nordic spend', 'Do not claim the report is manager-approved; the PoC produces a draft for review']
- See `evals/` for the basic evaluation script and `evaluation_plan.md` for the full plan.

**agentic extra required:** `agentic=True` depends on LangGraph. Install `gaik[multi-source-report-generator-agentic]` in addition to `gaik[multi-source-report-generator]`. Both are in `requirements.txt`.

**strict_review raises on unresolved edits:** if the reviewer model cannot repair a section after retries, the run raises before writing any output. To debug, temporarily set `strict_review=False` and inspect the raw draft.

**Path resolution is bundle-relative:** all source paths, `report_spec`, and `sample_report` are resolved relative to the directory that contains the bundle JSON. Moving the bundle requires updating the paths inside it.

**evidence_index.json written by the module:** when `include_evidence_index=True`, the module writes `evidence_index.json` to `output_dir`. `run_poc.py` includes a fallback that serialises `result.evidence_items` manually in case the module path changes in a future GAIK version.

**Duplicate-heading deduplication:** the `fix_duplicate_headings()` function in `run_poc.py` post-processes the report to remove headings that appear twice consecutively (a side-effect of `sample_report_path` already containing section headings). This is a code-level fix recorded in blueprint v1.1; do not remove it.

**Section instruction overrides:** `_SECTION_OVERRIDES` in `run_poc.py` patches section instructions after loading from `report_spec.json`. Currently restricts `[source_file]` citations to the Action column in the actions table. To update, edit `_SECTION_OVERRIDES` and update the corresponding `target_output_spec.fields` in the blueprint.

**reasoning_effort forwarded to Azure OpenAI:** passed inside `writer_options` and `review_options`. If the deployed model does not support this parameter, the API ignores it. Remove from the dicts if it causes unexpected behaviour.

**No extraction schema:** this pipeline has no Extractor step. The `schemas/` directory and `prompts/extraction_requirements.md` generated by the scaffolder are placeholders and are not used at runtime.
