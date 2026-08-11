# Evaluation Plan — Purchase Order ERP Record Extraction

> How the quality of this solution is measured. Generated from the blueprint.

## Goal
Demonstrate: Extract header and line-item fields from a sample purchase order PDF, produce structured JSON ready for reviewer verification, and confirm no fields are invented or garbled.

Success criteria:
- Faster and more consistent ERP data preparation
- Fewer manual transcription and omission errors
- Every record is reviewer-verified before ERP transfer

## Stated evaluation requirements
metrics: ['field_exact_match', 'confidence_score_distribution', 'required_field_coverage'], confidence_scores: True, confidence_score_range: 0.0 to 1.0, confidence_reasons: True, flag_uncertain_required_fields: True, test_data: sample PDF available in fixture

**Concrete metrics:**
- **Field exact match** — for each required field, the extracted value must match the ground-truth value character-for-character (including leading zeros, hyphens, and spacing). Computed per field and aggregated as Precision / Recall / F1 across all fields in the test set.
- **Required field coverage** — percentage of required fields (per header and per line item) that are non-null in the extraction. Target: 100% for clearly legible POs.
- **Confidence score distribution** — histogram of per-field confidence scores. Any required field with confidence < 0.7 should be flagged for reviewer attention.
- **Hallucination rate** — percentage of extracted field values not traceable to the source document, as reported by LLMJudge. Target: 0% hallucinated required fields.
- **`product_form` accuracy** — exact match rate against ground truth for the enum field. Null predictions (uncertain) are counted separately from wrong-enum predictions.

## Recommended metrics
- **Output type:** structured_json (schema: `PurchaseOrderERPRecord`)
- Use the GAIK `extraction_eval` framework (field-level Precision / Recall / F1, hallucination rate) via `ExtractionEvaluator`.

## Test data
- **Data sources:** customer_purchase_orders
- Place ground-truth examples under `evals/ground_truth/` and predictions under `evals/predictions/`.

For the PoC, a sample purchase order PDF is available in the fixture. Ground truth is established by manually transcribing the expected field values from the PDF into a reference JSON file with the same `PurchaseOrderERPRecord` structure. For a more robust evaluation set, collect 10–20 representative POs covering different customers, layouts, and edge cases (scanned vs. native, single-page vs. multi-page, POs with and without optional fields). Ground truth should be established by an experienced order-processing employee who is familiar with the ERP field definitions.

## Thresholds and acceptance

No numerical targets were specified by the stakeholders; the criteria below are recommended starting points for the PoC evaluation.

| Metric | Recommended threshold | Notes |
|---|---|---|
| Required-field exact match (F1) | ≥ 0.95 | Per required field across all test POs |
| Required field coverage (non-null rate) | 100% | For clearly legible POs; flag exceptions |
| Hallucination rate (required fields) | 0% | Any hallucinated required field is a blocker |
| `product_form` accuracy | ≥ 0.95 | Null predictions (uncertain) reviewed separately |
| Low-confidence required fields (< 0.7) | Flagged, not blocked | Routed to reviewer attention |
| `delivery_date` format compliance | 100% | Must be DD/MM/YYYY in the output |
| Leading-zero preservation | 100% | Spot-check article codes and PO numbers |

## Human review
- **Required:** yes
- **Reviewers:** procurement_reviewer, order_processing_reviewer

## Limitations
- **No ground truth yet:** the PoC ships with a single sample fixture PDF. Evaluation results on one document are indicative only; a meaningful F1 score requires at least 10–20 diverse POs with manually verified ground truth.
- **LLMJudge grounding limitation:** because VisionExtractor produces no intermediate text transcript, LLMJudge receives the extracted JSON (not the original page text) as its source. This means it can detect internal inconsistencies and obviously implausible values, but cannot verify values against the verbatim document text. The human reviewer with the original PDF remains the authoritative hallucination check.
- **`dimensions` and `material_grade` are free-text strings:** exact-match F1 may undercount correct extractions where the model copies a value in a slightly different format (e.g. `3×1500×3000` vs `3 x 1500 x 3000 mm`). Consider a normalised or semantic match mode for these fields when building a larger ground-truth set.
- **`product_form` subjectivity:** mapping a product description to one of three enum values requires interpretation. Edge cases (e.g. a flat bar vs. a rectangular bar) may require clarification of the mapping rules before ground truth can be established consistently.
