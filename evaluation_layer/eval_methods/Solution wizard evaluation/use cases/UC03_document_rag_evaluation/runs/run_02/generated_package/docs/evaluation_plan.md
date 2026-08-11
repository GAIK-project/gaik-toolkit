# Evaluation Plan — Manufacturing Internal Knowledge Assistant

> How the quality of this solution is measured. Generated from the blueprint.

## Goal
Demonstrate: Demonstrate role-aware citation-grounded Q&A over three PDFs with access_manifest.json and query_set.json from the supplied input bundle. Prove correct access control (deny management-confidential content to general employees), accurate [filename, page] citations, and graceful not-found response when no authorized content supports the query. Pass all four role-tagged queries (Q01-Q04) with exact expected access decisions and citation pairs.

Success criteria:
- Employees find reliable answers faster than manual search
- Answers are verifiable through document citations
- Employees never receive content outside their authorized role
- System correctly refuses to answer from unauthorized content

## Stated evaluation requirements
Four role-tagged queries (Q01-Q04) with exact expected access decisions, answer content, and citation pairs. Q01 (employee, Helsinki hotel limit): access=allowed, EUR 180/night + Finance Director approval, cite [employee_travel_policy.pdf, 3]. Q02 (employee, MX-200 filter): access=allowed, 250h inspection + 1000h or 1.8bar replacement, cite [mx200_maintenance_manual.pdf, 3] and [mx200_maintenance_manual.pdf, 4]. Q03 (employee, Project Aurora ceiling): access=denied, empty citations, no 12%/22%/CFO details. Q04 (manager, Project Aurora ceiling and approver): access=allowed, 12% ceiling + CFO written approval, cite [project_aurora_pricing_strategy.pdf, 3].

The primary metrics for this PoC are:

| Metric | What it measures |
|---|---|
| **Access-control correctness** | `access_decision` matches expected value for all 4 queries (binary pass/fail per query) |
| **Citation accuracy** | Each citation in an allowed answer matches the expected `[file_name, page_number]` pair exactly |
| **Answer groundedness** | Key facts (EUR 180, 250 h, 1 000 h, 1.8 bar, 12%) are present verbatim in the answer text |
| **Refusal correctness** | Denied answers contain no restricted facts (12%, 22%, CFO) and include a non-empty `refusal_reason` |

## Recommended metrics
- **Output type:** structured_json (schema: `RAGAnswerRecord`)
- For structured extraction, use the GAIK `extraction_eval` framework (field-level Precision / Recall / F1, hallucination rate) via `ExtractionEvaluator`.
- For RAG / answers, use `RAG_eval` (faithfulness, answer relevance, context precision/recall) via `RAGEvaluator`.
- For transcription, use `transcription_eval`; for translation, `translation_eval`; for report writing, `report_writing_eval`.

Use the **`RAG_eval`** framework (`RAGEvaluator`) for faithfulness and answer-relevance scoring on Q01, Q02, and Q04 (the three allowed queries). Access-control and citation-format checks are deterministic assertions, not LLM-judge metrics — implement them as exact-match rules in `evals/run_basic_eval.py`.

## Test data
- **Data sources:** local_file_bundle
- Place ground-truth examples under `evals/ground_truth/` and predictions under `evals/predictions/`.

**4 labelled queries** (Q01–Q04) supplied in `poc_input/query_set.json`. Ground truth is established by the use-case specification: expected `access_decision`, required citation pairs, and required factual values are fixed and documented in the blueprint (`evaluation.test_queries`). Place the ground-truth records (one JSON object per query with `expected_access_decision`, `expected_citations`, and `key_facts`) in `evals/ground_truth/` before running the evaluator.

## Thresholds and acceptance
- access_decision must be 'allowed' or 'denied'
- Allowed factual answers require at least one citation
- Each citation must be a two-element list [string file_name, integer page_number] with 1-based page number
- Denied answers require refusal_reason, empty citations list, and must not reveal restricted content
- Do not answer from model memory when authorized evidence is absent

| Metric | Pass threshold |
|---|---|
| Access-control correctness | 4/4 queries correct (100% — any RBAC failure is a hard fail) |
| Citation accuracy | All expected citations present; no extra citations from restricted docs |
| Answer groundedness | All key numeric values present verbatim in Q01, Q02, Q04 answers |
| Refusal correctness | Q03 answer contains none of: `12`, `22`, `Chief Financial Officer`, `CFO`; `refusal_reason` is non-empty |

No numerical RAG-quality thresholds (faithfulness score, MRR) were specified for the PoC. These can be added once a baseline is established in Gate 3.

## Human review
- **Required:** no
- **Reviewers:** _none_

## Limitations
- **Small sample:** 4 queries cover the RBAC boundary conditions but do not test retrieval quality across the full range of possible questions. Expand the query set before drawing conclusions about general accuracy.
- **No numerical RAG thresholds:** Faithfulness and answer-relevance scores are not yet baselined; the PoC uses exact-match assertions only.
- **Synthetic documents:** The three PDFs are purpose-built for this evaluation; results may not generalise to the full production document library, which may have more complex layouts, longer documents, or conflicting information across files.
- **Single-run evaluation:** The Chroma store is rebuilt on every run; vector-search results can vary slightly with model updates or embedding-model changes. Pin the embedding deployment name and model version to ensure reproducibility.
