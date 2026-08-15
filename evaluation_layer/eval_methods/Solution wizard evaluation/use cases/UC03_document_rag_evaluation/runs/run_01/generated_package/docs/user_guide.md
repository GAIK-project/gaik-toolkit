# User Guide — Manufacturing Knowledge Assistant

> How to run the solution, provide input, inspect output, and adjust settings.

## What this does
Role-aware assistant that answers employee questions from internal policies, equipment manuals, and management documents with citations, enforcing role-based access control so restricted documents are never retrieved or disclosed to unauthorized employees.

This proof of concept demonstrates: Demonstrate role-aware, citation-grounded question answering over three sample PDFs (employee travel policy, MX-200 maintenance manual, Project Aurora pricing strategy) using a supplied access manifest and query set. Run `python run_poc.py --input <path-to-poc_input_bundle.json>`, resolve the other supplied files relative to that bundle, execute the four role-tagged queries, and save non-empty parseable JSON results demonstrating correct access decisions and citations. Out of scope for this first PoC: a web interface, a live document-repository connector, enterprise sign-in/identity integration, a full audit-log service, and a numerical RAG-quality threshold.

## Prerequisites
- Python 3.11+
- Install dependencies: `pip install -r poc/requirements.txt`
- Copy `poc/.env.example` to `poc/.env` and fill in your model-provider credentials (provider: azure_openai).

## Providing input
- **Expected input:** document_collection, pdf (formats: pdf (text-based, English), json (access manifest, query set, input bundle))
- Place your input file(s) in `poc/sample_input/`.

The pipeline expects a **bundle file** (`poc_input_bundle.json`) plus, resolved relative to it: a folder of text-based PDF documents, an `access_manifest.json` (one entry per document with `file`, `title`, `classification`, `allowed_roles`), and a `query_set.json` (a list of `{query_id, role, question}` objects). A ready-to-run sample bundle covering three documents (`employee_travel_policy.pdf`, `mx200_maintenance_manual.pdf`, `project_aurora_pricing_strategy.pdf`) and four role-tagged queries is already included under `poc/sample_input/`.

## Running
```bash
python poc/run_poc.py --input poc/sample_input/poc_input_bundle.json
```

## Inspecting the output
- Results are written to `poc/output/answer_records.json`.
- The output is answer_with_citations, structured_json following the `RAGAnswerRecord` schema.
- **Human review:** no

A correct output file is a JSON array with one record per input query, each with: `query_id`/`role`/`question` copied unchanged from the input, `access_decision` (`allowed` or `denied`), `answer` (the grounded answer, or a refusal/not-found message), `citations` (a list of `[file_name, page_number]` pairs — non-empty whenever `access_decision` is `allowed` and the answer states a fact), and `refusal_reason` (set whenever access was denied or nothing relevant was found, otherwise `null`). To check correctness: for `allowed` records, verify each cited `[file_name, page_number]` actually appears in that document and no restricted document is cited for an unauthorized role; for `denied` records, verify `citations` is empty and the `answer` contains no facts from the restricted document. Run `python poc/evals/run_basic_eval.py` for an automated pass/fail check against the four supplied queries.

## Adjusting settings
| To change... | Edit... |
|--------------|---------|
| Output fields / structure | `poc/schemas/output_schema.py` |
| Answer-generation prompt / grounding rules | `ANSWER_PROMPT` in `poc/run_poc.py` |
| Model / temperature / reasoning effort | `poc/config.yaml` |
| "Not found" similarity threshold | `NOT_FOUND_FLOOR` in `poc/run_poc.py` |

## Privacy note
Personal data: unknown · output sensitivity: high. Handle outputs accordingly.
