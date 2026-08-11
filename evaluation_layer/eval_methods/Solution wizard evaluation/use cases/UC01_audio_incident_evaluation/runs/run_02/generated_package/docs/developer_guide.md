# Developer Guide — Finnish Voice Fault Reporting — Maintenance Ticket Generator

> Package structure, extension points, component configuration, tests, and evaluation.

## Architecture
This use case is driven by an **executable JSON blueprint** (`use_case.blueprint.json`) — the single source of truth. The PoC, the visual workflows (`workflow.mmd`, `workflow.bpmn`), and these docs are all *generated from it*. To change behaviour, edit the blueprint and regenerate; never hand-edit generated artifacts.

## Pipeline
| Step | Type | Component | Inputs | Outputs |
|------|------|-----------|--------|---------|
| record_and_upload | user_task | — | — | fault_audio |
| transcribe_audio | automated_task | Transcriber <br/>opts: language=fi, enhanced_transcript=True, model=gpt-4o-transcribe | fault_audio | enhanced_transcript |
| extract_ticket_fields | automated_task | Extractor <br/>opts: schema_ref=schemas/output_schema.py, requirements_ref=schemas/output_schema_requirements.json | enhanced_transcript | ticket_json |
| validate_ticket | automated_task | LLMJudge | enhanced_transcript, ticket_json | validation_report |
| notify_supervisor | automated_task | — | ticket_json, validation_report, enhanced_transcript | supervisor_notification |
| supervisor_review | human_review | — | ticket_json, validation_report, enhanced_transcript | approved_ticket |

### Components and their options
- **AudioToStructuredData** (module) — Primary input is Finnish audio; module encapsulates the full transcription, enhancement, and extraction pipeline.
- **Transcriber** (component)
- **Extractor** (component)
- **LLMJudge** (component)

- **AudioToStructuredData** — instantiated via `AudioToStructuredData(use_azure=True)`; `use_azure` is read from `config.yaml` (`use_azure: true`).
- **Transcriber** (inside the module) — constructor args passed via `transcriber_ctor` in `run_poc.py`: `enhanced_transcript=True` (Finnish two-pass enhancement), `transcription_model` from `config.yaml` (`models.transcription: gpt-4o-transcribe`), `language=fi`, `compress_audio=True`. Changing the transcription model: update `config.yaml → models.transcription`.
- **Extractor** (inside the module) — constructor args via `extractor_ctor`: `model` from `config.yaml` (`models.extraction: gpt-5.4`). Schema and requirements are loaded from `schemas/output_schema.py` and `schemas/output_schema_requirements.json`; the hash file `schemas/output_schema.hash` detects prompt changes and triggers regeneration on the next run.
- **LLMJudge** — instantiated as `LLMJudge(model_provider="openai", use_azure=True)`; `use_azure` follows the same `config.yaml` flag. Called via `detect_hallucinations(source_text=<transcript>, extracted=<ticket_dict>)`. Output written to `output/<stem>_validation.json`.

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
- **Model preferences:** transcription_model: gpt-4o-transcribe, extraction_model: gpt-5.4, temperature: 0.0
- **Integration targets:** _none_

## Tests and evaluation
- Evaluation requirements: metrics: ['json_parsing', 'required_field_coverage', 'semantic_fixture_fact_matching', 'unsupported_value_introduction'], thresholds: none specified for single-fixture PoC, eval_framework: extraction_eval
- See `evals/` for the basic evaluation script and `evaluation_plan.md` for the full plan.

- **Azure OpenAI structured output:** The `MaintenanceTicket` schema uses `ConfigDict(extra='forbid')` on the Pydantic model — required by Azure OpenAI's `additionalProperties: false` constraint. Do not add bare `dict` or `list[dict]` field types; define named sub-models instead.
- **urgency Literal:** The `urgency` field is `Literal['low', 'medium', 'high'] | None`. Azure OpenAI will reject any other string. If the model cannot map the spoken urgency to one of these values, it should output `null` and add `"urgency"` to `uncertain_fields`.
- **Schema hash invalidation:** Editing `prompts/extraction_requirements.md` without deleting `schemas/output_schema.hash` causes the PoC to detect the change and regenerate the schema on the next run. This is intentional. If you want to skip regeneration (e.g. after a whitespace edit), recompute the hash manually: `python -c "import hashlib; print(hashlib.sha256(open('poc/prompts/extraction_requirements.md','rb').read()).hexdigest())"` and write the result to `schemas/output_schema.hash`.
- **Raw audio deletion:** The pipeline does not persist the input audio file — `AudioToStructuredData` processes it in memory. Do not add any logging or caching that writes the raw audio bytes to disk; this would violate the security constraint stated in the blueprint.
- **LLMJudge single-document unwrap:** The Extractor returns `result.extracted_fields` as a list (multi-document pipeline). The LLMJudge block in `run_poc.py` unwraps the first element for single-document PoC runs (`extracted_for_judge = extracted_for_judge[0]`). If you extend the pipeline to process multiple files in a batch, update this unwrap logic accordingly.
