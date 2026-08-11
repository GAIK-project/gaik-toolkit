# Evaluation Plan — Purchase Order ERP Record Extraction

> How the quality of this solution is measured. Generated from the blueprint.

## Goal
Demonstrate: Given a supplied sample purchase-order PDF, extract the required header fields and all three line items into an ERP-compatible JSON record via a CLI interface. The PoC must accept the PDF, exit successfully, generate a non-empty parseable JSON record, preserve identifiers/leading zeros/article codes/dates/quantities/dimensions/units, and must not invent unsupported values for missing optional fields. Compare result semantically with fixtures/expected_erp_record.json. Out of scope: live ERP connection, PDF report, customer-specific format evaluation, numerical accuracy threshold.

Success criteria:
- Faster and more consistent ERP data preparation
- Fewer manual transcription and omission errors
- Reviewer-verifiable record produced before any ERP transfer

## Stated evaluation requirements
method: semantic comparison with fixtures/expected_erp_record.json, metrics: ['field_exact_match', 'semantic_match', 'completeness'], numerical_accuracy_threshold: not_specified

Concrete metrics for the PoC evaluation: **field exact-match rate** (extracted value equals expected value character-for-character, after whitespace normalisation) and **completeness rate** (required fields present and non-null). Semantic matching is applied to free-text fields (`delivery_address`, `special_flags`) where minor rewording is acceptable. The evaluation compares `poc/output/result.json` against `fixtures/expected_erp_record.json` using the built-in comparison in `run_poc.py` and the GAIK `extraction_eval` framework for batch runs.

## Recommended metrics
- **Output type:** structured_json (schema: `PurchaseOrderERPRecord`)
- For structured extraction, use the GAIK `extraction_eval` framework (field-level Precision / Recall / F1, hallucination rate) via `ExtractionEvaluator`.
- For RAG / answers, use `RAG_eval` (faithfulness, answer relevance, context precision/recall) via `RAGEvaluator`.
- For transcription, use `transcription_eval`; for translation, `translation_eval`; for report writing, `report_writing_eval`.

Applicable framework: **`extraction_eval`** (GAIK `ExtractionEvaluator`) — field-level precision, recall, F1, and hallucination rate for structured JSON output.

## Test data
- **Data sources:** customer_purchase_order_pdfs
- Place ground-truth examples under `evals/ground_truth/` and predictions under `evals/predictions/`.

**PoC stage:** one supplied sample purchase order PDF; ground truth is `fixtures/expected_erp_record.json`, which must be created manually by inspecting the PDF and recording the expected field values. A minimum of 3–5 diverse POs (different customers, layouts, and product types) is recommended for meaningful accuracy measurement beyond the single-sample PoC. Ground truth is established by expert review of each PO document, not by automated means.

## Thresholds and acceptance
- delivery_date must be in DD/MM/YYYY format
- product_form must be one of: Flat, round, rectangular bar
- item_number must preserve leading zeros as four-digit string
- article_code must preserve case and punctuation exactly
- vendor_number must preserve leading zeros
- Optional fields must be null (not empty string) when not present in the document
- Must not invent or hallucinate values for fields not present in the document

No numerical accuracy threshold was specified for this PoC. The pass criteria are qualitative: (1) all required header fields and all three line items are present and non-empty; (2) `product_form` is a valid enum value; (3) identifiers, leading zeros, article codes, and units are preserved exactly; (4) absent optional fields are `null`; (5) no values are invented for fields not in the document; (6) `delivery_date` is in DD/MM/YYYY format. Production-grade thresholds (e.g. field F1 ≥ 0.95 on required fields, hallucination rate = 0) should be defined when moving beyond the PoC.

## Human review
- **Required:** yes
- **Reviewers:** procurement_reviewer, order_processing_reviewer

## Limitations
- No ground truth file exists yet — `fixtures/expected_erp_record.json` must be created manually before any automated comparison can run.
- The PoC uses a single sample document; results may not generalise across all customer PO formats or layouts.
- LLMJudge grounding is unavailable for fully scanned PDFs (no text layer); hallucination detection relies on the human reviewer in those cases.
- No numerical accuracy threshold is defined for this PoC stage; all pass/fail decisions are qualitative reviewer judgements.
