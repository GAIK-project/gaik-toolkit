# Audio to Structured Data (Software Component)

Wraps the transcriber and extractor building blocks into a single workflow and returns everything you need.

- Import: `from gaik.software_components.audio_to_structured_data import AudioToStructuredData`
- Example: `examples/software_components/audio_to_structured_data/pipeline_example.py`
- Outputs: raw/enhanced transcripts, extracted fields, and the generated schema + requirements.
- Schema reuse: see `generate_schema` / `schema_name` flags in the example; schemas are persisted under `schema/`.

## Basic Usage

```python
from gaik.software_components.audio_to_structured_data import AudioToStructuredData

pipeline = AudioToStructuredData(use_azure=True)
result = pipeline.run(
    file_path="sample.mp3",
    user_requirements="""
    Extract: Title, Summary, Key decisions, Action items
    """,
    transcriber_ctor={"enhanced_transcript": False},
    transcribe_options={},
    extractor_ctor={},
    extract_options={"save_json": False},
)

print(result.transcription.raw_transcript)
print(result.extracted_fields)
```

## Parameters

### Constructor
- `api_config`: Optional OpenAI/Azure config dict. If omitted, `get_openai_config(use_azure)` is used.
- `use_azure`: Boolean, passed to `get_openai_config` when `api_config` is not supplied.

### `run(...)`
- `file_path`: Path to the audio/video file to transcribe.
- `user_requirements`: Natural-language description of the fields to extract.
- `transcriber_ctor`: Dict passed to `Transcriber(...)` (e.g., `output_dir`, `compress_audio`, `enhanced_transcript`, `max_size_mb`, `max_duration_seconds`).
- `transcribe_options`: Dict passed to `Transcriber.transcribe(...)` per call (e.g., `custom_context`, `use_case_name`, `compress_audio` override).
- `extractor_ctor`: Dict passed to `DataExtractor(...)` (e.g., `model` to override the LLM; applies to both schema generation and extraction).
- `extract_options`: Dict passed to `DataExtractor.extract(...)` (e.g., `save_json`, `json_path`). The example also uses:
  - `generate_schema` (bool): If `True`, generate a new schema; if `False`, try to load from disk via `load_schema`.
  - `schema_name` (str): Base filename (no `.py`) for saving/loading schema; defaults to `schema`.
- `schema`: Optional pre-generated schema model to reuse.
- `requirements`: Optional `ExtractionRequirements` matching the schema.

### Returns (`PipelineResult`)
- `transcription`: `TranscriptionResult` with `raw_transcript`, `enhanced_transcript`, `job_id`.
- `extracted_fields`: List of dicts returned by the extractor.
- `schema`: Generated or provided schema model.
- `requirements`: Corresponding `ExtractionRequirements`.

## Schema Persistence (example pattern)
- To reuse a schema, set `generate_schema=False` and `schema_name` to the desired base name; ensure the schema and `<name>_requirements.json` exist under `schema/`.
- To generate and save a schema, set `generate_schema=True`; the example uses `pipeline.save_schema(...)` to write both artifacts to `schema/`.
