# Developer Guide — AI-Supported Meeting Record Generation

> Package structure, extension points, component configuration, tests, and evaluation.

## Architecture
This use case is driven by an **executable JSON blueprint** (`use_case.blueprint.json`) — the single source of truth. The PoC, the visual workflows (`workflow.mmd`, `workflow.bpmn`), and these docs are all *generated from it*. To change behaviour, edit the blueprint and regenerate; never hand-edit generated artifacts.

## Pipeline
| Step | Type | Component | Inputs | Outputs |
|------|------|-----------|--------|---------|
| provide_input_bundle | user_task | — | — | meeting_audio, agenda_pdf, participant_list |
| transcribe_meeting | automated_task | Transcriber <br/>opts: transcription_model=whisper_local, diarization=False, language=en, enhanced_transcript=False | meeting_audio | raw_transcript |
| parse_agenda | automated_task | PyMuPDFParser <br/>opts: use_markdown=False | agenda_pdf | parsed_agenda |
| extract_meeting_record | automated_task | Extractor <br/>opts: schema_ref=schemas/output_schema.py, requirements_ref=schemas/output_schema_requirements.json | raw_transcript, parsed_agenda, participant_list | meeting_record_json |
| validate_meeting_record | automated_task | LLMJudge <br/>opts: rubric_ref=to_be_generated | raw_transcript, meeting_record_json | validation_report |
| human_review | human_review | — | meeting_record_json, validation_report | approved_meeting_record |

### Components and their options
- **Transcriber** (component)
- **PyMuPDFParser** (component)
- **Extractor** (component)
- **LLMJudge** (component)

- **Transcriber** — constructed with `transcription_model="whisper_local"`, `diarization=False`, `language` from `config.yaml`, `enhanced_transcript=False`, and `local_api_base`/`local_api_key` read from the `LOCAL_TRANSCRIBER_API_BASE`/`LOCAL_TRANSCRIBER_API_KEY` env vars (set in `.env`). `.segments` (list of `{start, end, text}`-shaped dicts, keys depend on the local server) is what supplies audio-citation timestamps — reformatted to `HH:MM:SS` in `run_poc.py`.
- **PyMuPDFParser** — constructed with defaults, called as `parse_document(path, use_markdown=False)` to get `=== PAGE N ===` markers in `text_content` for page-level citations.
- **Extractor (`DataExtractor`)** — constructed with `get_openai_config(use_azure=True)` (reads `AZURE_API_KEY`/`AZURE_ENDPOINT`/`AZURE_API_VERSION` from `.env`), `model` and `temperature` from `config.yaml` (`models.extraction`, `models.temperature`). Called with the pre-generated `MeetingRecord_Extraction` schema and its `CompositeExtractionRequirements` (loaded from `schemas/output_schema_requirements.json`).
- **LLMJudge** — constructed with `model_provider="azure"` (matching `use_azure`), used only for `detect_hallucinations()` (not the full `ValidationRubric` path); results written to `output/validation.json`.

## Layout (PoC)
```
poc/
  run_poc.py            <- pipeline entry point
  config.yaml           <- model names, temperature, paths
  requirements.txt
  .env.example
  schemas/              <- output_schema.py (Pydantic) + requirements + hash
  prompts/              <- extraction_requirements.md, validation_rubric.md
  sample_input/  output/
  evals/                <- run_basic_eval.py
```

## Extension points
- **Add/replace a component:** update `components` + `workflow.steps` + `artifacts` in the blueprint, re-validate, regenerate.
- **Change the schema/fields:** edit `target_output_spec` (and `prompts/extraction_requirements.md`); the schema regenerates on the next run via the requirements hash.
- **Tune a component option:** set it in `workflow.steps[].parameters` (e.g. `enhanced_transcript`, `include_verification`, `hybrid_search`).

## Configuration
- **Model provider:** azure_openai
- **Model preferences:** extraction_model: gpt-5.4, temperature: 0.0, transcription_model: whisper_local
- **Integration targets:** _none_

## Tests and evaluation
- Evaluation requirements: Compare the generated meeting_record.json semantically against fixtures/expected_meeting_record.json (decisions, actions, unresolved issues, conflicts). Validate every citation string against the required pipe-delimited pattern (file_name|start_timestamp|end_timestamp with HH:MM:SS for audio; file_name|page_number for the agenda). Confirm none of the fixture's must_not_assert statements are asserted by the output (hallucination check).
- See `evals/` for the basic evaluation script and `evaluation_plan.md` for the full plan.

**Gotchas:**
- `Transcriber` requires `api_config` positionally even on the `whisper_local` path (an empty `{}` is fine — it's only used if `enhanced_transcript=True`), and raises `ValueError` at `transcribe()` time if `local_api_base`/`local_api_key` are missing.
- `.segments` returned by `Transcriber` is a plain `list[dict]` with no fixed schema across local whisper servers — `run_poc.py`'s `_format_timestamp()` handles both numeric-seconds and pre-formatted string timestamps defensively.
- `PyMuPDFParser`'s page markers only appear with `use_markdown=False` (structured mode); the default `use_markdown=True` concatenates pages with no marker at all and silently breaks page-level citations.
- The generated `output_schema.py` from `SchemaGenerator` can leak an unqualified `gaik.software_components.extractor.schema.` prefix into nested `list[...]` type annotations (a known upstream quirk — the cleanup regex in `gaik/software_components/extractor/schema.py` targets a stale old module name). If you regenerate the schema, check for this and strip it, or the file will raise `NameError` on import.
- `LLMJudge.model_provider` accepts `"openai" | "azure" | "anthropic" | "google"` — **not** `"azure_openai"` — and defaults to `"google"` if omitted, which silently requires Google Vertex credentials even when nothing else in the blueprint mentions Google.
- The extracted `participants` field is overwritten post-extraction from the participant-list JSON directly (not trusted from the LLM) to guarantee exact name/role matches; `meeting_id` is likewise overwritten from the input bundle's own `meeting_id` field when present, since that's supplied data, not something to infer from audio.
