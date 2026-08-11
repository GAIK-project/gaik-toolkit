# User Guide — Purchase Order ERP Record Extraction

> How to run the solution, provide input, inspect output, and adjust settings.

## What this does
Extract structured header and line-item data from customer purchase order PDFs and produce reviewer-verified ERP-compatible JSON records.

This proof of concept demonstrates: Extract header and line-item fields from a sample purchase order PDF, produce structured JSON ready for reviewer verification, and confirm no fields are invented or garbled.

## Prerequisites
- Python 3.11+
- Install dependencies: `pip install -r poc/requirements.txt`
- Copy `poc/.env.example` to `poc/.env` and fill in your model-provider credentials (provider: azure_openai).

## Providing input
- **Expected input:** pdf (formats: native_pdf, scanned_pdf)
- Place your input file(s) in `poc/sample_input/`.

Place one PDF file in `poc/sample_input/` — any filename ending in `.pdf` is accepted (e.g. `purchase_order.pdf`). The file may be a native digital PDF or a scanned PDF. Multi-page documents are supported. If multiple PDFs are present the pipeline processes the first one alphabetically; to process a specific file, ensure it is the only PDF in the directory.

## Running
```bash
cd poc
python run_poc.py
```

## Inspecting the output
- Results are written to `poc/output/`.
- The output is structured_json following the `PurchaseOrderERPRecord` schema.
- **Human review:** yes

`poc/output/result.json` contains the extracted `PurchaseOrderERPRecord` — a JSON object with header fields (`purchase_order_number`, `delivery_date`, `delivery_address`, `vendor_number`) and a `line_items` array. Each line item carries required fields (article code, dimensions, material grade, quantity, product form) and any optional fields found in the document (standard designation, temper, hardness, etc.). Optional fields absent from the PO are `null`. If VisionExtractor's `include_verification` mode is active, each field also carries a `confidence` score (0–1) and a short `reason` string.

`poc/output/validation.json` contains the LLMJudge hallucination report: a list of flagged fields with severity and reason, and a top-level `passed` boolean.

**How to review:** open `result.json` alongside the original PDF. For each field, check:
- Required fields (`purchase_order_number`, `delivery_date`, `delivery_address`, `vendor_number`; per line: `item_number`, `article_code`, `dimensions`, `material_grade`, `quantity`, `product_form`) are present and match the document exactly — pay particular attention to leading zeros on codes and the date format (DD/MM/YYYY).
- Any field flagged in `validation.json` or showing low confidence warrants direct comparison with the source PDF.
- `product_form` must be exactly `Flat`, `round`, or `rectangular bar`; a `null` value means the form could not be determined and must be filled in manually before ERP entry.

## Adjusting settings
| To change... | Edit... |
|--------------|---------|
| What is extracted / the fields | `poc/prompts/extraction_requirements.md` then re-run (schema regenerates) |
| Output structure | `poc/schemas/output_schema.py` |
| Model / temperature | `poc/config.yaml` |

## Privacy note
Personal data: yes · output sensitivity: medium. Handle outputs accordingly.
