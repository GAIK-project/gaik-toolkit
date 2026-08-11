# Evaluation Plan — Maintenance Fault Reporting via Finnish Voice

> How the quality of this solution is measured. Generated from the blueprint.

## Goal
Demonstrate: Accept a supplied Finnish audio fixture, exit successfully, produce a non-empty parseable JSON maintenance ticket, preserve the fixture facts, include all required fields (location, fault_description, urgency), and leave unsupported or unknown values null rather than inventing them.

Success criteria:
- Faster incident reporting with fewer missing details
- Supervisor can verify and approve each ticket before it enters the maintenance system

## Stated evaluation requirements
metrics: ['json_parse_success', 'required_field_coverage', 'semantic_fixture_fact_matching', 'unsupported_value_introduction'], threshold: no numerical threshold specified for single-fixture PoC, test_data: single supplied Finnish audio fixture

| Metric | Description |
|---|---|
| **json_parse_success** | The output file can be loaded with `json.loads()` without error and matches the `MaintenanceTicket` Pydantic schema. |
| **required_field_coverage** | `location`, `fault_description`, and `urgency` are present as keys in the output JSON; each is either a non-null value or appears in `uncertain_fields`. |
| **semantic_fixture_fact_matching** | Every non-null field value in the output is semantically traceable to a fact stated in the transcript (evaluated by LLMJudge `detect_hallucinations`). |
| **unsupported_value_introduction** | `urgency` is strictly one of `"low"`, `"medium"`, `"high"`; no other string value appears; `observation_date` matches `YYYY-MM-DD` when present; `observation_time` matches `HH:MM` when present. |

## Recommended metrics
- **Output type:** structured_json (schema: `MaintenanceTicket`)
- For structured extraction, use the GAIK `extraction_eval` framework (field-level Precision / Recall / F1, hallucination rate) via `ExtractionEvaluator`.
- For RAG / answers, use `RAG_eval` (faithfulness, answer relevance, context precision/recall) via `RAGEvaluator`.
- For transcription, use `transcription_eval`; for translation, `translation_eval`; for report writing, `report_writing_eval`.

Use the **`extraction_eval`** framework via `ExtractionEvaluator` (field-level Precision / Recall / F1, hallucination rate). For transcription quality assessment run `transcription_eval` separately if a reference transcript is available.

## Test data
- **Data sources:** mobile_app_voice_recording
- Place ground-truth examples under `evals/ground_truth/` and predictions under `evals/predictions/`.

The PoC uses a **single Finnish audio fixture** supplied by the project team. Ground truth is a hand-authored JSON file stored in `evals/ground_truth/` with the same field names as `MaintenanceTicket`. Ground truth is established by a team member listening to the recording and recording the expected field values; the `uncertain_fields` list in the ground truth captures any fields the evaluator judges as genuinely inaudible or ambiguous. For a production evaluation set, aim for ≥ 20 diverse recordings covering all urgency levels, multiple reporters, and edge cases (missing fields, background noise, non-standard asset identifiers).

## Thresholds and acceptance
- urgency must be one of: low, medium, high — never any other string
- observation_date must be YYYY-MM-DD format when present
- observation_time must be HH:MM format when present
- required fields (location, fault_description, urgency) must be present in the JSON; a null value is acceptable only when the field name is also listed in uncertain_fields

No numerical thresholds are specified for this single-fixture PoC. The acceptance criteria are binary:
- **json_parse_success:** must be `true` (hard fail if the output cannot be parsed).
- **required_field_coverage:** all three required fields must be present in the JSON (hard fail if any is absent entirely).
- **semantic_fixture_fact_matching:** LLMJudge `hallucination_flags` should be empty; any flag is a soft warning requiring supervisor review.
- **unsupported_value_introduction:** `urgency` must be one of the three allowed values; any violation is a hard fail.

For a production threshold, recommend: required-field F1 ≥ 0.95; urgency accuracy ≥ 0.98; zero unsupported enum values over a 20-fixture test set.

## Human review
- **Required:** yes
- **Reviewers:** supervisor

## Limitations
- **Single fixture only:** conclusions from one recording cannot be generalised. Finnish transcription quality varies significantly with background noise, speaker accent, and recording device.
- **No numerical ground truth yet:** the PoC pass/fail criteria are structural (parse, field presence, enum validity). Semantic accuracy against ground-truth values requires a hand-authored reference file that does not yet exist.
- **Subjective fields:** `fault_description` and `actions_taken` are free-text; exact-match F1 will understate quality. Semantic similarity scoring (e.g. cosine distance on embeddings) or LLM-judge evaluation is needed for fair assessment of these fields.
- **LLMJudge bias:** the judge uses the same Azure OpenAI provider as the extractor. Shared-model hallucination (the model fabricating and then endorsing the same value) is a known risk; a second-opinion judge from a different provider is recommended before production use.
