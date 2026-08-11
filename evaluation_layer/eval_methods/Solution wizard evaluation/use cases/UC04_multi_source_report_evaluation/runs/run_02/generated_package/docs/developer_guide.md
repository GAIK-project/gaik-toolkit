# Developer Guide — Quarterly Supplier Performance Report Generator

> Package structure, extension points, component configuration, tests, and evaluation.

## Architecture
This use case is driven by an **executable JSON blueprint** (`use_case.blueprint.json`) — the single source of truth. The PoC, the visual workflows (`workflow.mmd`, `workflow.bpmn`), and these docs are all *generated from it*. To change behaviour, edit the blueprint and regenerate; never hand-edit generated artifacts.

## Pipeline
| Step | Type | Component | Inputs | Outputs |
|------|------|-----------|--------|---------|
| upload_sources | user_task | — | — | kpi_spreadsheet, quality_audit_pdf, meeting_notes_md, incident_log_csv |
| generate_report | automated_task | MultiSourceReportGenerator <br/>opts: agentic=True, parser_choice=auto, strict_review=True, include_source_references=True, include_evidence_index=True, report_language=English, report_title=Q2 2026 Supplier Performance Report, output_docx=False, curate_evidence=False, polish=False, verbose=True, writer_options={'model': 'gpt-5.4', 'temperature': 1.0, 'reasoning_effort': 'medium'}, review_options={'model': 'gpt-5.4', 'temperature': 1.0, 'reasoning_effort': 'medium'}, sample_report_path=report_template.md, sections=loaded_from_report_spec_json | kpi_spreadsheet, quality_audit_pdf, meeting_notes_md, incident_log_csv | report_draft_md, evidence_index_json |
| notify_reviewer | automated_task | — <br/>opts: note=Deliver output/report.md and output/evidence_index.json to the procurement manager. In PoC: console message confirming output files written. | report_draft_md, evidence_index_json | — |
| manager_review | human_review | — <br/>opts: decision=approve_or_return, rejection_outcome=return to analyst for rework and regeneration | report_draft_md, evidence_index_json | approved_report_md |

### Components and their options
- **MultiSourceReportGenerator** (module) — Pattern is multi_source_report. The module subsumes all parsing (xlsx, pdf, md, csv), synthesis, and report-writing steps end-to-end. No separate parser, transcriber, or extractor steps are required.

**MultiSourceReportGenerator** is constructed with `use_azure=True` (from `config.yaml: use_azure: true`). All LLM parameters are read from `config.yaml` (`models.extraction`, `models.temperature`, `models.reasoning_effort`) and passed as `writer_options` and `review_options` dicts — change model or temperature there without touching `run_poc.py`. The `sections` list is loaded at runtime from `poc_input/report_spec.json` inside the bundle — edit that file to change section titles, instructions, or `depends_on` relationships. The `sample_report_path` is resolved from the bundle's `sample_report` key — replace `report_template.md` to impose a different heading structure.

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
- **Model preferences:** model: gpt-5.4, temperature: 1.0, reasoning_effort: medium
- **Integration targets:** _none_

## Tests and evaluation
- Evaluation requirements: semantic_match_to_fixtures: fixtures/expected_report_results.json, required_sections: 6, required_source_file_coverage: 4, required_kpi_values: Overall 299/91.6%/26550/2.0%/867000; Nordic 135/85.2%/13500/3.1%/405000; Baltic 97/96.9%/9700/1.0%/194000; Alpine 67/97.0%/3350/0.6%/268000
- See `evals/` for the basic evaluation script and `evaluation_plan.md` for the full plan.

**Agentic mode requires the langgraph extra** — `gaik[multi-source-report-generator-agentic]` must be installed (it is in `requirements.txt`); without it the module silently falls back to single-call mode and `strict_review` has no effect. **`strict_review=True`** will raise a `RuntimeError` before writing any output if the per-section reviewer still has unresolved edits after retries — this is intentional behaviour implementing the no-premature-release requirement; do not catch this silently. **`evidence_index.json`** is written by the module when `include_evidence_index=True`; if it is absent after a run, `run_poc.py` writes it explicitly from `result.evidence_items` as a fallback. **`reasoning_effort`** is passed in `writer_options` as a string (`'medium'`); if your Azure OpenAI deployment does not support this parameter it will be ignored without error — confirm availability for your specific deployment endpoint.
