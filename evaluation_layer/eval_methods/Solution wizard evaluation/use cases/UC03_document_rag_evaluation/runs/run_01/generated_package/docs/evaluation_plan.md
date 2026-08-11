# Evaluation Plan — Manufacturing Knowledge Base RAG Assistant

> How the quality of this solution is measured. Generated from the blueprint.

## Goal
Demonstrate: Demonstrate role-aware, citation-grounded question answering over three PDF documents using a local vector store and trusted role metadata. CLI: python run_poc.py --input <path-to-poc_input_bundle.json>. Execute all four role-tagged queries (Q01-Q04) and save non-empty parseable JSON results to output/results.json.

Success criteria:
- Q01 (employee, Helsinki hotel limit): answers EUR 180 per night with Finance Director approval required when exceeded, citing [employee_travel_policy.pdf, 3]
- Q02 (employee, MX-200 filter): answers inspection every 250 operating hours and replacement after 1,000 operating hours or 1.8 bar, citing mx200_maintenance_manual.pdf pages 3 and 4
- Q03 (employee, Project Aurora ceiling): access_decision=denied, empty citations list, no restricted facts disclosed
- Q04 (manager, Project Aurora ceiling and approver): answers 12 percent ceiling with written CFO approval required above the ceiling, citing [project_aurora_pricing_strategy.pdf, 3]
- All four results returned as separate non-empty parseable JSON objects in output/results.json

## Stated evaluation requirements
method: deterministic query testing, queries: ['Q01', 'Q02', 'Q03', 'Q04'], expected_outputs: defined in poc_input_bundle.json and query_set.json, numerical_threshold: not_specified, eval_framework: RAG_eval

The PoC is evaluated by running all four predefined queries and checking each `RAGAnswerRecord` against the expected outputs below. All four checks must pass; there is no numerical accuracy threshold beyond the pass/fail criteria stated in the blueprint.

| Query | Check | Pass condition |
|---|---|---|
| Q01 | access_decision | `allowed` |
| Q01 | answer content | contains "EUR 180" and "Finance Director" |
| Q01 | citations | includes `["employee_travel_policy.pdf", 3]` |
| Q02 | access_decision | `allowed` |
| Q02 | answer content | contains "250 operating hours" and ("1,000 operating hours" or "1000 operating hours") and "1.8 bar" |
| Q02 | citations | includes page 3 and page 4 of `mx200_maintenance_manual.pdf` |
| Q03 | access_decision | `denied` |
| Q03 | citations | `[]` (empty list) |
| Q03 | answer text | does NOT contain "12 percent", "12%", "22 percent", "22%", or "Chief Financial Officer" |
| Q03 | refusal_reason | non-null string |
| Q04 | access_decision | `allowed` |
| Q04 | answer content | contains "12 percent" (or "12%") and "Chief Financial Officer" (or "CFO") |
| Q04 | citations | includes `["project_aurora_pricing_strategy.pdf", 3]` |

## Recommended metrics
- **Output type:** structured_json (schema: `RAGAnswerRecord`)
- **Primary framework:** `RAG_eval` — faithfulness (answer grounded in retrieved context), answer relevance, and citation precision (citations map to actually retrieved chunks, not fabricated references). Use `RAGEvaluator` from the GAIK toolkit.
- **Access-control correctness:** binary pass/fail per query — did the system produce the correct `access_decision` and respect the denied-content rules?
- **Value preservation:** spot-check that exact quantities (EUR 180, 250 h, 1,000 h, 1.8 bar, 12%, 22%) appear verbatim in allowed answers.

## Test data
- **Data sources:** local file bundle resolved relative to poc_input_bundle.json at runtime
- Place ground-truth examples under `evals/ground_truth/` and predictions under `evals/predictions/`.

The PoC evaluation set consists of 4 queries (Q01–Q04) defined in `query_set.json` and `poc_input_bundle.json`. Expected outputs (correct access decision, answer content, and citation pairs) are specified in the blueprint's `success_criteria`. Ground truth was authored by the use-case owner and is not LLM-generated. No additional test set exists at this stage; expanding to a larger query set is recommended before production.

## Thresholds and acceptance
- access_decision must be 'allowed' or 'denied'
- citations must be an empty list when access_decision=denied
- refusal_reason must be non-null when access_decision=denied
- each citation must be exactly [str, int] (filename, 1-based page number)
- answer must not reveal restricted content when access_decision=denied
- allowed factual answers must include at least one citation to a document permitted for that role
- exact values must be preserved: EUR 180, 250 operating hours, 1,000 operating hours, 1.8 bar, 12 percent, 22 percent

All 13 checks in the query-level table above must pass (4/4 queries). No partial pass is accepted for RBAC correctness — a single citation leaking into a denied record or restricted content appearing in an answer text is a failure. No numerical faithfulness threshold is specified for this first PoC; qualitative review of the answer text is sufficient.

## Human review
- **Required:** no
- **Reviewers:** _none_

## Limitations
- **Small sample:** 4 queries cover the critical RBAC and citation scenarios but do not constitute a statistically representative test set. Edge cases (ambiguous queries, cross-document answers, borderline similarity scores near the RBAC threshold) are not tested.
- **No adversarial queries:** The test set does not include prompt-injection attempts, queries designed to extract restricted content through indirect phrasing, or queries for which no document contains an answer.
- **LLM-judged faithfulness not implemented:** Citation validation is regex-based; answer faithfulness is not scored automatically in this PoC. Manual review of the answer text is required.
- **Static ground truth:** Expected outputs were authored ahead of running the pipeline; any paraphrase of the correct answer that differs in wording but not meaning may be flagged as incorrect by an automated string-match check.
