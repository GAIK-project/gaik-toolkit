# Transcriber

Transcribe audio and video files with configurable transcription backends and optional GPT enhancement.

## Installation

```bash
pip install gaik[transcriber]
```

## System Requirements

- For basic API transcription of supported formats, no extra system dependency is required.
- For chunking/video decoding through PyDub, install ffmpeg.

```bash
ffmpeg -version
```

## Quick Start

```python
from gaik.software_components.transcriber import Transcriber, get_openai_config

config = get_openai_config(use_azure=True)

transcriber = Transcriber(
    api_config=config,
    output_dir="transcripts",
    enhanced_transcript=True,
)

result = transcriber.transcribe(file_path="meeting.mp3")
print(result.raw_transcript)
```

## Transcription Models

`transcription_model` supports only:
- `"whisper"`
- `"gpt-4o-transcribe"`
- `"whisper_local"`

Resolution policy:
- If `transcription_model` is not provided:
  - `use_azure=True` -> `whisper-1`
  - `use_azure=False` -> `whisper`
- If `transcription_model="whisper"`:
  - `use_azure=True` -> `whisper-1`
  - `use_azure=False` -> `whisper`
- If `transcription_model="gpt-4o-transcribe"`:
  - both Azure/OpenAI -> `gpt-4o-transcribe`
- If `transcription_model="whisper_local"`:
  - ignores `use_azure`
  - uses local transcription endpoint through `whisper_local.py`

## Local Whisper Mode

When using `transcription_model="whisper_local"`, pass:
- `local_api_base` (required)
- `local_api_key` (required)

Optional local parameters:
- `language="auto"`
- `diarization=False`
- `speaker_count=None`
- `min_speakers=None`
- `max_speakers=None`
- `initial_prompt=None`

If these local-only options are given while model is not `whisper_local`, they are ignored with a message and no runtime error.

## Basic API

```python
from gaik.software_components.transcriber import Transcriber

transcriber = Transcriber(
    api_config=config,
    output_dir="workspace",
    compress_audio=True,            # backward-compatible, currently not used
    enhanced_transcript=True,
    max_size_mb=25,
    max_duration_seconds=1500,
    default_prompt="...",
    transcription_model=None,
    language="auto",
    diarization=False,
    speaker_count=None,
    min_speakers=None,
    max_speakers=None,
    initial_prompt=None,
    local_api_base=None,
    local_api_key=None,
)

result = transcriber.transcribe(
    file_path="audio.mp3",
    custom_context="",
    use_case_name=None,
    compress_audio=None,            # backward-compatible, currently not used
)
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_API_KEY` | Azure mode | Azure OpenAI API key |
| `AZURE_ENDPOINT` | Azure mode | Azure OpenAI endpoint URL |
| `OPENAI_API_KEY` | OpenAI mode | OpenAI API key |
| `AZURE_API_VERSION` | Optional | API version |

## Examples

- `implementation_layer/examples/software_components/transcriber/transcriber_example.py`
- `implementation_layer/examples/software_components/transcriber/transcriber_exmaple_local_model.py`

## License

MIT - see `LICENSE`.
