# User Guide — AI-Supported Meeting Record Generation

> How to run the solution, provide input, inspect output, and adjust settings.

## What this does
Combines a meeting audio recording, the agenda document, and the participant list to produce a structured, evidence-cited meeting record capturing decisions, actions, and unresolved issues for project-manager review.

This proof of concept demonstrates: Process a fixed input bundle (meeting WAV + agenda PDF + participant JSON, referenced by a bundle manifest) via a CLI invoked as `python run_poc.py --input <bundle_path>`. The PoC must exit successfully and save a non-empty, schema-valid JSON meeting record to poc/output/. The output must capture the frozen meeting decisions, actions, unresolved issues, and the agenda/meeting date conflict; cite audio evidence as 'file_name|start_timestamp|end_timestamp' (HH:MM:SS) and agenda evidence as 'file_name|page_number'; leave unsupported owners, dates, budget approval, and the SSO decision unset (null) with an uncertainty_reason; and set review_status to 'pending_review'. The output is compared semantically against a fixture expected_meeting_record.json. The web application, authentication, external system integrations, and operational scaling are out of scope for this first PoC.

## Prerequisites
- Python 3.11+
- Install dependencies: `pip install -r poc/requirements.txt`
- Copy `poc/.env.example` to `poc/.env` and fill in your model-provider credentials (provider: azure_openai).

## Providing input
- **Expected input:** audio, pdf, structured_data (formats: wav, pdf, json)
- This PoC does **not** auto-discover files in `sample_input/`. Instead, point it at an
  **input bundle manifest** (a JSON file) that references the three source files for
  one meeting:
  ```json
  {
    "meeting_id": "NIMBUS-PRR-2026-09-17",
    "inputs": {
      "meeting_audio": "input/meeting.wav",
      "agenda_pdf": "input/agenda.pdf",
      "participant_list": "input/participants.json"
    },
    "output": {"directory": "output", "filename": "meeting_record.json"}
  }
  ```
  Paths under `inputs` are resolved relative to the bundle file's own location. The
  meeting audio must be a `.wav`; the agenda must be a native-text (non-scanned) PDF;
  the participant list is a JSON file of `{name, role}` entries.

## Running
```bash
python poc/run_poc.py --input path/to/your_bundle.json
```

You also need a self-hosted Whisper endpoint configured in `.env`
(`LOCAL_TRANSCRIBER_API_BASE` / `LOCAL_TRANSCRIBER_API_KEY`) — audio citations require
per-segment timestamps, which hosted transcription models do not provide.

## Inspecting the output
- Results are written to `poc/output/`.
- The output is structured_json following the `MeetingRecord` schema.
- **Human review:** yes

A correct output file has all twelve top-level fields populated, `review_status` set to
`"pending_review"`, and — critically — every entry under `decisions`, `action_items`,
`unresolved_issues`, and `conflicts` carrying at least one citation string
(`file_name|start_timestamp|end_timestamp` for audio, `file_name|page_number` for the
agenda). To check it: spot-check a few citations by jumping to that timestamp in the
recording or that page in the agenda and confirming the claim is actually there; confirm
`owner`/`due_date` are `null` (with an `uncertainty_reason`) wherever the meeting did not
explicitly state them, rather than a plausible-looking guess; and check the `conflicts`
list for anything the agenda proposed that the meeting actually changed. The project
manager's sign-off is exactly this check, applied before the record is distributed.

## Adjusting settings
| To change... | Edit... |
|--------------|---------|
| What is extracted / the fields | `poc/prompts/extraction_requirements.md` then re-run (schema regenerates) |
| Output structure | `poc/schemas/output_schema.py` |
| Model / temperature | `poc/config.yaml` |

## Privacy note
Personal data: yes · output sensitivity: medium. Handle outputs accordingly.
