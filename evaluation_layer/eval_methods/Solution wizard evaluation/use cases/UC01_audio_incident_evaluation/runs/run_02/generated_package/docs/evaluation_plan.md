# Evaluation Plan — Finnish Voice Fault Reporting — Maintenance Ticket Generator

> How the quality of this solution is measured. Generated from the blueprint.

## Goal
Demonstrate: Accept a supplied Finnish audio fixture, exit successfully, produce a non-empty parseable JSON ticket with all required fields present (may be null/unknown if not stated but flagged in uncertain_fields), preserve fixture facts, and leave unsupported values null or unknown.

Success criteria:
- Faster incident reporting compared to manual entry
- Fewer missing details in submitted tickets
- Every ticket is supervisor-verifiable before transfer to the maintenance system

## Stated evaluation requirements
metrics: ['json_parsing', 'required_field_coverage', 'semantic_fixture_fact_matching', 'unsupported_value_introduction'], thresholds: none specified for single-fixture PoC, eval_framework: extraction_eval

The PoC is evaluated against four concrete checks on the single fixture run:

1. **JSON parsing** — the output file must be valid JSON and must parse without error.
2. **Required-field coverage** — `location`, `fault_description`, and `urgency` must all be present as keys in the output object (value may be `null` if not stated, but the key must exist).
3. **Semantic fixture-fact matching** — each non-null field value must be consistent with what was said in the audio fixture; no field may contain a value that contradicts or was not derivable from the recording.
4. **Unsupported-value introduction** — `urgency` must be one of `"low"`, `"medium"`, `"high"`, or `null`; no other string is acceptable. If the spoken urgency did not map to an allowed value, the field must be `null` and `"urgency"` must appear in `uncertain_fields`.

## Recommended metrics
- **Output type:** structured_json (schema: `MaintenanceTicket`)
- For structured extraction, use the GAIK `extraction_eval` framework (field-level Precision / Recall / F1, hallucination rate) via `ExtractionEvaluator`.
- For RAG / answers, use `RAG_eval` (faithfulness, answer relevance, context precision/recall) via `RAGEvaluator`.
- For transcription, use `transcription_eval`; for translation, `translation_eval`; for report writing, `report_writing_eval`.

This use case uses the **`extraction_eval`** framework (`ExtractionEvaluator`) for field-level Precision / Recall / F1 and hallucination rate. Transcription quality can be assessed separately with `transcription_eval` if reference transcripts are available.

## Test data
- **Data sources:** mobile app audio recordings from field technicians
- Place ground-truth examples under `evals/ground_truth/` and predictions under `evals/predictions/`.

The PoC uses a single supplied Finnish audio fixture. Ground truth is established by a human reviewer who listens to the recording and records the correct field values in `evals/ground_truth/<fixture_stem>_ticket.json`. For broader evaluation, additional recordings should be collected from real field technicians; ground truth for each should be annotated by a domain expert (ideally a supervisor familiar with the maintenance vocabulary) before comparison against model output.

## Thresholds and acceptance
- urgency must be one of ['low', 'medium', 'high'] or null
- If urgency is null, 'urgency' must appear in uncertain_fields
- If location is null, 'location' must appear in uncertain_fields
- If fault_description is null, 'fault_description' must appear in uncertain_fields
- observation_date must match YYYY-MM-DD format if present
- observation_time must match HH:MM format if present

No numerical thresholds have been specified for this single-fixture PoC. The PoC passes Gate 3 when all four qualitative checks are satisfied: the output is valid JSON, all required field keys are present, no extracted value contradicts the audio, and `urgency` is within the allowed enum. Numerical thresholds (e.g. F1 ≥ 0.9 on required fields, hallucination rate ≤ 5%) should be established once a multi-fixture evaluation set is available.

## Human review
- **Required:** yes
- **Reviewers:** supervisor

## Limitations
- **Single fixture:** conclusions drawn from one recording cannot be generalised. Accuracy on technical Finnish vocabulary, background noise, or non-standard urgency phrasing is unknown until more fixtures are tested.
- **No ground truth yet:** `evals/ground_truth/` is empty. A human listener must annotate the fixture before `run_basic_eval.py` can produce meaningful metrics.
- **Subjective fields:** `fault_description` and `location` are free-form strings. Exact-string matching against ground truth will undercount correct extractions (e.g. synonym or paraphrase). Semantic matching (via `ExtractionEvaluator` with `match_mode='semantic'`) is recommended for these fields.
- **Urgency mapping subjectivity:** the Finnish → urgency mapping table in `extraction_requirements.md` reflects the wizard's interpretation; edge cases should be validated with the supervisors who will review real tickets.
