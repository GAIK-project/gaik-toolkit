# User Guide — Manufacturing Internal Knowledge Assistant

> How to run the solution, provide input, inspect output, and adjust settings.

## What this does
Role-aware RAG assistant that answers employee questions over internal manufacturing policies, equipment manuals, and management documents with citations and enforced role-based access control.

This proof of concept demonstrates: Demonstrate role-aware citation-grounded Q&A over three PDFs with access_manifest.json and query_set.json from the supplied input bundle. Prove correct access control (deny management-confidential content to general employees), accurate [filename, page] citations, and graceful not-found response when no authorized content supports the query. Pass all four role-tagged queries (Q01-Q04) with exact expected access decisions and citation pairs.

## Prerequisites
- Python 3.11+
- Install dependencies: `pip install -r poc/requirements.txt`
- Copy `poc/.env.example` to `poc/.env` and fill in your model-provider credentials (provider: azure_openai).

## Providing input
- **Expected input:** pdf, document_collection, text (formats: pdf, json)
- Place your input file(s) in `poc/sample_input/`.

The pipeline is driven by a single **input bundle file**: `poc_input_bundle.json`. Pass its path with `--input`. The bundle references three other artefacts that must sit alongside it (all paths resolved relative to the bundle):

| Referenced path | File | Required |
|---|---|---|
| `poc_input/documents/` | `employee_travel_policy.pdf`, `mx200_maintenance_manual.pdf`, `project_aurora_pricing_strategy.pdf` | Yes — text-based PDFs |
| `poc_input/access_manifest.json` | Document-to-role mapping (`allowed_roles` per document) | Yes |
| `poc_input/query_set.json` | List of queries with `query_id`, `role`, and `question` | Yes |

Roles accepted in `query_set.json`: `"employee"` or `"manager"`. Role is trusted metadata — never inferred from question text.

## Running
```bash
python poc/run_poc.py
```

## Inspecting the output
- Results are written to `poc/output/`.
- The output is structured_json following the `RAGAnswerRecord` schema.
- **Human review:** no

A correct `output/results.json` is a non-empty JSON array with one `RAGAnswerRecord` object per query. To check a result:

1. **Structural check** — parse the JSON; confirm it is an array and each item has `query_id`, `role`, `question`, `access_decision`, `answer`, `citations`, and (where applicable) `refusal_reason`.
2. **Access-control check** — Q03 (`role=employee`, Project Aurora) must have `access_decision="denied"`, an empty `citations` list, and no mention of `12%`, `22%`, or `Chief Financial Officer` in the `answer` or `refusal_reason`.
3. **Citation check** — Q01, Q02, Q04 must have `access_decision="allowed"` and at least one citation. Each citation must be a two-element list `[string, integer]`, e.g. `["employee_travel_policy.pdf", 3]`. Page numbers are 1-based integers.
4. **Factual-value check** — Q01 answer should contain `EUR 180`; Q02 should contain `250` (operating hours) and either `1000` or `1,000`; Q04 should contain `12` (percent) and reference CFO approval.

## Adjusting settings
| To change... | Edit... |
|--------------|---------|
| What is extracted / the fields | `poc/prompts/extraction_requirements.md` then re-run (schema regenerates) |
| Output structure | `poc/schemas/output_schema.py` |
| Model / temperature | `poc/config.yaml` |

## Privacy note
Personal data: unknown · output sensitivity: high. Handle outputs accordingly.
