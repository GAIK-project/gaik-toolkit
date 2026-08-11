# User Guide — Maintenance Fault Reporting via Finnish Voice

> How to run the solution, provide input, inspect output, and adjust settings.

## What this does
Field technicians report facility faults via Finnish voice messages; the system transcribes, extracts a structured maintenance ticket, validates it, and presents it to a supervisor for approval before entry into the maintenance system.

This proof of concept demonstrates: Accept a supplied Finnish audio fixture, exit successfully, produce a non-empty parseable JSON maintenance ticket, preserve the fixture facts, include all required fields (location, fault_description, urgency), and leave unsupported or unknown values null rather than inventing them.

## Prerequisites
- Python 3.11+
- Install dependencies: `pip install -r poc/requirements.txt`
- Copy `poc/.env.example` to `poc/.env` and fill in your model-provider credentials (provider: azure_openai).

## Providing input
- **Expected input:** audio (formats: wav, mp3, m4a)
- Place your input file(s) in `poc/sample_input/`.

Place a single Finnish audio file in `poc/sample_input/`. Any of the following formats are accepted: `.wav`, `.mp3`, `.m4a`. The recording should be a technician describing a facility fault in spoken Finnish — typically 15–90 seconds. There are no specific sample-rate or bitrate requirements; the transcription model handles standard mobile-app quality recordings. The file name can be anything; the output files will share the same stem (e.g. `fault_report.wav` → `output/fault_report_ticket.json`).

## Running
```bash
cd poc
python run_poc.py                      # picks up the first audio file in sample_input/
python run_poc.py --input my.wav       # or specify the file directly
```

## Inspecting the output
- Results are written to `poc/output/`.
- The output is structured_json following the `MaintenanceTicket` schema.
- **Human review:** yes

A correct `_ticket.json` is a JSON object with exactly nine keys. Check:
- **Required fields present:** `location`, `fault_description`, and `urgency` must appear (value may be `null` only if also listed in `uncertain_fields`).
- **`urgency` is strictly one of:** `"low"`, `"medium"`, or `"high"` — any other string (or Finnish word) is an extraction error.
- **Dates and times are formatted:** `observation_date` as `YYYY-MM-DD`; `observation_time` as `HH:MM`.
- **No invented values:** cross-check field values against the `_transcript.txt` saved alongside the ticket. Every non-null value should be traceable to something the technician actually said.
- **`uncertain_fields` is honest:** if the technician did not state a required field, it should appear in this list and its value should be `null`, not a guess.
- **Validation report:** the `_validation.json` should show `"passed": true`; any `hallucination_flags` entries warrant closer review before approval.

## Adjusting settings
| To change... | Edit... |
|--------------|---------|
| What is extracted / the fields | `poc/prompts/extraction_requirements.md` then re-run (schema regenerates) |
| Output structure | `poc/schemas/output_schema.py` |
| Model / temperature | `poc/config.yaml` |

## Privacy note
Personal data: yes · output sensitivity: internal. Handle outputs accordingly.
