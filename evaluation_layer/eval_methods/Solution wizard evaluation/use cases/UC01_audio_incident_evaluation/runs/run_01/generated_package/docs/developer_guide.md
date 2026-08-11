# Developer Guide — Maintenance Fault Reporting via Finnish Voice

> Package structure, extension points, component configuration, tests, and evaluation.

## Architecture
This use case is driven by an **executable JSON blueprint** (`use_case.blueprint.json`) — the single source of truth. The PoC, the visual workflows (`workflow.mmd`, `workflow.bpmn`), and these docs are all *generated from it*. To change behaviour, edit the blueprint and regenerate; never hand-edit generated artifacts.

## Pipeline
| Step | Type | Component | Inputs | Outputs |
|------|------|-----------|--------|---------|
| record_voice_message | user_task | — | — | voice_message_audio |
| process_audio | automated_task | AudioToStructuredData <br/>opts: enhanced_transcript=True, language=fi, transcription_model=gpt-4o-transcribe, schema_ref=schemas/output_schema.py, requirements_ref=schemas/output_schema_requirements.json, extraction_model=gpt-5.4, temperature=0.0 | voice_message_audio | maintenance_ticket_json |
| validate_ticket | automated_task | LLMJudge <br/>opts: model_provider=azure_openai | maintenance_ticket_json | validation_report |
| supervisor_review | human_review | — | maintenance_ticket_json, validation_report | approved_ticket |

### Components and their options
- **AudioToStructuredData** (module) — Input is Finnish audio; module encapsulates transcription, Finnish enhancement, and structured extraction in a single pipeline. enhanced_transcript=True is set because language is Finnish.
- **LLMJudge** (component)

**AudioToStructuredData** is constructed in `run_poc.py` as `AudioToStructuredData(use_azure=True)`. The `transcriber_ctor` dict passed to `pipeline.run()` carries `enhanced_transcript=True` (Finnish two-pass enhancement), `transcription_model` (from `config.yaml → models.transcription`, default `gpt-4o-transcribe`), and `language="fi"`. The `extractor_ctor` dict carries `model` (from `config.yaml → models.extraction`, default `gpt-5.4`). Temperature is fixed at `0.0` in `config.yaml`.

**LLMJudge** is constructed inline in `run_poc.py` after the pipeline result is obtained: `LLMJudge(model_provider="openai", use_azure=True)`. The `use_azure` flag is taken from `config.yaml → use_azure`. The judge calls `detect_hallucinations(source_text=enhanced_transcript, extracted=ticket_dict)` and writes its report to `output/<stem>_validation.json`.

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
- Evaluation requirements: metrics: ['json_parse_success', 'required_field_coverage', 'semantic_fixture_fact_matching', 'unsupported_value_introduction'], threshold: no numerical threshold specified for single-fixture PoC, test_data: single supplied Finnish audio fixture
- See `evals/` for the basic evaluation script and `evaluation_plan.md` for the full plan.

**Schema hash caching:** `run_poc.py` hashes `prompts/extraction_requirements.md` on every run and compares it to `schemas/output_schema.hash`. If the prompt changed, the schema is regenerated automatically. If you edit `schemas/output_schema.py` directly without touching the prompt, delete `schemas/output_schema.hash` to force a reload — otherwise the stale hash will suppress regeneration.

**`urgency` Literal with empty string:** the generated `output_schema.py` declares `urgency` as `Optional[Literal['', 'low', 'medium', 'high']]`. The empty string `''` is an Azure OpenAI structured-output compatibility sentinel (the API requires every enum field to have at least one non-null value in the Literal). The GAIK Extractor maps `''` → `None` in post-processing; you will never see `''` in the output JSON. Do not remove it from the Pydantic model or Azure OpenAI will reject the schema.

**Finnish enhancement latency:** `enhanced_transcript=True` adds a second LLM pass over the raw transcript. For a typical 30-second field recording this adds 10–20 seconds; for a 5-minute recording expect ~60 seconds. Disable it (`enhanced_transcript=False` in `config.yaml` or `transcriber_ctor`) only for non-Finnish audio or latency-sensitive tests.

**Audio not retained:** `compress_audio=True` in `transcriber_ctor` instructs the transcriber to discard the audio file from any intermediate storage after transcription completes, satisfying the `stores_input_data=false` governance constraint.
