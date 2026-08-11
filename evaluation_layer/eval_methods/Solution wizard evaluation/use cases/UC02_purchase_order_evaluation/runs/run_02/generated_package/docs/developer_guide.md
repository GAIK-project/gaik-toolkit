# Developer Guide — Purchase Order ERP Record Extraction

> Package structure, extension points, component configuration, tests, and evaluation.

## Architecture
This use case is driven by an **executable JSON blueprint** (`use_case.blueprint.json`) — the single source of truth. The PoC, the visual workflows (`workflow.mmd`, `workflow.bpmn`), and these docs are all *generated from it*. To change behaviour, edit the blueprint and regenerate; never hand-edit generated artifacts.

## Pipeline
| Step | Type | Component | Inputs | Outputs |
|------|------|-----------|--------|---------|
| upload_po | user_task | — | — | source_pdf |
| extract_po_fields | automated_task | VisionExtractor <br/>opts: task=Extract purchase order header fields (PO number, delivery date, delivery address, vendor number) and all line items from the document into an ERP-compatible structured record., schema_ref=schemas/output_schema.py, requirements_ref=schemas/output_schema_requirements.json, include_verification=True, merge_table=True, model_provider=openai, additional_instructions=Preserve all leading zeros in item numbers, article codes, and vendor numbers exactly as printed. Article codes are case-sensitive — do not normalize case or punctuation. Normalize all dates to DD/MM/YYYY format. product_form must be exactly one of: Flat, round, rectangular bar. For absent optional fields output null, never an empty string. Merge line-item rows split across page breaks into a single entry. | source_pdf | erp_record_json |
| validate_extraction | automated_task | LLMJudge <br/>opts: model_provider=azure | erp_record_json | validation_report |
| notify_reviewer | automated_task | — | erp_record_json, validation_report | — |
| reviewer_approves | human_review | — | erp_record_json, validation_report | — |

### Components and their options
- **VisionExtractor** (component)
- **LLMJudge** (component)

**VisionExtractor** — constructed in `poc/run_poc.py` with `model_provider="openai"`, `use_azure=True` (reads `use_azure` from `config.yaml`), `include_verification=True`, `merge_table=True`, and `additional_instructions` encoding the domain preservation rules. The `extract()` call passes `extraction_model` and `requirements` loaded by `_load_output_schema()` from `poc/schemas/output_schema.py` and `poc/schemas/output_schema_requirements.json`. If the requirements hash changes, the schema is regenerated automatically on the next run.

**LLMJudge** — constructed with `model_provider="azure"`, `use_azure=True`. Receives `source_text` (PDF text layer extracted via PyMuPDF) and `extracted_fields` (the VisionExtractor output dict). For scanned PDFs where PyMuPDF returns no text, the judge block is skipped gracefully and a notice is printed. The judge report is written to `poc/output/validation.json`.

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
- **Integration targets:** _none_

## Tests and evaluation
- Evaluation requirements: method: semantic comparison with fixtures/expected_erp_record.json, metrics: ['field_exact_match', 'semantic_match', 'completeness'], numerical_accuracy_threshold: not_specified
- See `evals/` for the basic evaluation script and `evaluation_plan.md` for the full plan.

**VisionExtractor gotchas:**
- The wizard pre-generates `output_schema.py` and `output_schema_requirements.json`. These file names are fixed conventions — do not rename them. VisionExtractor's `schema_dir` convention uses `schema.py`/`requirements.json`, so the PoC loads the schema manually via `_load_output_schema()` and passes it as `extraction_model` + `requirements` to `extract()`.
- The `product_form` field uses `Literal['Flat', 'round', 'rectangular bar']` without an empty-string default — this was explicitly corrected from the SchemaGenerator output. Do not add an empty string back or Azure OpenAI structured output may return an empty value that bypasses validation.
- For Azure OpenAI structured output, `output_schema.py` must never contain bare `dict` or `list[dict]` field types. The `line_items` field uses the named sub-model `purchase_order_erp_record_line_item_Extraction` (with `extra='forbid'`) to satisfy the `additionalProperties: false` constraint.
- `merge_table=True` is important for POs with tables split across pages. Do not disable it without testing on multi-page documents.

**LLMJudge gotchas:**
- LLMJudge hallucination detection requires `source_text` (the document's text layer). For fully scanned PDFs, PyMuPDF returns an empty string and the judge is skipped. This is expected behaviour — the human reviewer acts as the safety net in that case.
- If `gaik[llm-judge]` is not installed, the judge block is skipped with an ImportError notice (not a fatal error). Ensure `pip install -r requirements.txt` is run to include it.
