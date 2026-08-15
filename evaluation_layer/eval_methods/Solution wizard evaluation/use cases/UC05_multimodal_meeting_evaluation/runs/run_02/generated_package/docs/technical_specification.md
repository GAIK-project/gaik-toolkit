# Technical Specification — AI-Supported Meeting Record Generation

> Generated from `use_case.blueprint.json`. Source of truth is the blueprint; regenerate after any change.

## Overview
Combines a meeting audio recording, the agenda document, and the participant list to produce a structured, evidence-cited meeting record capturing decisions, actions, and unresolved issues for project-manager review.

- **Use-case id:** `meeting_record_generation`
- **Domain:** project_management
- **Primary language:** en
- **Runtime interface:** cli: `python run_poc.py --input <bundle_path>`, where <bundle_path> is a JSON manifest referencing the meeting audio (wav), agenda (pdf), and participant list (json). The command must exit successfully and write a single JSON meeting record under poc/output/.

## Inputs and outputs
- **Input types:** audio, pdf, structured_data
- **Input formats:** wav, pdf, json
- **Output types:** structured_json
- **Data sources:** meeting_audio_recording, agenda_document, participant_list_json

## Selected components
- **Transcriber** (component)
- **PyMuPDFParser** (component)
- **Extractor** (component)
- **LLMJudge** (component)

- **Transcriber** (`transcription_model=whisper_local`) — selected because citations require `HH:MM:SS` audio timestamps, which only the self-hosted whisper_local path exposes (`.segments`); the hosted models return plain text only. `diarization=False` because only timestamps are needed, not speaker attribution; `enhanced_transcript=False` because the audio is English, not Finnish (the built-in enhancement is Finnish-tuned).
- **PyMuPDFParser** (`use_markdown=False`) — selected because the agenda is a native-text (non-scanned) PDF; the structured mode inserts `=== PAGE N ===` markers, the only free/local way to get `file_name|page_number` citations for a text-layer PDF.
- **Extractor** — combines the timestamped transcript, the page-marked agenda text, and the participant list against the approved `MeetingRecord` schema, following the evidence/citation rules in `prompts/extraction_requirements.md`.
- **LLMJudge** — added because `human_review_required=true`; runs a hallucination pre-screen on the extracted record against the transcript before the project manager reviews it.

## Workflow
| Step | Type | Component | Inputs | Outputs |
|------|------|-----------|--------|---------|
| provide_input_bundle | user_task | — | — | meeting_audio, agenda_pdf, participant_list |
| transcribe_meeting | automated_task | Transcriber <br/>opts: transcription_model=whisper_local, diarization=False, language=en, enhanced_transcript=False | meeting_audio | raw_transcript |
| parse_agenda | automated_task | PyMuPDFParser <br/>opts: use_markdown=False | agenda_pdf | parsed_agenda |
| extract_meeting_record | automated_task | Extractor <br/>opts: schema_ref=schemas/output_schema.py, requirements_ref=schemas/output_schema_requirements.json | raw_transcript, parsed_agenda, participant_list | meeting_record_json |
| validate_meeting_record | automated_task | LLMJudge <br/>opts: rubric_ref=to_be_generated | raw_transcript, meeting_record_json | validation_report |
| human_review | human_review | — | meeting_record_json, validation_report | approved_meeting_record |

### Artifacts
- `meeting_audio` — audio, source: user_upload
- `agenda_pdf` — pdf, source: user_upload
- `participant_list` — text, source: user_upload
- `raw_transcript` — transcript, source: generated
- `parsed_agenda` — text, source: generated
- `meeting_record_json` — structured_json, source: generated (final output)
- `validation_report` — validation_report, source: generated
- `approved_meeting_record` — structured_json, source: generated (final output)

## Output schema
- **Schema name:** MeetingRecord
- **Field count:** 12
- **Required fields:** meeting_id, title, meeting_date, start_time, end_time, participants, topics, decisions, action_items, unresolved_issues, conflicts, review_status
- **Missing-value policy:** Never invent unstated facts. For action_items, set owner/due_date to null and populate uncertainty_reason when not explicitly stated. Agenda-only proposals must not be recorded as decisions unless the meeting audio confirms them; when the agenda and the meeting disagree, record a conflict entry (citing both sources) and follow the spoken decision.

**Fields:**
- meeting_id
- title
- meeting_date
- start_time
- end_time
- participants
- topics
- decisions
- action_items
- unresolved_issues
- conflicts
- review_status

**Validation rules:**
- Every decision, action_item, unresolved_issue, and conflict must include at least one citation. Citations are pipe-delimited strings: 'file_name|start_timestamp|end_timestamp' (HH:MM:SS) for audio, or 'file_name|page_number' for the agenda document. review_status must equal 'pending_review' in the PoC output.

## Model configuration
- **Model provider:** azure_openai
- **Model preferences:** extraction_model: gpt-5.4, temperature: 0.0, transcription_model: whisper_local

## Runtime and integration assumptions
- **Integration targets:** _none_
- **Human review:** yes

## Security and governance
- **Security constraints:** Meeting material is internal. Access to the record must be limited to the project team and the designated reviewer (project manager). No connection to calendar, project-management, document-management, or identity systems is required or permitted in this evaluation.
- **Contains personal data:** yes
- **Output sensitivity:** medium
- **Audit log required:** no

## Evaluation method
Compare the generated meeting_record.json semantically against fixtures/expected_meeting_record.json (decisions, actions, unresolved issues, conflicts). Validate every citation string against the required pipe-delimited pattern (file_name|start_timestamp|end_timestamp with HH:MM:SS for audio; file_name|page_number for the agenda). Confirm none of the fixture's must_not_assert statements are asserted by the output (hallucination check).
