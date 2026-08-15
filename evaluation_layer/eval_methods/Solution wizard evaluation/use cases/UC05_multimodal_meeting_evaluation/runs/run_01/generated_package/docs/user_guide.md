# User Guide — AI-Assisted Meeting Record Generator

> How to run the solution, provide input, inspect output, and adjust settings.

## What this does
Combine meeting audio recordings, agenda documents, and participant lists into a structured, evidence-cited meeting record capturing decisions, actions, and unresolved issues.

This proof of concept demonstrates: Process fixtures/poc_input_bundle.json (referencing the meeting WAV, agenda PDF, and participant JSON) via a CLI accepting --input <bundle_path>. The run must exit successfully and save non-empty, parseable JSON to poc/output/ capturing the frozen meeting decisions, actions, unresolved issues, and the known date conflict, with audio citations as file_name|start_timestamp|end_timestamp (HH:MM:SS) and agenda citations as file_name|page_number. Unsupported owners, dates, budget approval, and SSO decisions must be left unset, and review_status must be pending_review. Output is compared semantically against fixtures/expected_meeting_record.json.

## Prerequisites
- Python 3.11+
- Install dependencies: `pip install -r poc/requirements.txt`
- Copy `poc/.env.example` to `poc/.env` and fill in your model-provider credentials (provider: azure_openai).

## Providing input
- **Expected input:** audio, pdf, json (formats: wav, pdf, json)
- This pipeline takes a single **bundle manifest** JSON file per meeting (e.g. `poc_input_bundle.json`) that points to the three source files for that meeting:
  ```json
  {
    "inputs": {
      "meeting_audio": "input/meeting.wav",
      "agenda_pdf": "input/agenda.pdf",
      "participant_list": "input/participants.json"
    },
    "output": {"directory": "output", "filename": "meeting_record.json", "format": "json"}
  }
  ```
- All three paths inside the manifest are resolved **relative to the manifest's own folder**, not the current working directory. The audio must be English `.wav`; the agenda must be a text-layer PDF (not scanned); the participant list is a JSON array of `{name, role}`.

## Running
```bash
python poc/run_poc.py --input /path/to/poc_input_bundle.json
```

## Inspecting the output
- Results are written to the directory/filename given in the bundle manifest's `output` block (e.g. `poc/output/meeting_record.json`), plus a `validation.json` LLMJudge report alongside it.
- The output is structured_json following the `MeetingRecord` schema.
- **Human review:** yes

A correct output file is one non-empty JSON object with all twelve top-level fields present (`meeting_id`, `title`, `meeting_date`, `start_time`, `end_time`, `participants`, `topics`, `decisions`, `action_items`, `unresolved_issues`, `conflicts`, `review_status="pending_review"`). When reviewing:
- Open each citation (`file|start|end` for audio, `file|page` for the agenda) and confirm it actually supports the statement next to it.
- Check that every `action_items` entry either has both an `owner` and `due_date`, or has both set to `null` with an `uncertainty_reason` explaining why — never a guessed value.
- Read `validation.json`: LLMJudge may flag items as "hallucinations" that are actually correct by design — e.g. a participant name normalized against the participant list, or an actual end time that differs from the agenda's *scheduled* end time. Treat judge flags as prompts to double-check, not automatic rejections; the reviewer's judgment is the final gate.

## Adjusting settings
| To change... | Edit... |
|--------------|---------|
| What is extracted / the fields | `poc/prompts/extraction_requirements.md` then re-run (schema regenerates) |
| Output structure | `poc/schemas/output_schema.py` |
| Model / temperature | `poc/config.yaml` |

## Privacy note
Personal data: yes · output sensitivity: internal. Handle outputs accordingly.
