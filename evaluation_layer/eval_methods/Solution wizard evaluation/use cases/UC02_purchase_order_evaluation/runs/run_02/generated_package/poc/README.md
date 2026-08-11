# Purchase Order ERP Record Extraction — Proof of Concept

Extract structured header and line-item data from customer purchase order PDFs
and produce an ERP-compatible JSON record for reviewer-verified entry.

---

## What this PoC demonstrates

Given a supplied sample purchase-order PDF, the pipeline:

1. Sends the PDF to **VisionExtractor** (Azure OpenAI vision model) which reads the
   visual layout — including complex tables, merged headers, and rows split across
   pages — and extracts all header and line-item fields.
2. Runs **LLMJudge** to pre-screen the extracted record for hallucinated or
   unsupported values before the human reviewer sees it.
3. Writes the extracted record to `output/result.json` and the validation report
   to `output/validation.json`.
4. Performs a semantic field-by-field comparison against
   `fixtures/expected_erp_record.json` (if present).

Human review and ERP transfer are **out of PoC scope**; the reviewer examines the
saved JSON before any ERP entry is made.

---

## Prerequisites

- Python 3.11+
- GAIK toolkit: `pip install -r requirements.txt`
- Azure OpenAI credentials (see `.env.example`)

---

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up credentials
cp .env.example .env
# Edit .env and fill in: AZURE_API_KEY, AZURE_ENDPOINT, AZURE_DEPLOYMENT, AZURE_API_VERSION
```

---

## Running the PoC

```bash
# Place a purchase order PDF in sample_input/, then run:
python run_poc.py

# Or supply a path directly:
python run_poc.py --input path/to/purchase_order.pdf
```

Results are written to `output/`.

---

## Input

Place a customer purchase order PDF in `sample_input/`. The pipeline handles:
- Digital (native-text) PDFs
- Scanned PDF attachments
- Multi-page documents with complex tables, merged headers, and cross-page rows

---

## Expected output

`output/result.json` — ERP-compatible JSON record:

```json
{
  "purchase_order_number": "0045231",
  "delivery_date": "15/03/2025",
  "delivery_address": "Steelworks GmbH, Industriestrasse 12, 40210 Düsseldorf, Germany",
  "vendor_number": "00456",
  "line_items": [
    {
      "item_number": "0010",
      "article_code": "S355J2+N",
      "dimensions": "12x1500x3000 mm",
      "material_grade": "S355J2+N",
      "quantity": "10 pcs",
      "product_form": "Flat",
      "standard_designation": "EN 10025-2",
      "cut_length": null,
      "temper_or_condition": null,
      "hardness_hv": null,
      "min_bend_radius": null,
      "delivery_length_note": null,
      "applicable_standard": null,
      "special_flags": null
    }
  ]
}
```

`output/validation.json` — LLMJudge hallucination report (flags and pass/fail).

---

## Fixture comparison

Place `fixtures/expected_erp_record.json` (same structure as the output above)
to enable automatic semantic comparison at the end of each run.

---

## Adjusting the PoC

| What to change | Which file |
|---|---|
| Extraction field descriptions or rules | `prompts/extraction_requirements.md` |
| Model or temperature | `config.yaml` |
| Schema field types or enum values | `schemas/output_schema.py` |
| Evaluation metrics | `evals/run_basic_eval.py` |

---

## Running the basic evaluation

```bash
python evals/run_basic_eval.py
```

Requires ground-truth files in `evals/ground_truth/`. See the script for the
expected format.

---

## Next steps

- Review `output/result.json` — check that all header fields and line items are
  correct, identifiers are preserved, and optional absent fields are `null`.
- If `output/validation.json` shows flags, review the flagged fields.
- Paste or describe the output in the wizard chat to trigger Gate 3 (refinement).
