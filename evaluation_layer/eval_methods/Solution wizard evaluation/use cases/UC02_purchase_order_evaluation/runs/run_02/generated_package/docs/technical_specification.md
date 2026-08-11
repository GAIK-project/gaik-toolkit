# Technical Specification — Purchase Order ERP Record Extraction

> Generated from `use_case.blueprint.json`. Source of truth is the blueprint; regenerate after any change.

## Overview
Extract structured header and line-item data from customer purchase order PDFs and produce an ERP-compatible JSON record for reviewer-verified entry.

- **Use-case id:** `purchase_order_erp_record`
- **Domain:** manufacturing / order processing
- **Primary language:** en
- **Runtime interface:** cli

## Inputs and outputs
- **Input types:** pdf
- **Input formats:** digital_pdf, scanned_pdf
- **Output types:** structured_json
- **Data sources:** customer_purchase_order_pdfs

## Selected components
- **VisionExtractor** (component)
- **LLMJudge** (component)

- **VisionExtractor** — selected over `DocumentsToStructuredData` because inputs include scanned PDFs and complex multi-page tables with merged/hierarchical headers and cross-page rows; sends full visual page context to a vision LLM in a single pass for highest fidelity. Non-default options: `include_verification=True` (per-field confidence before human review), `merge_table=True` (tables split across pages), `additional_instructions` (domain rules: leading zeros, case-sensitive codes, DD/MM/YYYY, product_form enum, null for absent optional fields).
- **LLMJudge** — added because `human_review=yes`; pre-screens extracted record for hallucinated or unsupported values before the reviewer sees it. Non-default option: `model_provider="azure"` (Azure OpenAI, matching configured provider).

## Workflow
| Step | Type | Component | Inputs | Outputs |
|------|------|-----------|--------|---------|
| upload_po | user_task | — | — | source_pdf |
| extract_po_fields | automated_task | VisionExtractor <br/>opts: task=Extract purchase order header fields (PO number, delivery date, delivery address, vendor number) and all line items from the document into an ERP-compatible structured record., schema_ref=schemas/output_schema.py, requirements_ref=schemas/output_schema_requirements.json, include_verification=True, merge_table=True, model_provider=openai, additional_instructions=Preserve all leading zeros in item numbers, article codes, and vendor numbers exactly as printed. Article codes are case-sensitive — do not normalize case or punctuation. Normalize all dates to DD/MM/YYYY format. product_form must be exactly one of: Flat, round, rectangular bar. For absent optional fields output null, never an empty string. Merge line-item rows split across page breaks into a single entry. | source_pdf | erp_record_json |
| validate_extraction | automated_task | LLMJudge <br/>opts: model_provider=azure | erp_record_json | validation_report |
| notify_reviewer | automated_task | — | erp_record_json, validation_report | — |
| reviewer_approves | human_review | — | erp_record_json, validation_report | — |

### Artifacts
- `source_pdf` — pdf, source: user_upload
- `erp_record_json` — structured_json, source: generated (final output)
- `validation_report` — validation_report, source: generated

## Output schema
- **Schema name:** PurchaseOrderERPRecord
- **Field count:** 19
- **Required fields:** purchase_order_number, delivery_date, delivery_address, vendor_number, line_items, item_number, article_code, dimensions, material_grade, quantity, product_form
- **Missing-value policy:** null

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
- delivery_date must be in DD/MM/YYYY format
- product_form must be one of: Flat, round, rectangular bar
- item_number must preserve leading zeros as four-digit string
- article_code must preserve case and punctuation exactly
- vendor_number must preserve leading zeros
- Optional fields must be null (not empty string) when not present in the document
- Must not invent or hallucinate values for fields not present in the document

## Model configuration
- **Model provider:** azure_openai
- **Model preferences:** extraction_model: gpt-5.4, temperature: 0.0

## Runtime and integration assumptions
- **Integration targets:** _none_
- **Human review:** yes

## Security and governance
- **Security constraints:** PO content must not be retained after processing, Original remains in source document system, Approved JSON and review decision may be retained (no exact retention period specified), Authentication, RBAC, ERP credentials, and full audit-log implementation are out of PoC scope, External model APIs allowed; local-only processing not required
- **Contains personal data:** unknown
- **Output sensitivity:** internal
- **Audit log required:** no

## Evaluation method
method: semantic comparison with fixtures/expected_erp_record.json, metrics: ['field_exact_match', 'semantic_match', 'completeness'], numerical_accuracy_threshold: not_specified
