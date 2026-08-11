# User Guide — Finnish Voice Fault Reporting — Maintenance Ticket Generator

> How to run the solution, provide input, inspect output, and adjust settings.

## What this does
Convert Finnish voice messages from field technicians into structured maintenance tickets for supervisor review and system entry.

This proof of concept demonstrates: Accept a supplied Finnish audio fixture, exit successfully, produce a non-empty parseable JSON ticket with all required fields present (may be null/unknown if not stated but flagged in uncertain_fields), preserve fixture facts, and leave unsupported values null or unknown.

## Prerequisites
- Python 3.11+
- Install dependencies: `pip install -r poc/requirements.txt`
- Copy `poc/.env.example` to `poc/.env` and fill in your model-provider credentials (provider: azure_openai).

## Providing input
- **Expected input:** audio (formats: mp3, m4a, wav)
- Place your input file(s) in `poc/sample_input/`.

Place a single Finnish voice recording in `poc/sample_input/`. Supported formats: `.wav`, `.mp3`, `.m4a`. The recording should be a technician describing a facility fault — ideally covering the fault location, what is wrong, and the urgency level. There is no minimum or maximum length requirement, but the pipeline is optimised for short field reports (typically under 3 minutes). Audio cannot be auto-generated; a real recording is required.

## Running
```bash
python poc/run_poc.py
```

## Inspecting the output
- Results are written to `poc/output/`.
- The output is structured_json following the `MaintenanceTicket` schema.
- **Human review:** yes

A correct output file (`output/<stem>_ticket.json`) is a JSON object with all nine `MaintenanceTicket` fields present. Required fields (`location`, `fault_description`, `urgency`) should be non-null strings if they were mentioned in the recording; if absent they must be `null` and the field name must appear in `uncertain_fields`. The `urgency` value must be exactly `"low"`, `"medium"`, or `"high"` — any other string indicates an extraction error. A companion `_validation.json` file reports the LLMJudge hallucination check: if `"passed": true`, all fields are grounded in the transcript. The supervisor should review the ticket alongside the `_transcript.txt` to verify that the extracted values faithfully reflect what the technician said before approving.

## Adjusting settings
| To change... | Edit... |
|--------------|---------|
| What is extracted / the fields | `poc/prompts/extraction_requirements.md` then re-run (schema regenerates) |
| Output structure | `poc/schemas/output_schema.py` |
| Model / temperature | `poc/config.yaml` |

## Privacy note
Personal data: yes · output sensitivity: internal. Handle outputs accordingly.
