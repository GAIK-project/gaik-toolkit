# Technical Specification — Maintenance Fault Reporting via Finnish Voice

> Generated from `use_case.blueprint.json`. Source of truth is the blueprint; regenerate after any change.

## Overview
Field technicians report facility faults via Finnish voice messages; the system transcribes, extracts a structured maintenance ticket, validates it, and presents it to a supervisor for approval before entry into the maintenance system.

- **Use-case id:** `maintenance_fault_reporting`
- **Domain:** facility_maintenance
- **Primary language:** fi
- **Runtime interface:** mobile_app

## Inputs and outputs
- **Input types:** audio
- **Input formats:** wav, mp3, m4a
- **Output types:** structured_json
- **Data sources:** mobile_app_voice_recording

## Selected components
- **AudioToStructuredData** (module) — Input is Finnish audio; module encapsulates transcription, Finnish enhancement, and structured extraction in a single pipeline. enhanced_transcript=True is set because language is Finnish.
- **LLMJudge** (component)

- **AudioToStructuredData** — selected by the module-first rule (audio → structured JSON); `enhanced_transcript=True` is set because the input language is Finnish, enabling the two-pass Finnish ASR repair pass internally (adds ~60 s latency per recording); `transcription_model=gpt-4o-transcribe`, `extraction_model=gpt-5.4`, `temperature=0.0`.
- **LLMJudge** — added because `human_review=yes`; pre-screens the extracted ticket for hallucinations and missing required fields before routing to the supervisor, reducing reviewer workload; `model_provider=azure_openai` (same provider as extractor — acceptable for PoC; a different provider would reduce shared-model bias in production).

## Workflow
| Step | Type | Component | Inputs | Outputs |
|------|------|-----------|--------|---------|
| record_voice_message | user_task | — | — | voice_message_audio |
| process_audio | automated_task | AudioToStructuredData <br/>opts: enhanced_transcript=True, language=fi, transcription_model=gpt-4o-transcribe, schema_ref=schemas/output_schema.py, requirements_ref=schemas/output_schema_requirements.json, extraction_model=gpt-5.4, temperature=0.0 | voice_message_audio | maintenance_ticket_json |
| validate_ticket | automated_task | LLMJudge <br/>opts: model_provider=azure_openai | maintenance_ticket_json | validation_report |
| supervisor_review | human_review | — | maintenance_ticket_json, validation_report | approved_ticket |

### Artifacts
- `voice_message_audio` — audio, source: user_upload
- `maintenance_ticket_json` — structured_json, source: generated
- `validation_report` — validation_report, source: generated
- `approved_ticket` — structured_json, source: generated (final output)

## Output schema
- **Schema name:** MaintenanceTicket
- **Field count:** 9
- **Required fields:** location, fault_description, urgency
- **Missing-value policy:** Set the field to null and add the field name to uncertain_fields. Do not invent or guess values. Required fields (location, fault_description, urgency) must appear in uncertain_fields when null.

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
- urgency must be one of: low, medium, high — never any other string
- observation_date must be YYYY-MM-DD format when present
- observation_time must be HH:MM format when present
- required fields (location, fault_description, urgency) must be present in the JSON; a null value is acceptable only when the field name is also listed in uncertain_fields

## Model configuration
- **Model provider:** azure_openai
- **Model preferences:** transcription_model: gpt-4o-transcribe, extraction_model: gpt-5.4, temperature: 0.0

## Runtime and integration assumptions
- **Integration targets:** _none_
- **Human review:** yes

## Security and governance
- **Security constraints:** Raw audio must not be retained after transcription, Approved ticket and supervisor approval decision may be retained, No specified retention period, External model APIs are permitted, No data-residency requirement specified, Authentication, RBAC, and full audit-log implementation are out of scope for PoC
- **Contains personal data:** yes
- **Output sensitivity:** internal
- **Audit log required:** no

## Evaluation method
metrics: ['json_parse_success', 'required_field_coverage', 'semantic_fixture_fact_matching', 'unsupported_value_introduction'], threshold: no numerical threshold specified for single-fixture PoC, test_data: single supplied Finnish audio fixture
