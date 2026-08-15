# Developer Guide — AI-Assisted Meeting Record Generator

> Package structure, extension points, component configuration, tests, and evaluation.

## Architecture
This use case is driven by an **executable JSON blueprint** (`use_case.blueprint.json`) — the single source of truth. The PoC, the visual workflows (`workflow.mmd`, `workflow.bpmn`), and these docs are all *generated from it*. To change behaviour, edit the blueprint and regenerate; never hand-edit generated artifacts.

## Pipeline
| Step | Type | Component | Inputs | Outputs |
|------|------|-----------|--------|---------|
| provide_meeting_bundle | user_task | — | — | meeting_audio, agenda_document, participant_list |
| transcribe_audio | automated_task | Transcriber <br/>opts: transcription_model=whisper_local, language=en, diarization=False | meeting_audio | audio_transcript |
| parse_agenda | automated_task | PyMuPDFParser <br/>opts: use_markdown=False | agenda_document | parsed_agenda |
| extract_meeting_record | automated_task | Extractor <br/>opts: schema_ref=schemas/output_schema.py, requirements_ref=schemas/output_schema_requirements.json | audio_transcript, parsed_agenda, participant_list | meeting_record_json |
| validate_extraction | automated_task | LLMJudge | audio_transcript, parsed_agenda, meeting_record_json | validation_report |
| human_review | human_review | — | meeting_record_json, validation_report | approved_meeting_record |

### Components and their options
- **Transcriber** (component)
- **PyMuPDFParser** (component)
- **Extractor** (component)
- **LLMJudge** (component)

- **Transcriber** — `run_poc.py`, `transcribe_audio` block: constructed with `transcription_model="whisper_local"`, `diarization=False`, `language` from `config.yaml` (`language: en`), and `local_api_base`/`local_api_key` read from the `LOCAL_TRANSCRIBER_API_BASE`/`LOCAL_TRANSCRIBER_API_KEY` env vars (`.env`). `.segments` (list of `{start, end, text}` dicts) is rendered into `[HH:MM:SS - HH:MM:SS] text` lines by `_build_audio_transcript_text()` so the extractor can cite timestamps.
- **PyMuPDFParser** — `parse_agenda` block: `parse_document(..., use_markdown=False)` inserts `=== PAGE N ===` markers into `text_content`; `_build_agenda_text()` prefixes the source file name so the extractor can build `file|page` citations.
- **Extractor** — `extract_meeting_record` block: reuses the wizard-approved schema via `_load_output_schema(schema_dir)` (falls back to a live `SchemaGenerator` call only if the schema files are missing or `extraction_requirements.md`'s hash has changed); `documents=[source_text]` where `source_text` concatenates the transcript, parsed agenda, and participant list (each with a `... FILE:` header) — see `config.yaml` for `extraction_model`/`temperature`.
- **LLMJudge** — end of `run_poc.py`: `model_provider="azure"`, `use_azure` from `config.yaml`. Runs only if both `extracted_fields` and `source_text` are set; writes `output/validation.json`.

## Layout (PoC)
```
poc/
  run_poc.py            <- pipeline entry point (python run_poc.py --input <bundle.json>)
  config.yaml           <- model names, temperature, paths
  requirements.txt
  .env.example
  schemas/              <- output_schema.py (Pydantic) + requirements JSON + hash
  prompts/              <- extraction_requirements.md
  output/                <- meeting_record.json + validation.json land here
  evals/                <- run_basic_eval.py, ground_truth/
```

Note: this pipeline reads its three inputs (audio, agenda, participant list) from a
bundle manifest passed via `--input`, not from a `sample_input/` folder that the
scaffold created by default for the generic single-file-per-run template.

## Extension points
- **Add/replace a component:** update `components` + `workflow.steps` + `artifacts` in the blueprint, re-validate, regenerate.
- **Change the schema/fields:** edit `target_output_spec` (and `prompts/extraction_requirements.md`); the schema regenerates on the next run via the requirements hash.
- **Tune a component option:** set it in `workflow.steps[].parameters` (e.g. `enhanced_transcript`, `include_verification`, `hybrid_search`).

## Configuration
- **Model provider:** azure_openai
- **Model preferences:** transcription_model: whisper_local, extraction_model: gpt-5.4, judge_model_provider: azure_openai, temperature: 0.0, notes: Self-hosted Whisper endpoint is available for transcription (local_api_base/local_api_key). Extraction uses Azure OpenAI.
- **Integration targets:** _none_

## Tests and evaluation
- Evaluation requirements: CLI run must exit successfully and save non-empty, parseable JSON to poc/output/. Compare output semantically against fixtures/expected_meeting_record.json, focusing on correctness of decisions, actions, unresolved issues, conflicts, and citation validity/format.
- See `evals/` for the basic evaluation script and `evaluation_plan.md` for the full plan.

## Gotchas

Found and fixed while building this PoC -- check again after any re-scaffold or re-generation:

- The `SchemaGenerator` output for a `parent_with_nested_list` structure (this schema's shape) rendered nested list-field type hints as a fully-qualified `gaik.software_components.extractor.schema.<Name>` path that isn't actually importable. Fixed by using the locally-defined class names directly in `output_schema.py`.
- `ExtractionRequirements`/`CompositeExtractionRequirements` field metadata can come back with the wrong `nullable`/`field_type`/`required` combination for a genuinely-nullable field (`uncertainty_reason` was generated as required non-null `str`, but it must be `null` whenever `owner`/`due_date` are both known). Cross-check generated field metadata against the actual business rule, not just against the enum of accepted `field_type` values.
- Whichever structure type `SchemaGenerator` picks (`ExtractionRequirements` vs `CompositeExtractionRequirements`), `_load_output_schema()` must instantiate the matching class -- a fixed call to `ExtractionRequirements(**data)` raises on composite payloads (missing `use_case_name`/`fields` at the top level). Detect via the `structure_type` key in the saved requirements JSON.
- `evals/run_basic_eval.py` as scaffolded had a stray indentation error that fails `ast.parse` before it can even run -- fixed here.
- LLMJudge does not know this pipeline's business rules (name normalization against the participant list, "the actual end time overrides the agenda's scheduled end time"). It will flag both as hallucinations even though they are correct by design. Treat judge flags as prompts for the human reviewer to double-check, not an automatic pass/fail gate.
