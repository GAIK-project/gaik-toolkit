# Transcriber

Transcribe audio and video files with configurable transcription backends and optional transcript error fixing.

## Installation

```bash
pip install gaik[transcriber]
```

## System Requirements

- For basic API transcription of supported formats, no extra system dependency is required.
- For chunking and video decoding through PyDub, install `ffmpeg`.

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
print(result.enhanced_transcript)
```

## Transcription Models

`transcription_model` supports only:
- `"whisper"`
- `"gpt-4o-transcribe"`
- `"whisper_local"`

Resolution policy:
- If `transcription_model` is not provided:
  - Azure config value is used, typically `whisper-1` or `gpt-4o-transcribe`
  - OpenAI config value is used, typically `whisper` or `gpt-4o-transcribe`
- If `transcription_model="whisper"`:
  - Azure resolves to the configured Azure transcription deployment, typically `whisper-1`
  - OpenAI resolves to `whisper`
- If `transcription_model="gpt-4o-transcribe"`:
  - Azure/OpenAI both use `gpt-4o-transcribe`
- If `transcription_model="whisper_local"`:
  - ignores `use_azure`
  - uses the local transcription endpoint through `whisper_local.py`

## Chunking Behavior

- Chunking is used only for Whisper models:
  - `whisper`
  - `whisper-1`
- `gpt-4o-transcribe` is sent without chunking.
- `whisper_local` uses the local transcription server path and does not use PyDub chunking.

## Transcript Error Fixing

If `enhanced_transcript=True`, the transcriber runs the raw transcript through the standalone `enhance_transcript` software component.

- Input: raw transcript text
- Output: corrected transcript text
- Returned in:
  - `result.enhanced_transcript`

Note: the result field name remains `enhanced_transcript` for compatibility, even though it now contains the corrected transcript returned by `TranscriptEnhancer`.

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

If these local-only options are given while the model is not `whisper_local`, they are ignored with a message.

### How `language` works with `whisper_local`

When `transcription_model="whisper_local"`, the `language` value is sent to the remote Whisper server and used there to select the ASR model.

Typical behavior with the current HH server implementation:
- `language="fi"`:
  - uses `Finnish-NLP/whisper-large-finnish-v3-ct2`
- `language="en"`:
  - uses `large-v3` with English
- `language="auto"`:
  - uses `large-v3` with automatic language detection

So the combination works in two layers:
- `transcription_model="whisper_local"` selects the local/remote Whisper server path
- `language` selects the ASR model or language mode inside that server

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
| `AZURE_TRANSCRIPTION_MODEL` | Optional | Azure transcription deployment/model |
| `OPENAI_TRANSCRIPTION_MODEL` | Optional | OpenAI transcription model |

## Examples

- `implementation_layer/examples/software_components/transcriber/transcriber_example.py`
- `implementation_layer/examples/software_components/transcriber/transcriber_exmaple_local_model.py`

## License

MIT - see `LICENSE`.
