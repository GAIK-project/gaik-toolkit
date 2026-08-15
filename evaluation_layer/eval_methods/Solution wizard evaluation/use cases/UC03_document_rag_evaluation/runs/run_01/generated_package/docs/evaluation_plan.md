# Evaluation Plan — Manufacturing Knowledge Assistant

> How the quality of this solution is measured. Generated from the blueprint.

## Goal
Demonstrate: Demonstrate role-aware, citation-grounded question answering over three sample PDFs (employee travel policy, MX-200 maintenance manual, Project Aurora pricing strategy) using a supplied access manifest and query set. Run `python run_poc.py --input <path-to-poc_input_bundle.json>`, resolve the other supplied files relative to that bundle, execute the four role-tagged queries, and save non-empty parseable JSON results demonstrating correct access decisions and citations. Out of scope for this first PoC: a web interface, a live document-repository connector, enterprise sign-in/identity integration, a full audit-log service, and a numerical RAG-quality threshold.

Success criteria:
- Employees find reliable answers faster, can verify answers through citations, and never receive content outside their role. No numerical time-saving, accuracy, cost, or adoption target was specified.

## Stated evaluation requirements
Deterministic acceptance test using the four supplied role-tagged queries (Q01-Q04), checked against required facts, the exact access decision (allowed/denied), and required citation pairs per query. No numerical RAG-quality threshold (e.g. a fixed recall/precision score) was specified for the first PoC.

Concretely, `evals/run_basic_eval.py` checks each of the four queries against `evals/ground_truth/expected_results.json` on four axes: (1) `access_decision` matches exactly, (2) every `required_fact` string appears (case-insensitive) in `answer`, (3) no `forbidden_fact` appears anywhere in `answer`, and (4) every `required_citation` is present in `citations`. All four axes must pass for all four queries for the PoC to be considered accepted at this stage — there is no partial-credit threshold, since the acceptance criteria were given as exact per-query expectations rather than an aggregate score.

## Recommended metrics
- **Output type:** answer_with_citations, structured_json (schema: `RAGAnswerRecord`)
- This PoC's acceptance gate is the deterministic 4-query check above (`evals/run_basic_eval.py`), not a generic aggregate score.
- If broader RAG-quality measurement is wanted later (beyond these 4 fixture queries), GAIK's `RAGEvaluator` (faithfulness, answer relevance, context precision/recall) is the applicable framework — this was intentionally deferred, per assumption_004, since no numerical RAG-quality threshold was specified for the first PoC.

## Test data
- **Data sources:** PoC uses a local fixture bundle: three sample PDFs (employee_travel_policy.pdf, mx200_maintenance_manual.pdf, project_aurora_pricing_strategy.pdf) plus access_manifest.json and query_set.json, all resolved relative to poc_input_bundle.json. Connection to a live enterprise document repository is out of scope for this PoC.
- Test data is exactly 4 queries (`Q01`-`Q04`) across the 2 roles (`employee`, `manager`) supplied in `poc/sample_input/poc_input/query_set.json`. Ground truth (`evals/ground_truth/expected_results.json`) was authored by the wizard agent directly from the acceptance criteria the user stated in the requirements conversation — required facts, forbidden facts, and required citations per query — not from any external answer key.

## Thresholds and acceptance
- An allowed factual answer requires at least one citation to a document permitted for that role
- A denied answer requires an empty citations list, a non-null refusal_reason, and must not reveal restricted facts
- Each citation is a two-element list [file_name (str), page_number (1-based int)], in that order
- query_id and role must be preserved unchanged from the input query
- Cite every material factual claim using [file_name, page_number]
- Do not answer from model memory when authorized evidence is absent

Pass/fail is binary per query, per the four checks in `run_basic_eval.py`: all four queries must pass all four checks (`access_decision` match, required facts present, forbidden facts absent, required citations present) for the PoC to be accepted at Gate 3. There is no partial/aggregate threshold (e.g. no "3 of 4 queries correct is acceptable") because the source requirement specified exact expected behavior per query, not a statistical target.

## Human review
- **Required:** no
- **Reviewers:** _none_

## Limitations
- Only 4 queries across 3 documents are covered — this validates the RBAC and citation *mechanism*, not broad retrieval quality or recall across a larger, more varied corpus.
- `temperature=1.0` (as explicitly requested) introduces run-to-run variability in the exact wording of `answer`; the eval checks for required substrings rather than exact string match to tolerate this, but a failing run should be re-run once before treating it as a real regression.
- The "not found" vs "denied" classification (`NOT_FOUND_FLOOR` and the restricted-topic score comparison in `run_poc.py`) is a heuristic tuned against this fixture's score distribution and has not been validated against a larger, more diverse set of documents/roles.
- No numerical RAG-quality threshold (recall/precision/faithfulness score) was specified or is measured in this first PoC (assumption_004) — only the deterministic per-query acceptance check above.
