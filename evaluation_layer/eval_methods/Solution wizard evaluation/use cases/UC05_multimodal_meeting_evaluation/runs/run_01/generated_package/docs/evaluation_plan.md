# Evaluation Plan — AI-Assisted Meeting Record Generator

> How the quality of this solution is measured. Generated from the blueprint.

## Goal
Demonstrate: Process fixtures/poc_input_bundle.json (referencing the meeting WAV, agenda PDF, and participant JSON) via a CLI accepting --input <bundle_path>. The run must exit successfully and save non-empty, parseable JSON to poc/output/ capturing the frozen meeting decisions, actions, unresolved issues, and the known date conflict, with audio citations as file_name|start_timestamp|end_timestamp (HH:MM:SS) and agenda citations as file_name|page_number. Unsupported owners, dates, budget approval, and SSO decisions must be left unset, and review_status must be pending_review. Output is compared semantically against fixtures/expected_meeting_record.json.

Success criteria:
- Supported decisions and actions are captured accurately with evidence; missing owners, dates, or decisions are not invented.

## Stated evaluation requirements
CLI run must exit successfully and save non-empty, parseable JSON to poc/output/. Compare output semantically against fixtures/expected_meeting_record.json, focusing on correctness of decisions, actions, unresolved issues, conflicts, and citation validity/format.

Concrete metrics used against the frozen fixture bundle:
1. **Run success** — exit code 0, `output/meeting_record.json` exists, is non-empty, and parses as JSON.
2. **Scalar field match** — `meeting_id`, `title`, `meeting_date`, `start_time`, `end_time`, `review_status` compared exactly against `expected_meeting_record.json`.
3. **Collection semantic match** — `decisions`, `action_items`, `unresolved_issues`, `conflicts` compared by count and by content overlap (paraphrased wording is acceptable; a different owner, due date, or missing fact is not).
4. **Citation validity** — every citation matches `file_name|start|end` (audio, `HH:MM:SS`) or `file_name|page` (agenda); every decision/action/unresolved-issue/conflict has at least one.
5. **Non-invention check** — every claim in the fixture's `must_not_assert` list must be absent from the output (e.g. no asserted budget approval, no asserted SSO decision, no owner/date on the FAQ action, no October-15 start date).

## Recommended metrics
- **Output type:** structured_json (schema: `MeetingRecord`)
- For structured extraction, use the GAIK `extraction_eval` framework (field-level Precision / Recall / F1, hallucination rate) via `ExtractionEvaluator`.
- ~~For RAG / answers, use `RAG_eval`~~ -- not applicable, this pipeline does not do retrieval/Q&A.
- ~~For transcription/translation/report-writing eval~~ -- not applicable; transcription is an intermediate artifact here, not the deliverable, and the output is structured JSON, not a narrative report.
- Applicable framework: **`extraction_eval`** only, run via `ExtractionEvaluator` against the frozen fixture bundle (`fixtures/poc_input_bundle.json` + `fixtures/expected_meeting_record.json`).

## Test data
- **Data sources:** Per-meeting bundle (fixtures/poc_input_bundle.json) referencing one WAV recording, one PDF agenda, and one JSON participant list. No live system integration in this PoC.
- Place ground-truth examples under `evals/ground_truth/` and predictions under `evals/predictions/`.

There is currently **one** frozen scenario (`UC05`, `fixtures/`): a synthetic meeting (`project_nimbus_meeting.wav`, `project_nimbus_agenda.pdf`, `project_nimbus_participants.json`) generated from a written scenario script, with a hand-authored `expected_meeting_record.json` (ground truth), an evaluator-only `reference_transcript.json`, and a `must_not_assert` list of claims the output must never make. This single scenario was used to validate the PoC during scaffolding (see Results below) but is not a statistically representative sample -- before production use, add real (or additional synthetic) meetings covering multiple speakers, languages if applicable, ambiguous or missing owners/dates, and agenda/transcript conflicts.

## Thresholds and acceptance
- Every decision, action_item, unresolved_issue, and conflict must carry at least one citation.
- Audio citations use a single string: file_name|start_timestamp|end_timestamp, with HH:MM:SS timestamps.
- Agenda citations use a single string: file_name|page_number.
- An agenda item alone is not a decision -- only the spoken meeting content determines what was actually decided.
- When the agenda and spoken content conflict, record the conflict and follow the explicit spoken decision.
- review_status starts as 'pending_review'.

Pass/fail thresholds for this PoC stage:
- Run success: must exit 0 and write non-empty, parseable JSON -- hard gate.
- Scalar fields (`meeting_id`, `title`, `meeting_date`, `start_time`, `end_time`, `review_status`): exact match required.
- `participants`: exact match on `{name, role}` set (case-insensitive on role wording).
- `decisions` / `action_items` / `unresolved_issues` / `conflicts`: count must match; each item's core facts (owner, due_date, statement content) must match semantically -- paraphrasing is acceptable, a different fact is not.
- Citations: 100% of decision/action/unresolved-issue/conflict entries must carry at least one syntactically valid citation -- hard gate (schema-enforceable minimum is 0 today; see `assumption` re: enforcing `min_length=1` if this regresses).
- Non-invention: 0 tolerance on `must_not_assert` violations -- any single violation fails the run regardless of other scores.
- On the current single scenario, the PoC met all of the above (see the Results note below); this does not yet establish a statistical threshold (e.g. F1 across many meetings) -- add one once more scenarios exist.

## Human review
- **Required:** yes
- **Reviewers:** project_manager

## Limitations
- Only one ground-truth scenario exists (`UC05`); results on it do not guarantee generalization to real meetings with different speaker counts, accents, audio quality, or agenda structures.
- `discussion_summary` and decision/issue/conflict `description` fields are free-text summaries -- "correctness" there is inherently semantic/subjective, not exact-match; human review remains the final gate for these.
- LLMJudge's hallucination flags are noisy for this use case: it does not know the pipeline's own normalization rule (participant-list name correction) or its own-time-overrides-scheduled-time rule, and flags both as suspect. Treat its report as an aid for the reviewer, not a pass/fail signal, until the judge prompt can be made aware of these rules.
- No adversarial or edge-case scenarios (e.g. multiple conflicting dates, no decisions at all, heavily overlapping speakers) have been evaluated yet.
