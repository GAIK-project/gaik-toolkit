# Developer Guide — Purchase Order ERP Record Extraction

> Package structure, extension points, component configuration, tests, and evaluation.

## Architecture
This use case is driven by an **executable JSON blueprint** (`use_case.blueprint.json`) — the single source of truth. The PoC, the visual workflows (`workflow.mmd`, `workflow.bpmn`), and these docs are all *generated from it*. To change behaviour, edit the blueprint and regenerate; never hand-edit generated artifacts.

## Pipeline
| Step | Type | Component | Inputs | Outputs |
|------|------|-----------|--------|---------|
| upload_po | user_task | — | — | source_pdf |
| extract_po_fields | automated_task | VisionExtractor <br/>opts: task=Extract a structured ERP purchase order record from the PDF, capturing header fields (purchase_order_number, delivery_date, delivery_address, vendor_number) and all line items (item_number, article_code, dimensions, material_grade, quantity, product_form, and optional material specification fields). Handle multi-page tables, merged headers, and rows split across pages., schema_ref=schemas/output_schema.py, requirements_ref=schemas/output_schema_requirements.json, include_verification=True, merge_table=True, additional_instructions=Preserve all alphanumeric identifiers — article codes, item numbers, vendor numbers, and product codes — exactly as written in the document, including leading zeros. Do not reformat, normalise, or truncate them. Delivery dates must be captured in DD/MM/YYYY format. The product_form field must be one of exactly: Flat, round, rectangular bar. Do not merge distinct line items. When a table row is continued on the next page, capture all continued rows as separate line items. Do not invent or infer any value not explicitly present in the source document. | source_pdf | extracted_po_json |
| validate_extraction | automated_task | LLMJudge | extracted_po_json | validation_report |
| notify_reviewer | automated_task | — | extracted_po_json, validation_report, source_pdf | — |
| reviewer_review | human_review | — | extracted_po_json, validation_report, source_pdf | approved_po_json |
| notify_employee | automated_task | — | — | — |
| employee_correct | user_task | — | extracted_po_json, source_pdf | — |

### Components and their options

**VisionExtractor** — constructed in `run_poc.py` with:
- `model_provider="openai"`, `use_azure=use_azure` (from `config.yaml`: `use_azure: true`, `provider: azure_openai`)
- `include_verification=True` — enables per-field confidence scores (0–1) and short reason strings; required by the reviewer workflow
- `merge_table=True` — merges table cell data into extraction context for better row/column fidelity on complex PO tables
- `additional_instructions` — hardcoded string in `run_poc.py` enforcing leading-zero preservation, DD/MM/YYYY date format, `product_form` enum, no-merge-rows, and no-hallucination rules
- Extraction prompt loaded from `poc/prompts/extraction_requirements.md` and passed as `user_requirements`

**LLMJudge** — constructed in the validation block of `run_poc.py` with:
- `model_provider="openai"`, `use_azure=use_azure`
- Receives `extracted_fields` (the extracted JSON dict) and `source_text` (JSON serialisation of the extraction, used for internal consistency checks since no plain-text transcript is available for vision-based extraction)
- Writes `poc/output/validation.json` with hallucination flags and a `passed` boolean

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
- **Model preferences:** extraction_model: gpt-5.4, temperature: 0.0
- **Integration targets:** downloadable_json_file

## Tests and evaluation
- Evaluation requirements: metrics: ['field_exact_match', 'confidence_score_distribution', 'required_field_coverage'], confidence_scores: True, confidence_score_range: 0.0 to 1.0, confidence_reasons: True, flag_uncertain_required_fields: True, test_data: sample PDF available in fixture
- See `evals/` for the basic evaluation script and `evaluation_plan.md` for the full plan.

**Gotchas for future developers:**
- **Azure OpenAI structured output constraint:** all Pydantic models in `output_schema.py` must have `model_config = ConfigDict(extra='forbid')` and must not use bare `dict` or `list[dict]` field types. The `LineItem` sub-model already satisfies this; if you add nested fields, always define a named sub-model.
- **`product_form` Literal:** the schema uses `Literal['Flat', 'round', 'rectangular bar'] | None`. A `null` value is intentional (uncertain/missing → flag for reviewer). Do not add an empty-string fallback — that would allow blank values to pass schema validation.
- **LLMJudge source_text limitation:** VisionExtractor has no text-transcript output, so `source_text` is set to the JSON serialisation of the extraction. This means LLMJudge performs internal consistency checks only, not full grounding against the document text. The human reviewer with the original PDF is the authoritative check.
- **Schema regeneration:** `_load_output_schema()` in `run_poc.py` checks `output_schema.hash` against a SHA-256 of `extraction_requirements.md`. If the prompt changes, the schema regenerates automatically on the next run. If you edit `output_schema.py` directly (as was done for the `product_form` Literal fix), update `output_schema.hash` or delete it to prevent a stale-hash false-positive causing unwanted regeneration.
- **Multi-page PO handling:** `merge_table=True` and the `additional_instructions` string instruct the model to combine rows split across pages. If you see duplicate line items for continued rows, check whether the PO layout changes (e.g. different column widths or page numbers inside the table) confuse the table merger.
