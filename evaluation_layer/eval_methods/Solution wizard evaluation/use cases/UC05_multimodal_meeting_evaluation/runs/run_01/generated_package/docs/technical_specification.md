# Technical Specification — AI-Assisted Meeting Record Generator

> Generated from `use_case.blueprint.json`. Source of truth is the blueprint; regenerate after any change.

## Overview
Combine meeting audio recordings, agenda documents, and participant lists into a structured, evidence-cited meeting record capturing decisions, actions, and unresolved issues.

- **Use-case id:** `meeting_record_generation`
- **Domain:** project_management
- **Primary language:** en
- **Runtime interface:** cli (python poc/run_poc.py --input <bundle_path>)

## Inputs and outputs
- **Input types:** audio, pdf, json
- **Input formats:** wav, pdf, json
- **Output types:** structured_json
- **Data sources:** Per-meeting bundle (fixtures/poc_input_bundle.json) referencing one WAV recording, one PDF agenda, and one JSON participant list. No live system integration in this PoC.

## Selected components
- **Transcriber** (component)
- **PyMuPDFParser** (component)
- **Extractor** (component)
- **LLMJudge** (component)

- **Transcriber** — selected over the `AudioToStructuredData` module because citations require `file|start_timestamp|end_timestamp`, which needs the whisper_local path's `.segments`; configured with `transcription_model=whisper_local` (self-hosted endpoint, confirmed available) and `diarization=False` (only timestamps are needed, not per-speaker attribution).
- **PyMuPDFParser** — selected over VisionParser/DoclingParser because the agenda is a plain text-layer PDF (no scanned pages or complex layout reported); `use_markdown=False` inserts `=== PAGE N ===` markers, the cheapest local way to get `file|page_number` citations.
- **Extractor** — combines the timestamped transcript, page-cited agenda text, and participant list into one `MeetingRecord` extraction call against the approved schema.
- **LLMJudge** — added because `human_review=yes`; pre-screens the extraction for unsupported claims before the project manager reviews it. Configured with `model_provider="azure"` to match the extraction provider (a different-family judge would reduce shared-model bias but wasn't required — see `assumption_008`).

## Workflow
| Step | Type | Component | Inputs | Outputs |
|------|------|-----------|--------|---------|
| provide_meeting_bundle | user_task | — | — | meeting_audio, agenda_document, participant_list |
| transcribe_audio | automated_task | Transcriber <br/>opts: transcription_model=whisper_local, language=en, diarization=False | meeting_audio | audio_transcript |
| parse_agenda | automated_task | PyMuPDFParser <br/>opts: use_markdown=False | agenda_document | parsed_agenda |
| extract_meeting_record | automated_task | Extractor <br/>opts: schema_ref=schemas/output_schema.py, requirements_ref=schemas/output_schema_requirements.json | audio_transcript, parsed_agenda, participant_list | meeting_record_json |
| validate_extraction | automated_task | LLMJudge | audio_transcript, parsed_agenda, meeting_record_json | validation_report |
| human_review | human_review | — | meeting_record_json, validation_report | approved_meeting_record |

### Artifacts
- `meeting_audio` — audio, source: user_upload
- `agenda_document` — pdf, source: user_upload
- `participant_list` — text, source: user_upload
- `audio_transcript` — transcript, source: generated
- `parsed_agenda` — text, source: generated
- `meeting_record_json` — structured_json, source: generated
- `validation_report` — validation_report, source: generated
- `approved_meeting_record` — structured_json, source: generated (final output)

## Output schema
- **Schema name:** MeetingRecord
- **Field count:** 12
- **Required fields:** meeting_id, title, meeting_date, start_time, end_time, participants, topics, decisions, action_items, unresolved_issues, conflicts, review_status
- **Missing-value policy:** Do not infer unsupported facts (owners, dates, budget approvals, SSO decisions, or any other fact not explicitly stated). For action_items, set owner/due_date to null and provide uncertainty_reason when not explicitly stated in a source.

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
- Every decision, action_item, unresolved_issue, and conflict must carry at least one citation.
- Audio citations use a single string: file_name|start_timestamp|end_timestamp, with HH:MM:SS timestamps.
- Agenda citations use a single string: file_name|page_number.
- An agenda item alone is not a decision -- only the spoken meeting content determines what was actually decided.
- When the agenda and spoken content conflict, record the conflict and follow the explicit spoken decision.
- review_status starts as 'pending_review'.

## Model configuration
- **Model provider:** azure_openai
- **Model preferences:** transcription_model: whisper_local, extraction_model: gpt-5.4, judge_model_provider: azure_openai, temperature: 0.0, notes: Self-hosted Whisper endpoint is available for transcription (local_api_base/local_api_key). Extraction uses Azure OpenAI.

## Runtime and integration assumptions
- **Integration targets:** _none_
- **Human review:** yes

## Security and governance
- **Security constraints:** Meeting material is internal. Access limited to the project team and the designated reviewer. No connection to calendar, project-management, document-management, or identity systems is required.
- **Contains personal data:** yes
- **Output sensitivity:** internal
- **Audit log required:** no

## Evaluation method
CLI run must exit successfully and save non-empty, parseable JSON to poc/output/. Compare output semantically against fixtures/expected_meeting_record.json, focusing on correctness of decisions, actions, unresolved issues, conflicts, and citation validity/format.
