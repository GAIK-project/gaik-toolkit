# Evaluation Plan — AI-Supported Meeting Record Generation

> How the quality of this solution is measured. Generated from the blueprint.

## Goal
Demonstrate: Process a fixed input bundle (meeting WAV + agenda PDF + participant JSON, referenced by a bundle manifest) via a CLI invoked as `python run_poc.py --input <bundle_path>`. The PoC must exit successfully and save a non-empty, schema-valid JSON meeting record to poc/output/. The output must capture the frozen meeting decisions, actions, unresolved issues, and the agenda/meeting date conflict; cite audio evidence as 'file_name|start_timestamp|end_timestamp' (HH:MM:SS) and agenda evidence as 'file_name|page_number'; leave unsupported owners, dates, budget approval, and the SSO decision unset (null) with an uncertainty_reason; and set review_status to 'pending_review'. The output is compared semantically against a fixture expected_meeting_record.json. The web application, authentication, external system integrations, and operational scaling are out of scope for this first PoC.

Success criteria:
- Decisions and actions that are actually supported by the meeting (or, for context, the agenda) are captured accurately with evidence citations; owners, dates, approvals, or decisions that were not explicitly stated are never invented.

## Stated evaluation requirements
Compare the generated meeting_record.json semantically against fixtures/expected_meeting_record.json (decisions, actions, unresolved issues, conflicts). Validate every citation string against the required pipe-delimited pattern (file_name|start_timestamp|end_timestamp with HH:MM:SS for audio; file_name|page_number for the agenda). Confirm none of the fixture's must_not_assert statements are asserted by the output (hallucination check).

Concretely, this becomes three checks run by `evals/run_basic_eval.py`:
1. **Citation format validity** — every `citations[]` string in `decisions`, `action_items`, `unresolved_issues`, and `conflicts` matches `file_name|HH:MM:SS|HH:MM:SS` (audio) or `file_name|page_number` (agenda).
2. **Structural completeness** — all 12 top-level fields present, `review_status == "pending_review"`, and every list item has at least one citation.
3. **Semantic comparison against a ground-truth record** — top-level scalar fields and per-container item counts compared to a fixture; a `must_not_assert` keyword-overlap heuristic flags (not hard-fails) possible hallucinated claims for manual review.

## Recommended metrics
- **Output type:** structured_json (schema: `MeetingRecord`)
- For structured extraction, use the GAIK `extraction_eval` framework (field-level Precision / Recall / F1, hallucination rate) via `ExtractionEvaluator`.
- For RAG / answers, use `RAG_eval` (faithfulness, answer relevance, context precision/recall) via `RAGEvaluator`.
- For transcription, use `transcription_eval`; for translation, `translation_eval`; for report writing, `report_writing_eval`.

This use case is structured extraction, so the applicable framework is **`extraction_eval`** (field-level Precision/Recall/F1 plus hallucination rate via `ExtractionEvaluator`/`LLMJudge`). The `RAG_eval`, `transcription_eval`, `translation_eval`, and `report_writing_eval` frameworks do not apply — there is no retrieval step, and the deliverable is a structured record, not a plain transcript, translation, or narrative report.

## Test data
- **Data sources:** meeting_audio_recording, agenda_document, participant_list_json
- Place ground-truth examples under `evals/ground_truth/` and predictions under `evals/predictions/`.

For this first PoC there is exactly one worked example: a synthetic meeting (audio + agenda + participant list) with a hand-authored ground-truth record and an explicit `must_not_assert` list of forbidden claims (e.g. an unapproved budget figure, an unselected SSO approach). Ground truth was established by construction — the synthetic recording's script is the source of truth for what was actually said, so every expected decision/action/issue/conflict is traceable to a specific line of that script. Before broader rollout, this should grow to a handful of real (or realistically messy) meetings covering: a meeting with no conflicts, a meeting with multiple simultaneous action owners, and a meeting where the agenda and the discussion diverge on more than one point.

## Thresholds and acceptance
- Every decision, action_item, unresolved_issue, and conflict must include at least one citation. Citations are pipe-delimited strings: 'file_name|start_timestamp|end_timestamp' (HH:MM:SS) for audio, or 'file_name|page_number' for the agenda document. review_status must equal 'pending_review' in the PoC output.

- **Citation coverage:** 100% — every decision/action_item/unresolved_issue/conflict must have ≥1 well-formed citation; any violation is a hard fail.
- **Structural completeness:** 100% — all 12 top-level fields present and `review_status == "pending_review"`; any violation is a hard fail.
- **Field/count match against ground truth:** target ≥90% on the flat scalar fields (meeting_id, title, meeting_date, start_time, end_time, review_status) plus per-container item counts; below that, treat as a regression worth investigating even though item-count differences (e.g. topic segmentation) are not automatically wrong.
- **must_not_assert heuristic flags:** any flag is a prompt for manual review, not an automatic fail — the check is a keyword-overlap heuristic and can false-positive on correctly-worded negations (e.g. "no budget was approved" still shares keywords with the forbidden claim "the budget was approved").

## Human review
- **Required:** yes
- **Reviewers:** project_manager

## Limitations
- Only one worked (synthetic) example exists today; metrics are not yet statistically meaningful across a real meeting population.
- The `must_not_assert` check in `run_basic_eval.py` is a keyword-overlap heuristic, not a semantic judge — it can both miss genuine hallucinations phrased without the forbidden keywords and false-positive on correct negations. A true semantic diff should use `LLMJudge`'s text-pair comparison or the full `evaluation_layer/eval_methods/extraction_eval/evaluate.py`.
- `discussion_summary`/topic segmentation is inherently subjective — the model may group the same spoken content into a different number/shape of topics than a human would, without that being a factual error. Evaluation should treat topic-count mismatches as informational, not a hard failure.
- Expected value (time saved, etc.) has not been quantified, so there is currently no way to measure business-impact ROI alongside extraction quality — see `assumption_001`.
