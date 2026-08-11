# Technical Specification — Purchase Order ERP Record Extraction

> Generated from `use_case.blueprint.json`. Source of truth is the blueprint; regenerate after any change.

## Overview
Extract structured header and line-item data from customer purchase order PDFs and produce reviewer-verified ERP-compatible JSON records.

- **Use-case id:** `po_erp_extraction`
- **Domain:** manufacturing / procurement
- **Primary language:** en
- **Runtime interface:** web_application

## Inputs and outputs
- **Input types:** pdf
- **Input formats:** native_pdf, scanned_pdf
- **Output types:** structured_json
- **Data sources:** customer_purchase_orders

## Selected components
- **VisionExtractor** (component) — selected over `DocumentsToStructuredData` because inputs include scanned PDFs and accuracy-critical complex layouts (multi-page tables, merged headers, split rows). Sends full page images to a vision LLM in a single pass. Non-default options: `include_verification=True` (per-field confidence scores and reasons, required by the reviewer workflow), `merge_table=True` (table cell data merged for better row/column fidelity), `additional_instructions` (domain rules: leading-zero preservation, DD/MM/YYYY date format, `product_form` enum enforcement, no hallucination).
- **LLMJudge** (component) — added because `human_review=yes`; pre-screens extracted JSON for hallucinated or internally inconsistent field values before the record reaches the reviewer, reducing reviewer burden on low-quality extractions.

## Workflow
| Step | Type | Component | Inputs | Outputs |
|------|------|-----------|--------|---------|
| upload_po | user_task | — | — | source_pdf |
| extract_po_fields | automated_task | VisionExtractor <br/>opts: task=Extract a structured ERP purchase order record from the PDF, capturing header fields (purchase_order_number, delivery_date, delivery_address, vendor_number) and all line items (item_number, article_code, dimensions, material_grade, quantity, product_form, and optional material specification fields). Handle multi-page tables, merged headers, and rows split across pages., schema_ref=schemas/output_schema.py, requirements_ref=schemas/output_schema_requirements.json, include_verification=True, merge_table=True, additional_instructions=Preserve all alphanumeric identifiers — article codes, item numbers, vendor numbers, and product codes — exactly as written in the document, including leading zeros. Do not reformat, normalise, or truncate them. Delivery dates must be captured in DD/MM/YYYY format. The product_form field must be one of exactly: Flat, round, rectangular bar. Do not merge distinct line items. When a table row is continued on the next page, capture all continued rows as separate line items. Do not invent or infer any value not explicitly present in the source document. | source_pdf | extracted_po_json |
| validate_extraction | automated_task | LLMJudge | extracted_po_json | validation_report |
| notify_reviewer | automated_task | — | extracted_po_json, validation_report, source_pdf | — |
| reviewer_review | human_review | — | extracted_po_json, validation_report, source_pdf | approved_po_json |
| notify_employee | automated_task | — | — | — |
| employee_correct | user_task | — | extracted_po_json, source_pdf | — |

### Artifacts
- `source_pdf` — pdf, source: user_upload
- `extracted_po_json` — structured_json, source: generated
- `validation_report` — validation_report, source: generated
- `approved_po_json` — structured_json, source: generated (final output)

## Output schema
- **Schema name:** PurchaseOrderERPRecord
- **Field count:** 19
- **Required fields:** purchase_order_number, delivery_date, delivery_address, vendor_number, line_items, item_number, article_code, dimensions, material_grade, quantity, product_form
- **Missing-value policy:** Optional fields: set to null when absent. Required fields: flag for human review when missing or uncertain.

**Fields:**
- purchase_order_number
- delivery_date
- delivery_address
- vendor_number
- line_items
- item_number
- article_code
- dimensions
- material_grade
- quantity
- product_form
- standard_designation
- cut_length
- temper_or_condition
- hardness_hv
- min_bend_radius
- delivery_length_note
- applicable_standard
- special_flags

**Validation rules:**
- delivery_date must match DD/MM/YYYY format
- product_form must be one of: Flat, round, rectangular bar
- Do not invent or infer values not present in the source document
- Preserve all alphanumeric identifiers exactly, including leading zeros
- Do not merge distinct line items

## Model configuration
- **Model provider:** azure_openai
- **Model preferences:** extraction_model: gpt-5.4, temperature: 0.0

## Runtime and integration assumptions
- **Integration targets:** downloadable_json_file
- **Human review:** yes

## Security and governance
- **Security constraints:** POs contain internal commercial information and customer/supplier identifiers. External model APIs are permitted. Local-only processing is not required.
- **Contains personal data:** yes
- **Output sensitivity:** medium
- **Audit log required:** no

## Evaluation method
metrics: ['field_exact_match', 'confidence_score_distribution', 'required_field_coverage'], confidence_scores: True, confidence_score_range: 0.0 to 1.0, confidence_reasons: True, flag_uncertain_required_fields: True, test_data: sample PDF available in fixture
