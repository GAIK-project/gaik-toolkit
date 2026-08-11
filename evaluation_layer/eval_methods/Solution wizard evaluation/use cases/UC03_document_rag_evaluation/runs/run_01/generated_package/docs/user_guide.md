# User Guide — Manufacturing Knowledge Base RAG Assistant

> How to run the solution, provide input, inspect output, and adjust settings.

## What this does
Role-aware question-answering assistant that retrieves cited answers from internal manufacturing policies, equipment manuals, and management documents, with pre-retrieval RBAC to enforce document access boundaries.

This proof of concept demonstrates: Demonstrate role-aware, citation-grounded question answering over three PDF documents using a local vector store and trusted role metadata. CLI: python run_poc.py --input <path-to-poc_input_bundle.json>. Execute all four role-tagged queries (Q01-Q04) and save non-empty parseable JSON results to output/results.json.

## Prerequisites
- Python 3.11+
- Install dependencies: `pip install -r poc/requirements.txt`
- Copy `poc/.env.example` to `poc/.env` and fill in your model-provider credentials (provider: azure_openai).

## Providing input
- **Expected input:** pdf, json (formats: PDF (text-based, 1-based page numbers), JSON (access_manifest, query_set, poc_input_bundle))

Pass the path to `poc_input_bundle.json` via the `--input` flag. The pipeline resolves all other files — `access_manifest.json`, `query_set.json`, and the three PDFs — automatically relative to the bundle file. No files need to be placed in `sample_input/` for this use case.

```bash
python poc/run_poc.py --input C:\Users\h02317\Downloads\runs\run_01\wizard_input\poc_input_bundle.json
```

## Running
```bash
python poc/run_poc.py --input <path-to-poc_input_bundle.json>
```

## Inspecting the output
Results are written to `poc/output/results.json` as a JSON array of `RAGAnswerRecord` objects, one per query. **Human review:** no.

A correct run produces exactly four records. Check each one as follows:

| Query | `access_decision` | `citations` | Key facts to look for |
|---|---|---|---|
| Q01 | `allowed` | `[["employee_travel_policy.pdf", 3]]` | EUR 180/night; Finance Director approval when exceeded |
| Q02 | `allowed` | includes pages 3 and 4 of `mx200_maintenance_manual.pdf` | 250 operating hours inspection; 1,000 h or 1.8 bar replacement |
| Q03 | `denied` | `[]` (empty) | No mention of 12%, 22%, or CFO in the answer text |
| Q04 | `allowed` | `[["project_aurora_pricing_strategy.pdf", 3]]` | 12% ceiling; written CFO approval |

If `citations` is non-empty on a denied record, or the answer for Q03 mentions restricted values, the RBAC logic needs investigation.

## Adjusting settings
| To change... | Edit... |
|--------------|---------|
| What is extracted / the fields | `poc/prompts/extraction_requirements.md` then re-run (schema regenerates) |
| Output structure | `poc/schemas/output_schema.py` |
| Model / temperature | `poc/config.yaml` |

## Privacy note
Personal data: false · output sensitivity: mixed. Handle outputs accordingly.
