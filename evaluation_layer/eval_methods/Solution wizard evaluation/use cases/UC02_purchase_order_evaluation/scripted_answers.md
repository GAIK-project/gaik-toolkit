# UC02 scripted answers

Use the initial prompt verbatim. Provide an answer below only when the wizard asks about that topic. Do not volunteer future answers. At every routine confirmation, answer **Yes. Proceed without changes.**

## SA01: Business Context And Stakeholders

**Use when asked:** Who uses or reviews the solution, what is the current process, what problem should be solved, or who else is involved?

Order-processing employees are the intended users. Today they inspect customer purchase orders and manually enter header and line-item information into the ERP system. A procurement or order-processing reviewer verifies the generated record before transfer. The expected value is faster, more consistent order entry with fewer transcription and omission errors. Customers are external document senders, but they do not use the PoC.

## SA02: Document Inputs Layout And Language

**Use when asked:** What documents, formats, layouts, languages, data sources, or document-quality conditions must be supported?

Inputs are customer purchase orders received as PDF files or scanned PDF email attachments. The documents are in English and may contain complex multi-page tables, merged or hierarchical headers, rows split across pages, notes inside table areas, and alphanumeric product identifiers. JSON keys are English and extracted text remains as written in the document.

## SA03: Erp Schema Fields And Types

**Use when asked:** What schema, fields, field types, required or optional fields, formats, or allowed values should the ERP record use?

Use the schema name PurchaseOrderERPRecord with a parent_with_nested_list structure. Required header fields are purchase_order_number (string), delivery_date (string in DD/MM/YYYY), delivery_address (string), vendor_number (string), and line_items (list). Every line item requires item_number, article_code, dimensions, material_grade, and quantity as strings. product_form is required and must be Flat, round, or rectangular bar. Optional line-item fields are standard_designation, cut_length, temper_or_condition, hardness_hv (number), min_bend_radius (number), delivery_length_note, applicable_standard, and special_flags. Missing optional values remain null.

## SA04: Uncertainty Confidence And Review Evidence

**Use when asked:** How should missing, ambiguous, low-confidence, or uncertain information be represented, and what evidence should the reviewer receive?

Do not infer or fabricate unstated values. Missing optional values remain null. Missing or uncertain required values must be flagged for human review. Include field-level confidence scores from 0 to 1 and short confidence reasons when the selected component supports them. The reviewer must receive the structured record, confidence or uncertainty information, and the original purchase-order PDF so the value can be checked against its source.

## SA05: Review Workflow Integration And Exceptions

**Use when asked:** How will employees interact with the system, how are purchase orders submitted, what happens after extraction, who reviews or approves the output, what happens after rejection, and how is the result provided or transferred to ERP?

Order-processing employees will interact with the system through a web application. The application will allow employees to upload one or more purchase-order PDFs. The system processes each purchase order and presents the extracted structured record together with the original PDF and confidence or uncertainty information. An internal procurement or order-processing reviewer can check and correct the extracted values and then approve the record or return it for correction. When the reviewer returns a record, the order-processing employee is notified and receives the reviewer’s comments. The employee can correct the extracted values or upload a corrected purchase order and then resubmit the record. The extraction and review cycle repeats until the reviewer approves the record. A returned record is not automatically discarded.
The application provides the resulting ERP-compatible record as a downloadable JSON file for each purchase order. Only approved data may proceed to ERP. A direct ERP API connection and automatic database write are outside the current scope. The customer is only the external sender of the purchase order.

## SA06: Privacy Security Storage And Audit

**Use when asked:** What privacy, security, access, storage, retention, audit, or data-residency requirements apply?

Purchase orders contain internal commercial information and customer or supplier identifiers. External model APIs are allowed and local-only processing is not required. The PoC must not create a retained duplicate of the input after processing; the original remains in the source document system. The approved JSON and review decision may be retained, but no exact retention period is specified. Authentication, production role-based access control, production ERP credentials, and a full audit-log implementation are outside PoC scope.

## SA07: Interface Outputs And Poc Evaluation

**Use when asked:** What should the first proof-of-concept demonstrate, what interface or output format should it use, what test data should it process, or what acceptance criteria should apply?

The first PoC should demonstrate that, given the supplied sample purchase-order PDF, it can extract the required header fields and all three line items into an ERP-compatible JSON record. A command-line interface is sufficient. The PoC must accept the supplied PDF, exit successfully, and generate a non-empty parseable JSON record. It must preserve identifiers, leading zeros, article codes, dates, quantities, dimensions, and units, and it must not invent unsupported values for missing optional fields. Compare the result semantically with fixtures/expected_erp_record.json. A live ERP connection, formatted report, customer-specific format evaluation, and numerical accuracy threshold are outside the scope of this first PoC.

## SA08: Provider Model Scale And Budget

**Use when asked:** Which provider, exact model, temperature, reasoning effort, deployment topology, SLA, throughput, volume, or budget should be used?

Provider= Azure OpenAI, model=gpt-5.4, temperature=0.0, reasoning effort=medium. No deployment topology, SLA, throughput, volume, or budget is specified. A valid implementation default is acceptable, but it must not be presented as a user-confirmed requirement.

## SA09: Business Success Value And Risks

**Use when asked:** What does business success mean, is there a quantified value target, and what risks should be considered?

Business success means faster and more consistent ERP data preparation, fewer manual transcription or omission errors, and a reviewer-verifiable record before transfer. No numerical time-saving, accuracy, or cost-saving target is specified. The main risks are losing table structure, merging different line items, missing a row continued across pages, altering product codes or leading zeros, dropping units, inventing missing values, and transferring an unreviewed record.

## SA10: Domain Vocabulary And Identifiers

**Use when asked:** What controlled values, domain terms, units, abbreviations, identifiers, or formatting conventions occur?

Purchase orders contain four-digit item numbers, case-sensitive article codes, vendor numbers, material grades, standards, dimensions, quantities with units, and dates. Preserve leading zeros, punctuation, letter case, and units exactly. Normalize delivery dates to DD/MM/YYYY. product_form is restricted to Flat, round, or rectangular bar. No separate domain glossary is supplied.

## SA11: Validation Rules

**Use when asked:** What validation rules or special extraction instructions should apply to the generated ERP record?

The five required header keys and all required line-item keys must exist. There must be exactly as many line items as the source document contains. Preserve item and article identifiers exactly, including leading zeros. Keep quantity and dimensions with their units. Use DD/MM/YYYY for dates and only the allowed product_form values. Values must be grounded in the source document. Missing optional values remain null, and missing or uncertain required values are flagged for review.

## Unexpected question

Not specified for this evaluation. If a value is required, record it as an explicit assumption for user confirmation.

## Recovery

Only after attempt 0 fails, return the recorded execution evidence to the wizard. Permit at most three sequential refinements and stop at first successful execution. Recovery does not change EQ4.
