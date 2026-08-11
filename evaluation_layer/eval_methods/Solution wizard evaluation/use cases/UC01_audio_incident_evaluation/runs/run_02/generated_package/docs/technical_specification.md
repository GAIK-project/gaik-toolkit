# Technical Specification — Finnish Voice Fault Reporting — Maintenance Ticket Generator

> Generated from `use_case.blueprint.json`. Source of truth is the blueprint; regenerate after any change.

## Overview
Convert Finnish voice messages from field technicians into structured maintenance tickets for supervisor review and system entry.

- **Use-case id:** `maintenance_ticket`
- **Domain:** facility_maintenance
- **Primary language:** fi
- **Runtime interface:** cli (PoC); mobile app upload (production)

## Inputs and outputs
- **Input types:** audio
- **Input formats:** mp3, m4a, wav
- **Output types:** structured_json
- **Data sources:** mobile app audio recordings from field technicians

## Selected components
- **AudioToStructuredData** (module) — Primary input is Finnish audio; module encapsulates the full transcription, enhancement, and extraction pipeline.
- **Transcriber** (component)
- **Extractor** (component)
- **LLMJudge** (component)

- **AudioToStructuredData** — module-first selection for `audio_to_structured` pattern; covers transcription, Finnish enhancement, and extraction in a single pipeline.
- **Transcriber** — selected because input is audio; `enhanced_transcript=True` activates Finnish-tuned two-pass ASR repair (subsumes a separate TranscriptEnhancer step); `model=gpt-4o-transcribe` per user preference; `language=fi`.
- **Extractor** — converts the enhanced transcript to structured JSON conforming to `MaintenanceTicket`; uses the approved `schemas/output_schema.py` and `schemas/output_schema_requirements.json`.
- **LLMJudge** — added because `human_review=yes`; cross-checks every extracted field against the source transcript before the supervisor sees the ticket, reducing the risk of hallucinated values reaching the system.

## Workflow
| Step | Type | Component | Inputs | Outputs |
|------|------|-----------|--------|---------|
| record_and_upload | user_task | — | — | fault_audio |
| transcribe_audio | automated_task | Transcriber <br/>opts: language=fi, enhanced_transcript=True, model=gpt-4o-transcribe | fault_audio | enhanced_transcript |
| extract_ticket_fields | automated_task | Extractor <br/>opts: schema_ref=schemas/output_schema.py, requirements_ref=schemas/output_schema_requirements.json | enhanced_transcript | ticket_json |
| validate_ticket | automated_task | LLMJudge | enhanced_transcript, ticket_json | validation_report |
| notify_supervisor | automated_task | — | ticket_json, validation_report, enhanced_transcript | supervisor_notification |
| supervisor_review | human_review | — | ticket_json, validation_report, enhanced_transcript | approved_ticket |

### Artifacts
- `fault_audio` — audio, source: user_upload
- `enhanced_transcript` — transcript, source: generated
- `ticket_json` — structured_json, source: generated
- `validation_report` — validation_report, source: generated
- `supervisor_notification` — notification, source: generated
- `approved_ticket` — structured_json, source: generated (final output)

## Output schema
- **Schema name:** MaintenanceTicket
- **Field count:** 9
- **Required fields:** location, fault_description, urgency
- **Missing-value policy:** Required fields may be null when not stated in the audio, but must be listed in uncertain_fields. Unsupported urgency values must be set to null and 'urgency' listed in uncertain_fields.

**Fields:**
- reporter_name
- asset_identifier
- location
- fault_description
- urgency
- observation_date
- observation_time
- actions_taken
- uncertain_fields

**Validation rules:**
- urgency must be one of ['low', 'medium', 'high'] or null
- If urgency is null, 'urgency' must appear in uncertain_fields
- If location is null, 'location' must appear in uncertain_fields
- If fault_description is null, 'fault_description' must appear in uncertain_fields
- observation_date must match YYYY-MM-DD format if present
- observation_time must match HH:MM format if present

## Model configuration
- **Model provider:** azure_openai
- **Model preferences:** transcription_model: gpt-4o-transcribe, extraction_model: gpt-5.4, temperature: 0.0

## Runtime and integration assumptions
- **Integration targets:** _none_
- **Human review:** yes

## Security and governance
- **Security constraints:** raw_audio_retention: must not be retained after transcription, approved_ticket_retention: may be retained; no exact retention period specified, supervisor_approval_decision_retention: may be retained, external_model_api_allowed: True, local_processing_required: False, data_residency_requirement: none specified, contains_pii: yes (employee name and internal facility details may appear in audio), auth_rbac_audit_log: outside PoC scope; retaining approval decision is sufficient
- **Contains personal data:** yes
- **Output sensitivity:** internal
- **Audit log required:** no

## Evaluation method
metrics: ['json_parsing', 'required_field_coverage', 'semantic_fixture_fact_matching', 'unsupported_value_introduction'], thresholds: none specified for single-fixture PoC, eval_framework: extraction_eval
