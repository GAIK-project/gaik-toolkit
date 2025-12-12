# Audio → Structured Data (transcriber + extractor)

Wraps the transcriber and extractor into a single workflow. Returns raw/enhanced transcripts, extracted fields, and the generated schema + requirements. Supports schema reuse/persistence (see `generate_schema` / `schema_name` flags in the example).

- Import: `from gaik.software_components.audio_to_structured_data import AudioToStructuredData`
- Example: `examples/software_components/audio_to_structured_data/pipeline_example.py`

## Basic Usage

```python
from gaik.software_components.audio_to_structured_data import AudioToStructuredData

pipeline = AudioToStructuredData(use_azure=True)
result = pipeline.run(
    file_path="sample.mp3",
    user_requirements="""Extract: Title, Summary, Key decisions, Action items""",
    transcriber_ctor={"enhanced_transcript": False},
    transcribe_options={},
    extractor_ctor={},                # e.g., {"model": "gpt-4.1"}
    extract_options={"save_json": False},
)

print(result.transcription.raw_transcript)
print(result.extracted_fields)
```

## Parameters (run)
- `file_path`: Audio/video file path.
- `user_requirements`: Natural-language fields to extract.
- `transcriber_ctor`: Args to `Transcriber(...)` (e.g., `output_dir`, `compress_audio`, `enhanced_transcript`, `max_size_mb`, `max_duration_seconds`).
- `transcribe_options`: Args to `Transcriber.transcribe(...)` (e.g., `custom_context`, `use_case_name`, per-call `compress_audio`).
- `extractor_ctor`: Args to `DataExtractor(...)` (e.g., `model` override, applied to schema generation and extraction).
- `extract_options`: Args to `DataExtractor.extract(...)` (e.g., `save_json`, `json_path`). Example adds `generate_schema` (bool) and `schema_name` (base filename) for schema reuse/persistence.
- `schema`, `requirements`: Optional pre-generated schema/requirements to reuse.

## Returns (`PipelineResult`)
- `transcription`: `TranscriptionResult` with `raw_transcript`, `enhanced_transcript`, `job_id`.
- `extracted_fields`: List of dicts.
- `schema`: Generated or provided schema model.
- `requirements`: Matching `ExtractionRequirements`.
