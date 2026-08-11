# User Guide — Purchase Order ERP Record Extraction

> How to run the solution, provide input, inspect output, and adjust settings.

## What this does
Extract structured header and line-item data from customer purchase order PDFs and produce an ERP-compatible JSON record for reviewer-verified entry.

This proof of concept demonstrates: Given a supplied sample purchase-order PDF, extract the required header fields and all three line items into an ERP-compatible JSON record via a CLI interface. The PoC must accept the PDF, exit successfully, generate a non-empty parseable JSON record, preserve identifiers/leading zeros/article codes/dates/quantities/dimensions/units, and must not invent unsupported values for missing optional fields. Compare result semantically with fixtures/expected_erp_record.json. Out of scope: live ERP connection, PDF report, customer-specific format evaluation, numerical accuracy threshold.

## Prerequisites
- Python 3.11+
- Install dependencies: `pip install -r poc/requirements.txt`
- Copy `poc/.env.example` to `poc/.env` and fill in your model-provider credentials (provider: azure_openai).

## Providing input
- **Expected input:** pdf (formats: digital_pdf, scanned_pdf)
- Place your input file(s) in `poc/sample_input/`.

Place a single purchase order PDF named anything (e.g. `purchase_order.pdf`) in `poc/sample_input/`. Both digital (native-text) PDFs and scanned PDF attachments are supported. Alternatively, supply the path directly with `python poc/run_poc.py --input /path/to/purchase_order.pdf`. Multi-page documents, complex tables, merged headers, and rows split across pages are all handled.

## Running
```bash
python poc/run_poc.py
```

## Inspecting the output
- Results are written to `poc/output/`.
- The output is structured_json following the `PurchaseOrderERPRecord` schema.
- **Human review:** yes

A correct `poc/output/result.json` will contain a single JSON object with four header fields (`purchase_order_number`, `delivery_date` in DD/MM/YYYY, `delivery_address`, `vendor_number`) and a `line_items` list with one entry per PO row. Check that: (1) all required fields are present and non-empty; (2) `product_form` is exactly `Flat`, `round`, or `rectangular bar`; (3) leading zeros in `item_number`, `article_code`, and `vendor_number` are preserved exactly as in the PDF; (4) absent optional fields appear as `null` (not empty string or `"N/A"`); (5) `delivery_date` is in DD/MM/YYYY format. If `poc/output/validation.json` lists hallucination flags, review those fields against the source PDF before approving.

## Adjusting settings
| To change... | Edit... |
|--------------|---------|
| What is extracted / the fields | `poc/prompts/extraction_requirements.md` then re-run (schema regenerates) |
| Output structure | `poc/schemas/output_schema.py` |
| Model / temperature | `poc/config.yaml` |

## Privacy note
Personal data: unknown · output sensitivity: internal. Handle outputs accordingly.
